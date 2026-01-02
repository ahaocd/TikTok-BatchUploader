@echo off
REM ========================================================================
REM TikTok-BatchUploader 一键安装脚本 (Windows)
REM ========================================================================
REM 用法: 双击运行或在命令行运行 install.bat
REM ========================================================================

setlocal enabledelayedexpansion
chcp 65001 >nul

echo.
echo ======================================================================
echo TikTok-BatchUploader 一键安装
echo ======================================================================
echo.

REM 步骤1: 检查Python
echo [1/7] 检查Python版本...
python --version >nul 2>&1
if errorlevel 1 (
    echo [FAIL] Python未安装
    echo 请访问 https://www.python.org/downloads/ 下载安装
    pause
    exit /b 1
) else (
    for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYTHON_VERSION=%%i
    echo [OK] Python !PYTHON_VERSION!
)

REM 步骤2: 检查FFmpeg
echo.
echo [2/7] 检查FFmpeg...
ffmpeg -version >nul 2>&1
if errorlevel 1 (
    echo [WARN] FFmpeg未安装
    echo 请安装FFmpeg:
    echo   - 使用Chocolatey: choco install ffmpeg
    echo   - 或下载: https://ffmpeg.org/download.html
    echo.
    set /p CONTINUE="是否继续安装？(y/n): "
    if /i not "!CONTINUE!"=="y" exit /b 1
) else (
    echo [OK] FFmpeg已安装
)

REM 步骤3: 安装依赖
echo.
echo [3/7] 安装Python依赖...
python -m pip install -r requirements.txt
if errorlevel 1 (
    echo [FAIL] 依赖安装失败
    pause
    exit /b 1
) else (
    echo [OK] 依赖安装成功
)

REM 步骤4: 安装Playwright
echo.
echo [4/7] 安装Playwright浏览器...
python -m playwright install chromium
if errorlevel 1 (
    echo [WARN] Playwright安装失败（如果使用云登浏览器则不影响）
) else (
    echo [OK] Playwright浏览器安装成功
)

REM 步骤5: 创建配置文件
echo.
echo [5/7] 创建配置文件...

REM conf.py
if not exist "conf.py" (
    if exist "conf.example.py" (
        copy conf.example.py conf.py >nul
        echo [OK] 已创建 conf.py
        echo [WARN] 请编辑 conf.py 修改配置
    ) else (
        echo [FAIL] conf.example.py不存在
    )
) else (
    echo [WARN] conf.py已存在，跳过
)

REM system.conf
if not exist "..\..\..\system.conf" (
    if exist "..\..\..\system.conf.example" (
        copy ..\..\..\system.conf.example ..\..\..\system.conf >nul
        echo [OK] 已创建 system.conf
        echo [WARN] 请编辑 system.conf 配置DeepSeek API密钥
    ) else (
        echo [WARN] system.conf.example不存在，跳过
    )
) else (
    echo [WARN] system.conf已存在，跳过
)

REM 步骤6: 创建目录
echo.
echo [6/7] 创建必要的目录...
if not exist "db" mkdir db
if not exist "logs" mkdir logs
if not exist "videos" mkdir videos
if not exist "videos\douyin" mkdir videos\douyin
if not exist "videos\tiktok" mkdir videos\tiktok
echo [OK] 目录创建完成

REM 步骤7: 运行测试
echo.
echo [7/7] 运行快速测试...
if exist "test_quick.py" (
    python test_quick.py
    if errorlevel 1 (
        echo [WARN] 测试未通过
    )
) else (
    echo [WARN] test_quick.py不存在，跳过测试
)

REM 安装完成
echo.
echo ======================================================================
echo 安装完成
echo ======================================================================
echo.
echo 下一步操作：
echo 1. 编辑配置文件:
echo    - conf.py: 设置Chrome路径
echo    - ..\..\..\system.conf: 配置DeepSeek API密钥
echo.
echo 2. 启动云登浏览器:
echo    - 打开云登客户端
echo    - 创建至少1个TikTok环境
echo    - 确保已登录TikTok账号
echo.
echo 3. 运行测试:
echo    python test_quick.py
echo.
echo 4. 开始使用:
echo    python social_auto_upload_tool.py
echo.
echo ======================================================================
echo.

pause
