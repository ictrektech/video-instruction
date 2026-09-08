# 基镜像可参数化：国内构建机建议先把 python:3.13-slim 按架构镜像到 SWR
# （参考 image-studio docker/mirror_base_images.sh），构建时传入
#   --build-arg PYTHON_BASE_IMAGE=${REGISTRY}/python:${arch}_3.13-slim
# 并配合 build_image.sh 的 --pull=false，构建过程不触碰 Docker Hub
ARG PYTHON_BASE_IMAGE=python:3.13-slim
FROM ${PYTHON_BASE_IMAGE}

# Use Tsinghua mirror for apt (faster in CN, fallback for DNS issues)
RUN sed -i \
    -e 's|http://deb.debian.org/debian$|https://mirrors.tuna.tsinghua.edu.cn/debian|' \
    -e 's|http://deb.debian.org/debian-security$|https://mirrors.tuna.tsinghua.edu.cn/debian-security|' \
    /etc/apt/sources.list.d/debian.sources 2>/dev/null || true

RUN apt-get update && apt-get install -y --no-install-recommends \
    libgl1 \
    libglib2.0-0t64 \
    libxcb1 \
    ffmpeg \
    && rm -rf /var/lib/apt/lists/*

COPY --from=ghcr.io/astral-sh/uv:latest /uv /uvx /bin/

WORKDIR /app

# Use Tsinghua mirror for uv (PyPI proxy, essential for sophon/CN networks)
ENV UV_INDEX_URL=https://pypi.tuna.tsinghua.edu.cn/simple/
ENV UV_INDEX_PRIORITY=always

# Install dependencies first (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY src/ src/
COPY config/ config/
COPY README.md ./
# 单镜像：同时包含 scene-detect 与 structure 两套运行时（两者依赖相同）。
# 部署时两个容器共用本镜像，仅通过 command（scene-detect / structure）与 APP_PORT 区分，
# 因此本文件不设 ENTRYPOINT/CMD——启动命令由 compose 的 command 提供。
RUN uv sync --frozen --no-dev --extra scene-detect --extra structure

ENV PATH="/app/.venv/bin:$PATH"

# 8910 = scene-detect，8911 = structure；实际监听端口由容器 APP_PORT 决定
EXPOSE 8910 8911
