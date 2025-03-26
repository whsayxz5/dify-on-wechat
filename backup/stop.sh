#!/bin/bash

# 停止本地运行的admin_ui.py进程
ps -ef | grep admin_ui.py | grep -v grep | awk '{print $2}' | xargs kill -9 2>/dev/null || echo "没有运行中的admin_ui.py进程"

# 如果docker-compose可用，尝试停止docker服务
if command -v docker-compose &> /dev/null; then
    docker-compose down 2>/dev/null || echo "没有运行中的docker容器"
elif command -v docker &> /dev/null && command -v docker compose &> /dev/null; then
    docker compose down 2>/dev/null || echo "没有运行中的docker容器"
fi

echo "所有dify-on-wechat服务已停止"

