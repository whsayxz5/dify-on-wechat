FROM python:3.10-slim-bullseye

LABEL maintainer="dify-on-wechat"
ARG TZ='Asia/Shanghai'

ENV BUILD_PREFIX=/app
ENV PYTHONUNBUFFERED=1

WORKDIR ${BUILD_PREFIX}

# 复制项目文件
COPY . ${BUILD_PREFIX}

# 安装系统依赖和编译工具
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        bash \
        ffmpeg \
        espeak \
        libavcodec-extra \
        gcc \
        g++ \
        make \
        curl \
    && cd ${BUILD_PREFIX} \
    && cp config-template.json config.json \
    && /usr/local/bin/python -m pip install --no-cache --upgrade pip \
    && pip install --no-cache -r requirements.txt \
    && pip install --no-cache -r requirements-optional.txt \
    # 清理编译工具和缓存
    && apt-get remove -y gcc g++ make \
    && apt-get autoremove -y \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/* \
    && rm -rf ~/.cache/pip/*

# 暴露必要的端口
EXPOSE 7860 9919

# 设置默认启动命令为admin_ui.py
CMD ["python", "admin_ui.py"]
