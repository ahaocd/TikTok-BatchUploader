# TikTok-BatchUploader

TikTok全智能运营助手 - 集合AI与多技术栈，替代大量重复劳动

[![Python](https://img.shields.io/badge/Python-3.10+-blue.svg)](https://www.python.org/)
[![Playwright](https://img.shields.io/badge/Playwright-1.52.0-green.svg)](https://playwright.dev/)
[![License](https://img.shields.io/badge/License-MIT-yellow.svg)](LICENSE)

**黑盒智能体** | [www.xasia.cc](https://www.xasia.cc) | 智能体聚合平台 | 一键搭建跨境专线 | 电商网站 | 智能证书

---

## 预览

![预览](preview.png)

---

## 项目介绍

这是一个全自动化的TikTok运营工具，从内容采集到发布全流程自动化，亲自开发用于替代大量重复的人工操作。

### 全流程自动化

**1. 内容采集**
- 自动从抖音采集热门视频
- 支持按用户ID批量下载
- 自动去除水印
- 智能过滤已下载内容

**2. 视频剪辑**
- FFmpeg自动处理视频
- 统一分辨率和帧率
- 可选添加边框防重复检测
- 批量预处理节省时间

**3. AI文案改写**
- DeepSeek V3智能改写标题
- 通过提示词控制输出语言（英文/繁体/任意语言）
- 自动生成热门标签
- 避免内容重复被检测

**4. 自动发布**
- 云登指纹浏览器多账号管理
- 自动轮换账号发布
- 模拟真人操作行为
- 随机延迟防风控

**5. 数据管理**
- SQLite数据库去重
- 上传记录追踪
- 支持断点续传
- 日志完整记录

---

## 核心优势

- 全自动: 采集-下载-剪辑-改写-发布一条龙
- 多账号: 支持多个TikTok账号轮换发布
- AI驱动: DeepSeek V3智能文案，提升内容质量
- 指纹浏览器: 云登浏览器独立环境，账号隔离
- Web界面: 可视化操作，配置简单
- 开源免费: MIT协议，可自由修改

---

## 快速开始

### 环境要求

- Python 3.10+
- FFmpeg
- 云登浏览器 (https://www.yunlogin.com/)
- DeepSeek API (https://siliconflow.cn)

### 安装

```bash
git clone https://github.com/ahaocd/TikTok-BatchUploader.git
cd TikTok-BatchUploader
pip install -r requirements.txt
playwright install chromium
```

### 运行

```bash
python tiktok_api.py
```

访问: http://localhost:5409

---

## 配置说明

### config.json

```json
{
  "ai": {
    "enabled": true,
    "api_key": "sk-your-api-key",
    "base_url": "https://api.siliconflow.cn/v1",
    "model": "deepseek-ai/DeepSeek-V3",
    "temperature": 0.7
  },
  "proxy": {
    "enabled": false,
    "http": "http://127.0.0.1:7897",
    "https": "http://127.0.0.1:7897"
  }
}
```

### user_config.json

```json
{
  "custom_tags": ["#fyp", "#viral", "#trending"],
  "ai_prompt_template": "把标题改写成英文，简短有吸引力"
}
```

---

## 云登浏览器设置

1. 下载安装: https://www.yunlogin.com/
2. 创建环境 -> 选择TikTok平台
3. 启动环境 -> 手动登录TikTok -> 保存
4. 保持云登客户端后台运行

---

## 自动创建的文件

| 文件 | 说明 |
|------|------|
| config.json | AI和代理配置 |
| user_config.json | 自定义标签和提示词 |
| db/database.db | SQLite去重数据库 |
| logs/*.log | 日志文件 |
| cookies/ | 抖音下载Cookie |

---

## 运营建议

当流量有所好转后，建议：
- 使用手机登录账号进行精细化运营
- 结合热点内容提升曝光
- 保持稳定的发布频率
- 关注数据反馈优化内容

---

## 联系方式

**黑盒智能体** - [www.xasia.cc](https://www.xasia.cc)

智能体聚合平台 | 一键搭建跨境专线 | 电商网站 | 智能证书

---

## License

MIT License
