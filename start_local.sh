#!/bin/bash
set -e

# 检查是否已存在 config.json，如果不存在，则从模板创建
if [ ! -f "config.json" ]; then
    echo "未找到 config.json，将从模板创建..."
    cp config-template.json config.json
    echo "请编辑 config.json 文件，配置必要的参数后再启动服务。"
    exit 1
fi

# 确保必要的目录存在
mkdir -p logs
mkdir -p tmp

# 确保日志目录权限正确
chmod -R 755 logs 2>/dev/null || true

# 检查Python是否安装
if ! command -v python3 &> /dev/null; then
    echo "错误: 未检测到 Python3。请先安装 Python3: https://www.python.org/downloads/"
    exit 1
fi

# 检查依赖
echo "检查项目依赖..."
if ! python3 -c "import psutil" &> /dev/null; then
    echo "安装必要的依赖 psutil..."
    pip3 install psutil
fi

# 检查其他依赖
if [ ! -f "requirements.txt" ]; then
    echo "错误: 未找到 requirements.txt 文件"
    exit 1
fi

# 检查是否已安装依赖
if ! python3 -c "import flask" &> /dev/null; then
    echo "安装项目依赖..."
    pip3 install -r requirements.txt
    if [ -f "requirements-optional.txt" ]; then
        pip3 install -r requirements-optional.txt
    fi
fi

# 启动服务
echo "正在启动 dify-on-wechat 服务..."
python3 admin_ui.py

# 注：此脚本会在前台运行服务，终端关闭后服务会停止
# 如需后台运行，可使用 nohup python3 admin_ui.py > logs/admin_ui.log 2>&1 & 