#!/usr/bin/env python
# -*- coding: utf-8 -*-
"""
TikTok-BatchUploader Web API
========================================
简单的Web API，用于管理TikTok批量上传任务

功能：
1. 云登浏览器环境管理
2. 配置管理（AI、下载、上传）
3. 批量任务启动和进度查询
"""

import asyncio
import json
import threading
import logging
from pathlib import Path
from flask import Flask, request, jsonify, Response, send_from_directory
from flask_cors import CORS

from conf import BASE_DIR
from utils.yunlogin_api import YunLoginAPI
from social_auto_upload_tool import ContentAutomationAgent

# 配置日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(name)s: %(message)s',
    datefmt='%Y-%m-%d %H:%M:%S'
)
logger = logging.getLogger(__name__)

# ========================================================================
# Flask应用初始化
# ========================================================================
app = Flask(__name__, static_folder='web', static_url_path='')
CORS(app)  # 允许跨域

# 全局任务状态
current_task = {
    "running": False,
    "progress": 0,
    "total": 0,
    "status": "idle",
    "message": ""
}

# ========================================================================
# 配置文件路径
# ========================================================================
CONFIG_PATH = BASE_DIR / "config.json"  # 项目本地配置
USER_CONFIG_PATH = BASE_DIR / "user_config.json"  # 用户自定义配置（标签、提示词）


def load_config():
    """加载项目配置"""
    if CONFIG_PATH.exists():
        try:
            with open(CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "ai": {"enabled": False, "api_key": "", "base_url": "", "model": "", "temperature": 0.7},
        "download": {"count": 10},
        "upload": {"delay_min": 3, "delay_max": 8, "stay_time_min": 20, "stay_time_max": 60}
    }


def save_config(config_data):
    """保存项目配置"""
    try:
        with open(CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存配置失败: {e}")
        return False


def load_user_config():
    """加载用户自定义配置（标签、提示词）"""
    if USER_CONFIG_PATH.exists():
        try:
            with open(USER_CONFIG_PATH, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception:
            pass
    return {
        "custom_tags": [],
        "ai_prompt_template": ""
    }


def save_user_config(config_data):
    """保存用户自定义配置"""
    try:
        with open(USER_CONFIG_PATH, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        logger.error(f"保存用户配置失败: {e}")
        return False


# ========================================================================
# API 1: 健康检查
# ========================================================================
@app.route('/api/health', methods=['GET'])
def health_check():
    """健康检查接口"""
    return jsonify({
        "status": "ok",
        "message": "TikTok-BatchUploader API is running"
    })


# ========================================================================
# 前端路由：Serve HTML
# ========================================================================
@app.route('/')
def index():
    """提供前端HTML页面"""
    return send_from_directory('web', 'index.html')


# ========================================================================
# API 2: 获取云登环境列表
# ========================================================================
@app.route('/api/yunlogin/envs', methods=['GET'])
def get_yunlogin_envs():
    """
    获取云登浏览器环境列表

    返回：
    {
        "success": true,
        "data": [
            {
                "id": "env_123",
                "name": "TikTok账号A",
                "status": "stopped"
            }
        ]
    }
    """
    try:
        api = YunLoginAPI()

        # 检查云登客户端状态
        if not api.check_status():
            return jsonify({
                "success": False,
                "message": "云登浏览器客户端未运行"
            }), 503

        # 获取环境列表
        envs = api.get_all_environments()

        if not envs:
            return jsonify({
                "success": True,
                "data": [],
                "message": "没有找到环境（请在云登中创建TikTok环境）"
            })

        # 格式化环境数据
        env_list = []
        for env in envs:
            env_list.append({
                "id": env.get("shopId", ""),
                "name": env.get("accountName", "未命名"),
                "remark": env.get("remark", ""),
                "status": "stopped"  # 云登API不返回运行状态，默认为stopped
            })

        return jsonify({
            "success": True,
            "data": env_list,
            "message": f"找到 {len(env_list)} 个环境"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取环境列表失败: {str(e)}"
        }), 500


# ========================================================================
# API 3: 获取配置
# ========================================================================
@app.route('/api/config', methods=['GET'])
def get_config():
    """获取系统配置（从本地config.json读取）"""
    try:
        config_data = load_config()
        return jsonify({
            "success": True,
            "data": config_data
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取配置失败: {str(e)}"
        }), 500


# ========================================================================
# API 4: 更新配置
# ========================================================================
@app.route('/api/config', methods=['POST'])
def update_config():
    """更新系统配置（保存到本地config.json）"""
    try:
        data = request.get_json()
        
        # 加载现有配置
        config_data = load_config()
        
        # 更新AI配置
        if 'ai' in data:
            ai_config = data['ai']
            if 'enabled' in ai_config:
                config_data['ai']['enabled'] = ai_config['enabled']
            if 'api_key' in ai_config:
                config_data['ai']['api_key'] = ai_config['api_key']
            if 'base_url' in ai_config:
                config_data['ai']['base_url'] = ai_config['base_url']
            if 'model' in ai_config:
                config_data['ai']['model'] = ai_config['model']
            if 'temperature' in ai_config:
                config_data['ai']['temperature'] = ai_config['temperature']
        
        # 更新下载配置
        if 'download' in data:
            config_data['download'].update(data['download'])
        
        # 更新上传配置
        if 'upload' in data:
            config_data['upload'].update(data['upload'])
        
        # 保存配置
        if save_config(config_data):
            return jsonify({
                "success": True,
                "message": "配置已保存"
            })
        else:
            return jsonify({
                "success": False,
                "message": "保存配置失败"
            }), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"更新配置失败: {str(e)}"
        }), 500


# ========================================================================
# API 4.5: 账号管理
# ========================================================================
@app.route('/api/accounts', methods=['GET'])
def get_accounts():
    """获取抖音账号列表"""
    try:
        from social_auto_upload_tool import AccountManager
        account_mgr = AccountManager()
        accounts = account_mgr.config.get("source_accounts", [])
        return jsonify({
            "success": True,
            "data": accounts
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取账号失败: {str(e)}"
        }), 500

@app.route('/api/accounts', methods=['POST'])
def save_accounts():
    """保存抖音账号列表"""
    try:
        data = request.get_json()
        accounts = data.get('accounts', [])
        
        from social_auto_upload_tool import AccountManager
        account_mgr = AccountManager()
        account_mgr.config["source_accounts"] = accounts
        
        # 保存到配置文件
        import json
        with open(account_mgr.config_path, 'w', encoding='utf-8') as f:
            json.dump(account_mgr.config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"保存了 {len(accounts)} 个账号到配置文件")
        return jsonify({
            "success": True,
            "message": f"已保存 {len(accounts)} 个账号"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"保存账号失败: {str(e)}"
        }), 500

@app.route('/api/accounts/add', methods=['POST'])
def add_account():
    """添加单个抖音账号"""
    try:
        data = request.get_json()
        name = data.get('name', '')
        sec_user_id = data.get('sec_user_id', '')
        
        if not name or not sec_user_id:
            return jsonify({
                "success": False,
                "message": "账号名称和用户ID不能为空"
            }), 400
        
        # 验证sec_user_id格式
        if "..." in sec_user_id or len(sec_user_id) < 20:
            return jsonify({
                "success": False,
                "message": f"无效的用户ID: '{sec_user_id}'（应为完整的sec_user_id）"
            }), 400
        
        from social_auto_upload_tool import AccountManager
        account_mgr = AccountManager()
        
        # 检查是否已存在
        for acc in account_mgr.config.get("source_accounts", []):
            if acc.get("sec_user_id") == sec_user_id:
                return jsonify({
                    "success": False,
                    "message": f"账号 '{sec_user_id}' 已存在"
                }), 400
        
        # 添加新账号
        from datetime import datetime
        new_account = {
            "name": name,
            "sec_user_id": sec_user_id,
            "enabled": True,
            "last_check": None,
            "added_at": datetime.now().isoformat(),
            "description": ""
        }
        account_mgr.config["source_accounts"].append(new_account)
        
        # 保存到配置文件
        import json
        with open(account_mgr.config_path, 'w', encoding='utf-8') as f:
            json.dump(account_mgr.config, f, ensure_ascii=False, indent=2)
        
        logger.info(f"添加账号: {name} -> {sec_user_id}")
        return jsonify({
            "success": True,
            "message": f"已添加账号: {name}"
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"添加账号失败: {str(e)}"
        }), 500


# ========================================================================
# API 4.8: 预下载视频（仅下载，不上传）
# ========================================================================
@app.route('/api/task/download', methods=['POST'])
def pre_download():
    """
    预下载视频到Downloaded池（仅下载，不启动上传）
    
    请求体：
    {
        "count": 5  // 每个账号下载数量
    }
    """
    try:
        data = request.get_json()
        count = data.get('count', 5)
        
        # 在后台线程执行下载
        def run_download():
            try:
                import asyncio
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)
                
                agent = ContentAutomationAgent()
                source_accounts = agent.account_mgr.get_source_accounts()
                
                if not source_accounts:
                    return {"success": False, "error": "没有配置抖音账号"}
                
                total_downloaded = 0
                for acc in source_accounts:
                    try:
                        result = loop.run_until_complete(
                            agent.downloader.download_account_videos(
                                sec_user_id=acc['sec_user_id'],
                                count=count,
                                skip_if_exists=True
                            )
                        )
                        if result and result.get('success'):
                            total_downloaded += result.get('success_count', 0)
                            logger.info(f"✅ 账号 {acc['name']} 下载成功: {result.get('success_count')} 个")
                    except Exception as e:
                        logger.error(f"❌ 账号 {acc['name']} 下载失败: {e}")
                
                loop.close()
                return {"success": True, "downloaded": total_downloaded}
            except Exception as e:
                logger.error(f"预下载失败: {e}")
                return {"success": False, "error": str(e)}
        
        # 同步执行下载（等待完成）
        result = run_download()
        return jsonify(result)
        
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"预下载失败: {str(e)}"
        }), 500


# ========================================================================
# API 5: 启动批量任务
# ========================================================================
@app.route('/api/task/start', methods=['POST'])
def start_task():
    """
    启动批量下载上传任务

    请求体：
    {
        "sec_user_id": "MS4wLjABAAAA...",
        "count": 10,
        "ai_enabled": true
    }
    """
    global current_task

    try:
        if current_task["running"]:
            return jsonify({
                "success": False,
                "message": "任务正在运行中"
            }), 400

        data = request.get_json()
        sec_user_id = data.get('sec_user_id', '')
        count = data.get('count', 10)
        ai_enabled = data.get('ai_enabled', True)
        auto_download = data.get('auto_download', True)  # 是否启用自动下载
        upload_pool = data.get('upload_pool', 'alternating')  # 视频来源：alternating/downloaded/videos

        # 如果sec_user_id为空，尝试从配置文件读取第一个有效账号
        if not sec_user_id:
            try:
                from social_auto_upload_tool import AccountManager
                account_mgr = AccountManager()
                source_accounts = account_mgr.get_source_accounts()
                if source_accounts:
                    sec_user_id = source_accounts[0].get('sec_user_id', '')
                    logger.info(f"从配置读取账号: {source_accounts[0].get('name', '未命名')} -> {sec_user_id}")
                else:
                    return jsonify({
                        "success": False,
                        "message": "未配置有效的抖音账号！请在 social_auto_upload/videos/accounts_config.json 中配置或在前端添加账号"
                    }), 400
            except Exception as e:
                logger.error(f"读取账号配置失败: {e}")
                return jsonify({
                    "success": False,
                    "message": f"读取账号配置失败: {str(e)}"
                }), 400
        
        # 再次验证sec_user_id
        if not sec_user_id or "..." in sec_user_id or len(sec_user_id) < 20:
            return jsonify({
                "success": False,
                "message": f"无效的抖音用户ID: '{sec_user_id}'（应为完整的sec_user_id，如 MS4wLjABAAAAxxxxxxx）"
            }), 400

        # 处理完整URL：提取user/后面的ID
        if 'douyin.com/user/' in sec_user_id:
            import re
            match = re.search(r'/user/([^/?]+)', sec_user_id)
            if match:
                sec_user_id = match.group(1)
                logger.info(f"从URL提取用户ID: {sec_user_id}")
            else:
                return jsonify({
                    "success": False,
                    "message": "无法从URL提取用户ID"
                }), 400

        # 重置任务状态
        current_task = {
            "running": True,
            "progress": 0,
            "total": count,
            "status": "starting",
            "message": "任务启动中..."
        }

        # 在后台线程启动任务
        def run_task():
            global current_task
            try:
                current_task["message"] = "正在初始化..."

                agent = ContentAutomationAgent()

                current_task["message"] = "开始批量下载和上传..."

                # 调用真正的批量任务
                loop = asyncio.new_event_loop()
                asyncio.set_event_loop(loop)

                result = loop.run_until_complete(
                    agent.batch_download_and_upload(
                        sec_user_id=sec_user_id,
                        count=count,
                        target_platforms=["tiktok"],
                        ai_enabled=ai_enabled,
                        skip_download=not auto_download,  # 如果关闭自动下载，则跳过下载步骤
                        upload_pool=upload_pool  # 视频来源
                    )
                )

                loop.close()

                current_task["running"] = False
                current_task["status"] = "completed"
                current_task["progress"] = current_task["total"]
                current_task["message"] = f"任务完成！下载: {result.get('downloaded', 0)}, 上传: {result.get('uploaded', 0)}"

            except Exception as e:
                current_task["running"] = False
                current_task["status"] = "error"
                current_task["message"] = f"任务失败: {str(e)}"

        # 启动后台线程
        task_thread = threading.Thread(target=run_task, daemon=True)
        task_thread.start()

        return jsonify({
            "success": True,
            "message": "任务已启动",
            "data": {
                "sec_user_id": sec_user_id,
                "count": count,
                "ai_enabled": ai_enabled
            }
        })

    except Exception as e:
        current_task["running"] = False
        return jsonify({
            "success": False,
            "message": f"启动任务失败: {str(e)}"
        }), 500


# ========================================================================
# API 6: 获取任务进度
# ========================================================================
@app.route('/api/task/progress', methods=['GET'])
def get_task_progress():
    """
    获取当前任务进度

    返回：
    {
        "success": true,
        "data": {
            "running": true,
            "progress": 5,
            "total": 10,
            "status": "downloading",
            "message": "正在下载第5个视频..."
        }
    }
    """
    return jsonify({
        "success": True,
        "data": current_task
    })


# ========================================================================
# API 7: 停止任务
# ========================================================================
@app.route('/api/task/stop', methods=['POST'])
def stop_task():
    """停止当前任务"""
    global current_task

    try:
        if not current_task["running"]:
            return jsonify({
                "success": False,
                "message": "没有正在运行的任务"
            }), 400

        # 创建停止标记文件
        stop_file = BASE_DIR / "STOP_UPLOAD"
        stop_file.touch()

        current_task["status"] = "stopping"
        current_task["message"] = "正在停止任务..."

        return jsonify({
            "success": True,
            "message": "停止信号已发送"
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"停止任务失败: {str(e)}"
        }), 500


# ========================================================================
# API 8: 获取视频池统计
# ========================================================================
@app.route('/api/stats', methods=['GET'])
def get_stats():
    """
    获取视频池统计信息

    返回：
    {
        "success": true,
        "data": {
            "downloaded": 149,  # Downloaded文件夹视频数
            "videos": 0,        # videos文件夹视频数
            "uploaded": 0       # 已上传数量（从数据库读取）
        }
    }
    """
    try:
        # Downloaded文件夹
        downloaded_dir = BASE_DIR / "douyin-downloader" / "Downloaded"
        downloaded_count = 0
        if downloaded_dir.exists():
            downloaded_count = sum(1 for f in downloaded_dir.rglob("*.mp4"))

        # videos文件夹（项目根目录）
        videos_dir = BASE_DIR / "videos"
        videos_count = 0
        if videos_dir.exists():
            videos_count = sum(1 for f in videos_dir.rglob("*.mp4"))

        # 已上传数量（从数据库读取）
        db_file = BASE_DIR / "social_auto_upload" / "videos" / "upload_records.json"
        uploaded_count = 0
        if db_file.exists():
            try:
                with open(db_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    records = data.get('records', {})
                    # records是字典，统计已上传到tiktok的数量
                    uploaded_count = sum(1 for r in records.values() if r.get('uploaded_to', {}).get('tiktok'))
            except:
                pass

        return jsonify({
            "success": True,
            "data": {
                "downloaded": downloaded_count,
                "videos": videos_count,
                "uploaded": uploaded_count
            }
        })

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"获取统计失败: {str(e)}"
        }), 500


# ========================================================================
# API 9: 打开文件夹
# ========================================================================
@app.route('/api/open-folder', methods=['POST'])
def open_folder():
    """
    打开文件夹（在Windows资源管理器中）

    请求体：
    {
        "path": "E:\\liusisi\\SmartSisi\\llm\\a2a\\tools\\tiktok-batch-uploader\\videos"
    }
    """
    try:
        import subprocess
        import os

        data = request.get_json()
        path = data.get('path', '')

        if not path:
            return jsonify({
                "success": False,
                "message": "路径为空"
            }), 400

        # 处理相对路径：转换为绝对路径
        if path.startswith('./') or path.startswith('.\\'):
            path = str(BASE_DIR / path[2:])
        elif not os.path.isabs(path):
            path = str(BASE_DIR / path)

        # 规范化路径
        path = os.path.normpath(path)

        # 检查路径是否存在
        if not os.path.exists(path):
            return jsonify({
                "success": False,
                "message": f"路径不存在: {path}"
            }), 404

        # 如果是文件，获取其所在目录
        if os.path.isfile(path):
            path = os.path.dirname(path)

        # 在Windows资源管理器中打开文件夹
        subprocess.Popen(f'explorer "{path}"', shell=True)

        return jsonify({
            "success": True,
            "message": "文件夹已打开",
            "path": path
        })

    except Exception as e:
        logger.error(f"打开文件夹失败: {e}")
        return jsonify({
            "success": False,
            "message": f"打开文件夹失败: {str(e)}"
        }), 500


# ========================================================================
# API 10: 获取用户自定义配置（标签、提示词）
# ========================================================================
@app.route('/api/user-config', methods=['GET'])
def get_user_config():
    """
    获取用户自定义配置（自定义标签、AI提示词模板）

    返回：
    {
        "success": true,
        "data": {
            "custom_tags": ["#标签1", "#标签2", ...],
            "ai_prompt_template": "完整的AI提示词模板文本..."
        }
    }
    """
    try:
        user_config = load_user_config()
        return jsonify({
            "success": True,
            "data": user_config
        })
    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"加载用户配置失败: {str(e)}"
        }), 500


# ========================================================================
# API 11: 保存用户自定义配置（标签、提示词）
# ========================================================================
@app.route('/api/user-config', methods=['POST'])
def update_user_config():
    """
    保存用户自定义配置

    请求体：
    {
        "custom_tags": ["#标签1", "#标签2", ...],  // 可选
        "ai_prompt_template": "..."                 // 可选
    }
    """
    try:
        data = request.get_json()

        # 加载现有配置
        user_config = load_user_config()

        # 更新配置
        if 'custom_tags' in data:
            # 如果传入的是字符串（多行文本），转换为列表
            if isinstance(data['custom_tags'], str):
                tags_text = data['custom_tags']
                # 按行分割，过滤空行
                tags_list = [line.strip() for line in tags_text.split('\n') if line.strip()]
                user_config['custom_tags'] = tags_list
            else:
                user_config['custom_tags'] = data['custom_tags']

        if 'ai_prompt_template' in data:
            user_config['ai_prompt_template'] = data['ai_prompt_template']

        # 保存配置
        if save_user_config(user_config):
            return jsonify({
                "success": True,
                "message": "用户配置已保存"
            })
        else:
            return jsonify({
                "success": False,
                "message": "保存配置失败"
            }), 500

    except Exception as e:
        return jsonify({
            "success": False,
            "message": f"保存用户配置失败: {str(e)}"
        }), 500


# ========================================================================
# 主函数
# ========================================================================
if __name__ == '__main__':
    print("=" * 70)
    print(" " * 20 + "TikTok-BatchUploader API")
    print("=" * 70)
    print(f"API地址: http://127.0.0.1:5409")
    print(f"前端地址: http://localhost:5173")
    print("=" * 70)

    app.run(host='0.0.0.0', port=5409, debug=False)
