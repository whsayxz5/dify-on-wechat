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
    print_blue "检查端口使用情况..."
    
    # 检查是否在Docker容器内运行
    if [ -f "/.dockerenv" ]; then
        print_yellow "检测到Docker环境，跳过端口清理以避免容器崩溃"
        return 0
    fi
    
    # 检查是否有docker容器在使用端口
    print_blue "检查Docker容器端口使用情况..."
    DOCKER_CONTAINERS_USING_7860=$(docker ps --format "{{.Names}}" 2>/dev/null | xargs -I {} sh -c "docker port {} 2>/dev/null | grep -q '7860' && echo {}" | xargs)
    DOCKER_CONTAINERS_USING_9919=$(docker ps --format "{{.Names}}" 2>/dev/null | xargs -I {} sh -c "docker port {} 2>/dev/null | grep -q '9919' && echo {}" | xargs)
    
    # 处理7860端口
    if lsof -i:7860 > /dev/null 2>&1; then
        print_yellow "发现端口7860被占用，显示占用进程信息:"
        lsof -i:7860 -n
        
        if [ ! -z "$DOCKER_CONTAINERS_USING_7860" ]; then
            print_yellow "警告: 端口7860被Docker容器使用 ($DOCKER_CONTAINERS_USING_7860)"
            print_yellow "建议先手动停止Docker容器: docker stop $DOCKER_CONTAINERS_USING_7860"
            print_yellow "或使用docker-compose down命令停止所有相关容器"
            
            read -p "是否尝试强制终止端口占用进程? (y/n，不推荐): " force_kill_7860
            if [[ "$force_kill_7860" == "y" || "$force_kill_7860" == "Y" ]]; then
                print_red "警告: 强制终止Docker容器进程可能导致容器异常!"
                lsof -ti:7860 | xargs kill -9 2>/dev/null && print_green "已强制终止端口7860进程" || print_red "无法释放端口7860，请手动处理"
            fi
        else
            print_yellow "端口7860被非Docker进程占用，正在终止..."
            # 获取占用端口的PID
            PORT_7860_PIDS=$(lsof -ti:7860)
            for pid in $PORT_7860_PIDS; do
                # 获取进程命令
                CMD=$(ps -p $pid -o command= 2>/dev/null || echo "未知命令")
                CMDNAME=$(ps -p $pid -o comm= 2>/dev/null || echo "未知")
                
                print_yellow "终止PID为 $pid 的进程 ($CMDNAME): $CMD"
                
                # 先尝试使用SIGTERM优雅终止
                kill -15 $pid 2>/dev/null
                sleep 1
                
                # 检查进程是否仍然存在
                if ps -p $pid > /dev/null 2>&1; then
                    print_yellow "进程 $pid 未能优雅终止，使用SIGKILL强制终止..."
                    kill -9 $pid 2>/dev/null && print_green "已终止进程 $pid" || print_red "无法终止进程 $pid，请手动检查"
                else
                    print_green "已优雅终止进程 $pid"
                fi
            done
        fi
    else
        print_green "端口7860未被占用"
    fi
    
    # 处理9919端口
    if lsof -i:9919 > /dev/null 2>&1; then
        print_yellow "发现端口9919被占用，显示占用进程信息:"
        lsof -i:9919 -n
        
        if [ ! -z "$DOCKER_CONTAINERS_USING_9919" ]; then
            print_yellow "警告: 端口9919被Docker容器使用 ($DOCKER_CONTAINERS_USING_9919)"
            print_yellow "建议先手动停止Docker容器: docker stop $DOCKER_CONTAINERS_USING_9919"
            print_yellow "或使用docker-compose down命令停止所有相关容器"
            
            read -p "是否尝试强制终止端口占用进程? (y/n，不推荐): " force_kill_9919
            if [[ "$force_kill_9919" == "y" || "$force_kill_9919" == "Y" ]]; then
                print_red "警告: 强制终止Docker容器进程可能导致容器异常!"
                lsof -ti:9919 | xargs kill -9 2>/dev/null && print_green "已强制终止端口9919进程" || print_red "无法释放端口9919，请手动处理"
            fi
        else
            print_yellow "端口9919被非Docker进程占用，正在终止..."
            # 获取占用端口的PID
            PORT_9919_PIDS=$(lsof -ti:9919)
            for pid in $PORT_9919_PIDS; do
                # 获取进程命令
                CMD=$(ps -p $pid -o command= 2>/dev/null || echo "未知命令")
                CMDNAME=$(ps -p $pid -o comm= 2>/dev/null || echo "未知")
                
                print_yellow "终止PID为 $pid 的进程 ($CMDNAME): $CMD"
                
                # 先尝试使用SIGTERM优雅终止
                kill -15 $pid 2>/dev/null
                sleep 1
                
                # 检查进程是否仍然存在
                if ps -p $pid > /dev/null 2>&1; then
                    print_yellow "进程 $pid 未能优雅终止，使用SIGKILL强制终止..."
                    kill -9 $pid 2>/dev/null && print_green "已终止进程 $pid" || print_red "无法终止进程 $pid，请手动检查"
                else
                    print_green "已优雅终止进程 $pid"
                fi
            done
        fi
    else
        print_green "端口9919未被占用"
    fi
    
    # 最终检查端口状态
    sleep 1
    if lsof -i:7860 > /dev/null 2>&1 || lsof -i:9919 > /dev/null 2>&1; then
        print_yellow "警告：仍有端口被占用，可能影响服务启动"
        if lsof -i:7860 > /dev/null 2>&1; then
            print_yellow "端口7860仍被占用："
            lsof -i:7860 -n
        fi
        if lsof -i:9919 > /dev/null 2>&1; then
            print_yellow "端口9919仍被占用："
            lsof -i:9919 -n
        fi
        read -p "是否继续? (y/n): " continue_with_ports_used
        if [[ "$continue_with_ports_used" != "y" && "$continue_with_ports_used" != "Y" ]]; then
            print_red "操作取消，请手动释放端口后重试"
            exit 1
        fi
    else
        print_green "所有端口已成功释放"
    fi
}

# 安装依赖函数
install_dependencies() {
    local force=$1
    
    print_blue "检查Python环境..."
    if ! command -v python3 &> /dev/null; then
        print_red "错误: 未检测到 Python3。请先安装 Python3: https://www.python.org/downloads/"
        exit 1
    fi

    # 检查依赖
    print_blue "检查项目依赖..."
    
    # 检查其他依赖
    if [ ! -f "requirements.txt" ]; then
        print_red "错误: 未找到 requirements.txt 文件"
        exit 1
    fi
    
    # 强制重新安装依赖或检查是否已安装
    if [ "$force" = "true" ]; then
        print_yellow "强制重新安装所有依赖..."
        pip3 install -r requirements.txt --upgrade
        if [ -f "requirements-optional.txt" ]; then
            pip3 install -r requirements-optional.txt --upgrade
        fi
    elif ! python3 -c "import flask" &> /dev/null; then
        print_yellow "安装项目依赖..."
        pip3 install -r requirements.txt
        if [ -f "requirements-optional.txt" ]; then
            pip3 install -r requirements-optional.txt
        fi
    else
        print_green "依赖检查完成"
    fi
}

# 检查本地Python环境
check_python_env() {
    local force=$1
    install_dependencies "$force"
}

# 询问是否强制安装依赖
ask_reinstall_deps() {
    print_blue "是否需要强制重新安装所有依赖？(适用于首次安装或出现依赖问题时)"
    echo "1. 不需要 [默认]"
    echo "2. 需要"
    echo ""
    read -p "请选择 [1/2]: " reinstall_deps
    reinstall_deps=${reinstall_deps:-1}

    if [ "$reinstall_deps" = "2" ]; then
        FORCE_REINSTALL=true
        print_yellow "将强制重新安装所有依赖..."
    else
        FORCE_REINSTALL=false
    fi
    
    return 0
}

# 前台启动函数
start_local_foreground() {
    print_green "准备前台模式启动 dify-on-wechat 服务..."
    
    # 询问是否强制安装依赖
    ask_reinstall_deps
    
    cleanup_ports
    check_python_env "$FORCE_REINSTALL"
    print_green "前台模式启动 dify-on-wechat 服务..."
    python3 admin_ui.py
}

# 后台启动函数
start_local_background() {
    print_green "准备后台模式启动 dify-on-wechat 服务..."
    
    # 询问是否强制安装依赖
    ask_reinstall_deps
    
    cleanup_ports
    check_python_env "$FORCE_REINSTALL"
    print_green "后台模式启动 dify-on-wechat 服务..."
    nohup python3 admin_ui.py > logs/admin_ui.log 2>&1 &
    print_green "服务已在后台启动，管理面板地址: http://localhost:7860"
    print_green "查看日志: tail -f logs/admin_ui.log"
}

# Docker重新构建启动函数
start_docker_rebuild() {
    print_green "Docker模式(重新构建)启动 dify-on-wechat 服务..."
    
    # 检查是否有已有容器在运行
    if command -v docker-compose &> /dev/null; then
        CONTAINERS=$(docker-compose ps -q 2>/dev/null)
    else
        CONTAINERS=$(docker compose ps -q 2>/dev/null)
    fi
    
    if [ ! -z "$CONTAINERS" ]; then
        print_yellow "发现已运行的dify-on-wechat容器，先停止它们..."
        if command -v docker-compose &> /dev/null; then
            docker-compose down
        else
            docker compose down
        fi
        # 等待容器完全停止
        sleep 3
    fi
    
    # 在Docker操作前检查端口
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
    
    # 检查是否有已有容器在运行
    if command -v docker-compose &> /dev/null; then
        CONTAINERS=$(docker-compose ps -q 2>/dev/null)
    else
        CONTAINERS=$(docker compose ps -q 2>/dev/null)
    fi
    
    if [ ! -z "$CONTAINERS" ]; then
        print_yellow "发现已运行的dify-on-wechat容器，先停止它们..."
        if command -v docker-compose &> /dev/null; then
            docker-compose down
        else
            docker compose down
        fi
        # 等待容器完全停止
        sleep 3
    fi
    
    # 在Docker操作前检查端口
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
    print_blue "检查 dify-on-wechat:local 镜像是否存在..."
    
    # 使用精确匹配且提供更多信息
    IMAGE_INFO=$(docker images dify-on-wechat:local --format "{{.Repository}}:{{.Tag}} (创建于 {{.CreatedSince}})" 2>/dev/null)
    
    if [ -z "$IMAGE_INFO" ]; then
        print_yellow "本地镜像 dify-on-wechat:local 不存在，将改为重新构建..."
        start_docker_rebuild
        return
    else
        print_green "找到本地镜像: $IMAGE_INFO"
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
    print_blue "正在停止服务..."
    
    # 获取当前脚本所在目录的绝对路径
    SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
    print_blue "当前目录: ${SCRIPT_DIR}"
    
    # 检查是否在Docker容器内运行
    if [ -f "/.dockerenv" ]; then
        print_yellow "检测到Docker环境，推荐从容器外部使用docker-compose down命令停止服务"
        print_yellow "在容器内直接停止服务可能会导致容器崩溃"
        read -p "是否继续? (y/n): " confirm
        if [[ "$confirm" != "y" && "$confirm" != "Y" ]]; then
            print_blue "取消操作"
            return 0
        fi
    fi
    
    # 检查是否有docker容器在使用这些端口
    print_blue "检查Docker容器端口使用情况..."
    DOCKER_CONTAINERS_USING_7860=$(docker ps --format "{{.Names}}" 2>/dev/null | xargs -I {} sh -c "docker port {} 2>/dev/null | grep -q '7860' && echo {}" | xargs)
    DOCKER_CONTAINERS_USING_9919=$(docker ps --format "{{.Names}}" 2>/dev/null | xargs -I {} sh -c "docker port {} 2>/dev/null | grep -q '9919' && echo {}" | xargs)
    
    # 如果docker-compose可用，尝试优先停止docker服务（仅限当前目录）
    if [ -f "${SCRIPT_DIR}/docker-compose.yml" ]; then
        print_blue "检测到docker-compose.yml，尝试停止Docker容器..."
        
        if command -v docker-compose &> /dev/null; then
            cd "${SCRIPT_DIR}" && docker-compose ps 2>/dev/null
            if cd "${SCRIPT_DIR}" && docker-compose down 2>/dev/null; then
                print_green "已停止Docker容器，继续检查本地进程"
            else
                print_yellow "没有运行中的docker容器或停止失败，继续检查本地进程"
            fi
        elif command -v docker &> /dev/null && command -v docker compose &> /dev/null; then
            cd "${SCRIPT_DIR}" && docker compose ps 2>/dev/null
            if cd "${SCRIPT_DIR}" && docker compose down 2>/dev/null; then
                print_green "已停止Docker容器，继续检查本地进程"
            else
                print_yellow "没有运行中的docker容器或停止失败，继续检查本地进程"
            fi
        fi
    else
        print_yellow "未找到docker-compose.yml，跳过Docker容器清理"
    fi
    
    # 停止本地运行的admin_ui.py和Bot.py进程
    print_blue "查找并停止本程序相关进程..."
    
    # 直接查找占用7860和9919端口的进程并终止，这是最可靠的方法
    print_blue "检查并终止占用7860和9919端口的进程..."
    
    # 处理7860端口
    if lsof -i:7860 > /dev/null 2>&1; then
        print_yellow "发现7860端口被占用，显示占用进程信息:"
        lsof -i:7860 -n
        
        # 检查是否被Docker使用
        if [ ! -z "$DOCKER_CONTAINERS_USING_7860" ]; then
            print_yellow "警告：端口7860被Docker容器使用 ($DOCKER_CONTAINERS_USING_7860)"
            print_yellow "请使用docker stop $DOCKER_CONTAINERS_USING_7860 或docker-compose down命令停止服务"
            print_yellow "强制终止可能导致容器崩溃，跳过此端口处理"
        else
            # 获取占用端口的PID
            PORT_7860_PIDS=$(lsof -ti:7860)
            for pid in $PORT_7860_PIDS; do
                # 获取进程命令
                CMD=$(ps -p $pid -o command= 2>/dev/null || echo "未知命令")
                CMDNAME=$(ps -p $pid -o comm= 2>/dev/null || echo "未知")
                
                print_yellow "正在终止PID为 $pid 的进程 ($CMDNAME), 命令行: $CMD"
                
                # 先尝试使用SIGTERM优雅终止
                kill -15 $pid 2>/dev/null
                sleep 1
                
                # 检查进程是否仍然存在
                if ps -p $pid > /dev/null 2>&1; then
                    print_yellow "进程 $pid 未能优雅终止，使用SIGKILL强制终止..."
                    kill -9 $pid 2>/dev/null && print_green "已终止进程 $pid" || print_red "无法终止进程 $pid，请手动检查"
                else
                    print_green "已优雅终止进程 $pid"
                fi
            done
        fi
    else
        print_green "端口7860未被占用"
    fi
    
    # 处理9919端口
    if lsof -i:9919 > /dev/null 2>&1; then
        print_yellow "发现9919端口被占用，显示占用进程信息:"
        lsof -i:9919 -n
        
        # 检查是否被Docker使用
        if [ ! -z "$DOCKER_CONTAINERS_USING_9919" ]; then
            print_yellow "警告：端口9919被Docker容器使用 ($DOCKER_CONTAINERS_USING_9919)"
            print_yellow "请使用docker stop $DOCKER_CONTAINERS_USING_9919 或docker-compose down命令停止服务"
            print_yellow "强制终止可能导致容器崩溃，跳过此端口处理"
        else
            # 获取占用端口的PID
            PORT_9919_PIDS=$(lsof -ti:9919)
            for pid in $PORT_9919_PIDS; do
                # 获取进程命令
                CMD=$(ps -p $pid -o command= 2>/dev/null || echo "未知命令")
                CMDNAME=$(ps -p $pid -o comm= 2>/dev/null || echo "未知")
                
                print_yellow "正在终止PID为 $pid 的进程 ($CMDNAME), 命令行: $CMD"
                
                # 先尝试使用SIGTERM优雅终止
                kill -15 $pid 2>/dev/null
                sleep 1
                
                # 检查进程是否仍然存在
                if ps -p $pid > /dev/null 2>&1; then
                    print_yellow "进程 $pid 未能优雅终止，使用SIGKILL强制终止..."
                    kill -9 $pid 2>/dev/null && print_green "已终止进程 $pid" || print_red "无法终止进程 $pid，请手动检查"
                else
                    print_green "已优雅终止进程 $pid"
                fi
            done
        fi
    else
        print_green "端口9919未被占用"
    fi
    
    # 特别查找并终止admin_ui.py和Bot.py进程
    print_blue "查找并终止admin_ui.py和Bot.py进程..."
    
    # 使用多种方式查找进程，提高匹配成功率
    ADMIN_UI_PIDS=$(ps -ef | grep -E "python3.*admin_ui\.py" | grep -v grep | awk '{print $2}')
    BOT_PIDS=$(ps -ef | grep -E "python3.*Bot\.py" | grep -v grep | awk '{print $2}')
    
    # 处理admin_ui.py进程
    if [ ! -z "$ADMIN_UI_PIDS" ]; then
        for pid in $ADMIN_UI_PIDS; do
            CMD=$(ps -p $pid -o command= 2>/dev/null || echo "未知命令")
            print_yellow "找到admin_ui.py进程: PID=$pid, 命令: $CMD"
            
            # 终止进程
            print_yellow "正在终止admin_ui.py进程 $pid..."
            kill -15 $pid 2>/dev/null
            sleep 1
            
            # 检查进程是否仍然存在
            if ps -p $pid > /dev/null 2>&1; then
                print_yellow "进程 $pid 未能优雅终止，使用SIGKILL强制终止..."
                kill -9 $pid 2>/dev/null && print_green "已终止admin_ui.py进程 $pid" || print_red "无法终止进程 $pid，请手动检查"
            else
                print_green "已终止admin_ui.py进程 $pid"
            fi
        done
    else
        print_green "未找到admin_ui.py进程"
    fi
    
    # 处理Bot.py进程
    if [ ! -z "$BOT_PIDS" ]; then
        for pid in $BOT_PIDS; do
            CMD=$(ps -p $pid -o command= 2>/dev/null || echo "未知命令")
            print_yellow "找到Bot.py进程: PID=$pid, 命令: $CMD"
            
            # 终止进程
            print_yellow "正在终止Bot.py进程 $pid..."
            kill -15 $pid 2>/dev/null
            sleep 1
            
            # 检查进程是否仍然存在
            if ps -p $pid > /dev/null 2>&1; then
                print_yellow "进程 $pid 未能优雅终止，使用SIGKILL强制终止..."
                kill -9 $pid 2>/dev/null && print_green "已终止Bot.py进程 $pid" || print_red "无法终止进程 $pid，请手动检查"
            else
                print_green "已终止Bot.py进程 $pid"
            fi
        done
    else
        print_green "未找到Bot.py进程"
    fi
    
    # 最终检查端口
    sleep 2
    print_blue "最终检查端口状态..."
    PORT_7860_STILL_USED=$(lsof -i:7860 2>/dev/null)
    PORT_9919_STILL_USED=$(lsof -i:9919 2>/dev/null)
    
    if [ ! -z "$PORT_7860_STILL_USED" ]; then
        print_red "警告: 端口7860仍被占用:"
        echo "$PORT_7860_STILL_USED"
        print_yellow "尝试强制释放端口7860..."
        lsof -ti:7860 | xargs kill -9 2>/dev/null || print_red "无法释放端口7860，请手动处理"
    else
        print_green "端口7860已成功释放"
    fi
    
    if [ ! -z "$PORT_9919_STILL_USED" ]; then
        print_red "警告: 端口9919仍被占用:"
        echo "$PORT_9919_STILL_USED"
        print_yellow "尝试强制释放端口9919..."
        lsof -ti:9919 | xargs kill -9 2>/dev/null || print_red "无法释放端口9919，请手动处理"
    else
        print_green "端口9919已成功释放"
    fi
    
    print_green "已完成停止服务操作"
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