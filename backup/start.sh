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
mkdir -p plugins

# 确保日志目录权限正确
chmod -R 755 logs 2>/dev/null || true

# 检查 Docker 是否安装
if ! command -v docker &> /dev/null; then
    echo "错误: 未检测到 Docker。请先安装 Docker: https://docs.docker.com/get-docker/"
    exit 1
fi

# 检查 Docker Compose 是否安装
if ! command -v docker-compose &> /dev/null && ! command -v docker compose &> /dev/null; then
    echo "错误: 未检测到 Docker Compose。请先安装 Docker Compose: https://docs.docker.com/compose/install/"
    exit 1
fi

# 检查镜像是否存在
echo "检查 dify-on-wechat:local 镜像是否存在..."
if ! docker images | grep -q "dify-on-wechat" | grep -q "local"; then
    echo "本地镜像不存在，正在构建..."
    docker-compose build
fi

# 启动服务
echo "正在启动 dify-on-wechat 服务..."
if command -v docker-compose &> /dev/null; then
    docker-compose up -d
else
    docker compose up -d
fi

# 显示服务状态
echo "服务已启动，管理面板地址: http://localhost:7860"
echo "用户名和密码可在 config.json 中或 docker-compose.yml 环境变量中配置"
echo "查看日志: docker-compose logs -f dify-on-wechat"

