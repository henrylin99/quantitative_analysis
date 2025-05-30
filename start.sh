#!/bin/bash

echo "🚀 启动股票分析系统..."

# 检查Python版本
python_version=$(python3 --version 2>&1 | awk '{print $2}' | cut -d. -f1,2)
required_version="3.8"

if [ "$(printf '%s\n' "$required_version" "$python_version" | sort -V | head -n1)" != "$required_version" ]; then
    echo "❌ 错误: 需要Python 3.8或更高版本，当前版本: $python_version"
    exit 1
fi

echo "✅ Python版本检查通过: $python_version"

# 检查虚拟环境
if [ ! -d "venv" ]; then
    echo "📦 创建虚拟环境..."
    python3 -m venv venv
fi

# 激活虚拟环境
echo "🔧 激活虚拟环境..."
source venv/bin/activate

# 安装依赖
echo "📥 安装依赖包..."
pip install -r requirements.txt

# 检查环境变量文件
if [ ! -f ".env" ]; then
    echo "⚙️ 创建环境变量文件..."
    cat > .env << EOF
# 数据库配置
DB_HOST=localhost
DB_USER=root
DB_PASSWORD=root
DB_NAME=stock_cursor
DB_CHARSET=utf8mb4

# Flask配置
SECRET_KEY=your-secret-key-here
DEBUG=True

# Redis配置
REDIS_HOST=localhost
REDIS_PORT=6379
REDIS_DB=0

# 日志配置
LOG_LEVEL=INFO
LOG_FILE=logs/stock_analysis.log

# 数据更新配置
DATA_UPDATE_HOUR=18
DATA_UPDATE_MINUTE=0

# 邮件配置
EMAIL_SMTP_SERVER=smtp.qq.com
EMAIL_SMTP_PORT=587
EMAIL_USERNAME=
EMAIL_PASSWORD=
EOF
    echo "✅ 环境变量文件已创建，请根据需要修改 .env 文件"
fi

# 创建日志目录
mkdir -p logs

# 检查MySQL连接
echo "🔍 检查数据库连接..."
python3 -c "
import pymysql
import os
from dotenv import load_dotenv

load_dotenv()

try:
    conn = pymysql.connect(
        host=os.getenv('DB_HOST', 'localhost'),
        user=os.getenv('DB_USER', 'root'),
        password=os.getenv('DB_PASSWORD', 'root'),
        charset='utf8mb4'
    )
    
    # 检查数据库是否存在
    cursor = conn.cursor()
    cursor.execute('SHOW DATABASES LIKE \"stock_cursor\"')
    result = cursor.fetchone()
    
    if not result:
        print('📊 创建数据库...')
        cursor.execute('CREATE DATABASE stock_cursor CHARACTER SET utf8mb4 COLLATE utf8mb4_unicode_ci')
        print('✅ 数据库创建成功')
    else:
        print('✅ 数据库连接成功')
    
    conn.close()
except Exception as e:
    print(f'❌ 数据库连接失败: {e}')
    print('请确保MySQL服务已启动，并检查.env文件中的数据库配置')
    exit 1
"

# 检查Redis连接
echo "🔍 检查Redis连接..."
python3 -c "
import redis
import os
from dotenv import load_dotenv

load_dotenv()

try:
    r = redis.Redis(
        host=os.getenv('REDIS_HOST', 'localhost'),
        port=int(os.getenv('REDIS_PORT', 6379)),
        db=int(os.getenv('REDIS_DB', 0)),
        decode_responses=True
    )
    r.ping()
    print('✅ Redis连接成功')
except Exception as e:
    print(f'⚠️ Redis连接失败: {e}')
    print('Redis服务未启动，缓存功能将不可用')
"

echo ""
echo "🎉 系统准备就绪！"
echo ""
echo "📝 启动命令:"
echo "   python run.py"
echo ""
echo "🌐 访问地址:"
echo "   http://localhost:5000"
echo ""
echo "📚 API文档:"
echo "   http://localhost:5000/api/stocks"
echo ""

# 询问是否立即启动
read -p "是否立即启动应用？(y/n): " -n 1 -r
echo
if [[ $REPLY =~ ^[Yy]$ ]]; then
    echo "🚀 启动应用..."
    python run.py
fi 