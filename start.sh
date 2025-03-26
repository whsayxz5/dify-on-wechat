#!/bin/bash

# 设置脚本遇到错误时终止执行
set -e

# 彩色输出函数
print_green() {
    echo -e "\033[32m$1\033[0m"
}

print_blue() {
    echo -e "\033[34m$1\033[0m"
}

print_yellow() {
    echo -e "\033[33m$1\033[0m"
}

print_red() {
    echo -e "\033[31m$1\033[0m"
}

# 标题
clear
print_blue "============================================"
print_blue "       Dify-on-WeChat 启动脚本"
print_blue "============================================"
echo ""

# 检查是否已存在 config.json，如果不存在，则从模板创建
if [ ! -f "config.json" ]; then
    print_yellow "未找到 config.json，将从模板创建..."
    cp config-template.json config.json
    print_yellow "请编辑 config.json 文件，配置必要的参数后再启动服务。"
    exit 1
fi

# 确保必要的目录存在
mkdir -p logs
mkdir -p tmp
mkdir -p plugins

# 确保日志目录权限正确
chmod -R 755 logs 2>/dev/null || true

# 清理端口函数
cleanup_ports() {
    print_blue "检查并清理端口..."
    
    # 清理7860端口
    if lsof -i:7860 > /dev/null 2>&1; then
        print_yellow "发现端口7860被占用，正在尝试释放..."
        lsof -ti:7860 | xargs kill -9 2>/dev/null || print_red "无法释放端口7860，可能需要手动终止进程"
    fi
    
    # 清理9919端口
    if lsof -i:9919 > /dev/null 2>&1; then
        print_yellow "发现端口9919被占用，正在尝试释放..."
        lsof -ti:9919 | xargs kill -9 2>/dev/null || print_red "无法释放端口9919，可能需要手动终止进程"
    fi
}

# 检查本地Python环境
check_python_env() {
    print_blue "检查Python环境..."
    if ! command -v python3 &> /dev/null; then
        print_red "错误: 未检测到 Python3。请先安装 Python3: https://www.python.org/downloads/"
        exit 1
    fi

    # 检查依赖
    print_blue "检查项目依赖..."
    if ! python3 -c "import psutil" &> /dev/null; then
        print_yellow "安装必要的依赖 psutil..."
        pip3 install psutil
    fi

    # 检查其他依赖
    if [ ! -f "requirements.txt" ]; then
        print_red "错误: 未找到 requirements.txt 文件"
        exit 1
    fi

    # 检查是否已安装依赖
    if ! python3 -c "import flask" &> /dev/null; then
        print_yellow "安装项目依赖..."
        pip3 install -r requirements.txt
        if [ -f "requirements-optional.txt" ]; then
            pip3 install -r requirements-optional.txt
        fi
    fi
}

# 前台启动函数
start_local_foreground() {
    print_green "前台模式启动 dify-on-wechat 服务..."
    cleanup_ports
    check_python_env
    python3 admin_ui.py
}

# 后台启动函数
start_local_background() {
    print_green "后台模式启动 dify-on-wechat 服务..."
    cleanup_ports
    check_python_env
    nohup python3 admin_ui.py > logs/admin_ui.log 2>&1 &
    print_green "服务已在后台启动，管理面板地址: http://localhost:7860"
    print_green "查看日志: tail -f logs/admin_ui.log"
}

# Docker重新构建启动函数
start_docker_rebuild() {
    print_green "Docker模式(重新构建)启动 dify-on-wechat 服务..."
    cleanup_ports
    
    # 检查 Docker 是否安装
    if ! command -v docker &> /dev/null; then
        print_red "错误: 未检测到 Docker。请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    # 检查 Docker Compose 是否安装
    if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null; then
        print_red "错误: 未检测到 Docker Compose。请先安装 Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    print_blue "正在重新构建Docker镜像..."
    if command -v docker-compose &> /dev/null; then
        docker-compose build
        docker-compose up -d
    else
        docker compose build
        docker compose up -d
    fi
    
    print_green "服务已启动，管理面板地址: http://localhost:7860"
    print_green "用户名和密码可在 config.json 中或 docker-compose.yml 环境变量中配置"
    print_green "查看日志: docker-compose logs -f dify-on-wechat"
}

# Docker使用现有镜像启动函数
start_docker_existing() {
    print_green "Docker模式(使用现有镜像)启动 dify-on-wechat 服务..."
    cleanup_ports
    
    # 检查 Docker 是否安装
    if ! command -v docker &> /dev/null; then
        print_red "错误: 未检测到 Docker。请先安装 Docker: https://docs.docker.com/get-docker/"
        exit 1
    fi

    # 检查 Docker Compose 是否安装
    if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null; then
        print_red "错误: 未检测到 Docker Compose。请先安装 Docker Compose: https://docs.docker.com/compose/install/"
        exit 1
    fi
    
    # 检查镜像是否存在
    echo "检查 dify-on-wechat:local 镜像是否存在..."
    if ! docker images | grep -q "dify-on-wechat" | grep -q "local"; then
        print_yellow "本地镜像不存在，将改为重新构建..."
        start_docker_rebuild
        return
    fi
    
    # 启动服务
    print_blue "正在启动 Docker 容器..."
    if command -v docker-compose &> /dev/null; then
        docker-compose up -d
    else
        docker compose up -d
    fi
    
    print_green "服务已启动，管理面板地址: http://localhost:7860"
    print_green "用户名和密码可在 config.json 中或 docker-compose.yml 环境变量中配置"
    print_green "查看日志: docker-compose logs -f dify-on-wechat"
}

# 停止服务函数
stop_service() {
    print_blue "正在停止所有服务..."
    
    # 停止本地运行的admin_ui.py进程
    if ps -ef | grep admin_ui.py | grep -v grep > /dev/null; then
        print_yellow "停止本地运行的进程..."
        ps -ef | grep admin_ui.py | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || print_red "没有运行中的admin_ui.py进程"
    fi
    
    # 如果docker-compose可用，尝试停止docker服务
    if command -v docker-compose &> /dev/null; then
        print_yellow "停止Docker容器..."
        docker-compose down 2>/dev/null || print_yellow "没有运行中的docker容器"
    elif command -v docker &> /dev/null && command -v docker compose &> /dev/null; then
        print_yellow "停止Docker容器..."
        docker compose down 2>/dev/null || print_yellow "没有运行中的docker容器"
    fi

    print_green "所有dify-on-wechat服务已停止"
}

# 查看日志函数
view_logs() {
    print_blue "查看日志文件"
    echo ""
    
    echo "可用日志文件:"
    ls -l logs/*.log 2>/dev/null | awk '{print NR, $9}' || echo "暂无日志文件"
    echo ""
    
    read -p "请输入要查看的日志序号 (默认: 1): " log_num
    log_num=${log_num:-1}
    
    read -p "显示最后多少行 (默认: 50): " lines
    lines=${lines:-50}
    
    log_file=$(ls -1 logs/*.log 2>/dev/null | sed -n "${log_num}p")
    
    if [ -z "$log_file" ]; then
        print_red "未找到日志文件或序号无效"
        return
    fi
    
    print_blue "正在查看 $log_file 的最后 $lines 行..."
    tail -f "$log_file" -n $lines
}

# 检查Docker是否可用
DOCKER_AVAILABLE=0
if command -v docker &> /dev/null; then
    DOCKER_AVAILABLE=1
    print_green "检测到Docker已安装"
else
    print_yellow "未检测到Docker，Docker启动模式将不可用"
fi

# 主菜单
print_blue "请选择启动模式:"
echo "1. 本地启动 (前台运行) [默认]"
echo "2. 本地启动 (后台运行)"
if [ $DOCKER_AVAILABLE -eq 1 ]; then
    echo "3. Docker启动 (使用现有镜像)"
    echo "4. Docker启动 (重新构建镜像)"
fi
echo "5. 停止所有服务"
echo "6. 查看日志"
echo "0. 退出"
echo ""

read -p "请输入选项 [0-6] (默认: 1): " choice
choice=${choice:-1}

case $choice in
    1)
        start_local_foreground
        ;;
    2)
        start_local_background
        ;;
    3)
        if [ $DOCKER_AVAILABLE -eq 1 ]; then
            start_docker_existing
        else
            print_red "Docker未安装，无法使用此选项"
            exit 1
        fi
        ;;
    4)
        if [ $DOCKER_AVAILABLE -eq 1 ]; then
            start_docker_rebuild
        else
            print_red "Docker未安装，无法使用此选项"
            exit 1
        fi
        ;;
    5)
        stop_service
        ;;
    6)
        view_logs
        ;;
    0)
        print_blue "退出脚本"
        exit 0
        ;;
    *)
        print_red "无效选项，请输入0-6之间的数字"
        exit 1
        ;;
esac 