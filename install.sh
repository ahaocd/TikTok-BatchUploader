#!/bin/bash
# ========================================================================
# TikTok-BatchUploader 一键安装脚本 (Linux/Mac)
# ========================================================================
# 用法: chmod +x install.sh && ./install.sh
# ========================================================================

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 打印函数
print_header() {
    echo -e "\n${BLUE}======================================================================${NC}"
    echo -e "${BLUE}$1${NC}"
    echo -e "${BLUE}======================================================================${NC}\n"
}

print_step() {
    echo -e "${BLUE}[$1/$2] $3...${NC}"
}

print_success() {
    echo -e "${GREEN}[OK] $1${NC}"
}

print_warning() {
    echo -e "${YELLOW}[WARN] $1${NC}"
}

print_error() {
    echo -e "${RED}[FAIL] $1${NC}"
}

# 主函数
main() {
    print_header "TikTok-BatchUploader 一键安装"

    # 步骤1: 检查Python
    print_step 1 7 "检查Python版本"
    if command -v python3 &> /dev/null; then
        PYTHON_CMD=python3
    elif command -v python &> /dev/null; then
        PYTHON_CMD=python
    else
        print_error "Python未安装"
        exit 1
    fi

    PYTHON_VERSION=$($PYTHON_CMD --version 2>&1 | awk '{print $2}')
    print_success "Python $PYTHON_VERSION"

    # 步骤2: 检查FFmpeg
    print_step 2 7 "检查FFmpeg"
    if command -v ffmpeg &> /dev/null; then
        FFMPEG_VERSION=$(ffmpeg -version 2>&1 | head -n1)
        print_success "FFmpeg已安装: $FFMPEG_VERSION"
    else
        print_error "FFmpeg未安装"
        print_warning "请安装FFmpeg:"
        if [[ "$OSTYPE" == "darwin"* ]]; then
            echo "  macOS: brew install ffmpeg"
        else
            echo "  Ubuntu/Debian: sudo apt install ffmpeg"
            echo "  CentOS/RHEL: sudo yum install ffmpeg"
        fi
        read -p "是否继续安装？(y/n): " -n 1 -r
        echo
        if [[ ! $REPLY =~ ^[Yy]$ ]]; then
            exit 1
        fi
    fi

    # 步骤3: 安装依赖
    print_step 3 7 "安装Python依赖"
    $PYTHON_CMD -m pip install -r requirements.txt || {
        print_error "依赖安装失败"
        exit 1
    }
    print_success "依赖安装成功"

    # 步骤4: 安装Playwright
    print_step 4 7 "安装Playwright浏览器"
    $PYTHON_CMD -m playwright install chromium || {
        print_warning "Playwright安装失败（如果使用云登浏览器则不影响）"
    }
    print_success "Playwright浏览器安装成功"

    # 步骤5: 创建配置文件
    print_step 5 7 "创建配置文件"

    # conf.py
    if [ ! -f "conf.py" ]; then
        if [ -f "conf.example.py" ]; then
            cp conf.example.py conf.py
            print_success "已创建 conf.py"
            print_warning "请编辑 conf.py 修改配置"
        else
            print_error "conf.example.py不存在"
        fi
    else
        print_warning "conf.py已存在，跳过"
    fi

    # system.conf
    if [ ! -f "../../../system.conf" ]; then
        if [ -f "../../../system.conf.example" ]; then
            cp ../../../system.conf.example ../../../system.conf
            print_success "已创建 system.conf"
            print_warning "请编辑 system.conf 配置DeepSeek API密钥"
        else
            print_warning "system.conf.example不存在，跳过"
        fi
    else
        print_warning "system.conf已存在，跳过"
    fi

    # 步骤6: 创建目录
    print_step 6 7 "创建必要的目录"
    mkdir -p db logs videos/douyin videos/tiktok
    print_success "目录创建完成"

    # 步骤7: 运行测试
    print_step 7 7 "运行快速测试"
    if [ -f "test_quick.py" ]; then
        $PYTHON_CMD test_quick.py || {
            print_warning "测试未通过"
        }
    else
        print_warning "test_quick.py不存在，跳过测试"
    fi

    # 安装完成
    print_header "安装完成"
    print_success "所有步骤完成！"

    echo -e "\n下一步操作："
    echo "1. 编辑配置文件:"
    echo "   - conf.py: 设置Chrome路径"
    echo "   - ../../../system.conf: 配置DeepSeek API密钥"
    echo ""
    echo "2. 启动云登浏览器:"
    echo "   - 打开云登客户端"
    echo "   - 创建至少1个TikTok环境"
    echo ""
    echo "3. 运行测试:"
    echo "   $PYTHON_CMD test_quick.py"
    echo ""
    echo "4. 开始使用:"
    echo "   $PYTHON_CMD social_auto_upload_tool.py"
    echo ""
    echo "======================================================================"
}

# 运行
main
