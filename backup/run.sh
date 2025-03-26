#!/bin/bash
set -e

echo "Dify-on-WeChat 启动脚本"
echo "======================="

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
mkdir -p plugins

# 确保日志目录权限正确
chmod -R 755 logs 2>/dev/null || true

# 检查Docker是否可用
DOCKER_AVAILABLE=0
if command -v docker &> /dev/null; then
    DOCKER_AVAILABLE=1
    echo "检测到Docker已安装"
else
    echo "未检测到Docker，将使用本地模式运行"
fi

# 询问用户选择运行模式
if [ $DOCKER_AVAILABLE -eq 1 ]; then
    echo ""
    echo "请选择运行模式:"
    echo "1. 本地模式 (使用本地Python环境)"
    echo "2. Docker模式 (使用Docker容器)"
    echo ""
    read -p "请输入选项 [1/2] (默认: 1): " choice
    
    if [ "$choice" = "2" ]; then
        echo "选择Docker模式运行..."
        ./start.sh
        exit 0
    else
        echo "选择本地模式运行..."
    fi
fi

# 本地模式运行
echo "检查Python环境..."
if ! command -v python3 &> /dev/null; then
    echo "错误: 未检测到 Python3。请先安装 Python3。"
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

# 询问是否后台运行
echo ""
echo "请选择运行方式:"
echo "1. 前台运行 (可以看到实时日志，关闭终端会停止服务)"
echo "2. 后台运行 (关闭终端不会停止服务，可使用 ./stop.sh 停止)"
echo ""
read -p "请输入选项 [1/2] (默认: 1): " run_mode

if [ "$run_mode" = "2" ]; then
    echo "后台模式启动 dify-on-wechat 服务..."
    nohup python3 admin_ui.py > logs/admin_ui.log 2>&1 &
    echo "服务已在后台启动，管理面板地址: http://localhost:7860"
    echo "查看日志: tail -f logs/admin_ui.log"
else
    echo "前台模式启动 dify-on-wechat 服务..."
    python3 admin_ui.py
fi 