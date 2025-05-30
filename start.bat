@echo off
chcp 65001 >nul
echo 🚀 启动股票分析系统...

REM 检查Python是否安装
python --version >nul 2>&1
if errorlevel 1 (
    echo ❌ 错误: 未找到Python，请先安装Python 3.8或更高版本
    pause
    exit /b 1
)

echo ✅ Python检查通过

REM 检查虚拟环境
if not exist "venv" (
    echo 📦 创建虚拟环境...
    python -m venv venv
)

REM 激活虚拟环境
echo 🔧 激活虚拟环境...
call venv\Scripts\activate.bat

REM 安装依赖
echo 📥 安装依赖包...
pip install -r requirements.txt

REM 检查环境变量文件
if not exist ".env" (
    echo ⚙️ 创建环境变量文件...
    (
        echo # 数据库配置
        echo DB_HOST=localhost
        echo DB_USER=root
        echo DB_PASSWORD=root
        echo DB_NAME=stock_cursor
        echo DB_CHARSET=utf8mb4
        echo.
        echo # Flask配置
        echo SECRET_KEY=your-secret-key-here
        echo DEBUG=True
        echo.
        echo # Redis配置
        echo REDIS_HOST=localhost
        echo REDIS_PORT=6379
        echo REDIS_DB=0
        echo.
        echo # 日志配置
        echo LOG_LEVEL=INFO
        echo LOG_FILE=logs/stock_analysis.log
        echo.
        echo # 数据更新配置
        echo DATA_UPDATE_HOUR=18
        echo DATA_UPDATE_MINUTE=0
        echo.
        echo # 邮件配置
        echo EMAIL_SMTP_SERVER=smtp.qq.com
        echo EMAIL_SMTP_PORT=587
        echo EMAIL_USERNAME=
        echo EMAIL_PASSWORD=
    ) > .env
    echo ✅ 环境变量文件已创建，请根据需要修改 .env 文件
)

REM 创建日志目录
if not exist "logs" mkdir logs

echo.
echo 🎉 系统准备就绪！
echo.
echo 📝 启动命令:
echo    python run.py
echo.
echo 🌐 访问地址:
echo    http://localhost:5000
echo.
echo 📚 API文档:
echo    http://localhost:5000/api/stocks
echo.

REM 询问是否立即启动
set /p choice="是否立即启动应用？(y/n): "
if /i "%choice%"=="y" (
    echo 🚀 启动应用...
    python run.py
) else (
    echo 使用 'python run.py' 命令启动应用
)

pause 