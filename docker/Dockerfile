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

# 固定 uv 版本：用 latest 时上游一发版就会改变 digest，
# 导致本层之后（含最贵的依赖安装）全部缓存失效
COPY --from=ghcr.io/astral-sh/uv:0.11.8 /uv /uvx /bin/

WORKDIR /app

# PyPI 镜像源固化在 pyproject.toml 的 [[tool.uv.index]]（清华源）：
# uv sync --frozen 按 uv.lock 里记录的 URL 下载，仅设 UV_INDEX_URL 环境变量
ENV PYTHONUNBUFFERED=1

# Install dependencies first (layer caching)
# cache mount：依赖变化时复用已下载的包，避免整层重建时重新拉取
# 第三方依赖（含两个 extras）全部在这一层装完，改代码时不会重装；
COPY pyproject.toml uv.lock ./
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra scene-detect --extra structure --no-install-project

# Copy application code
# 版本文件与代码一起拷贝：它只在项目安装（下一层）时读取，
# 不参与上面的依赖层，因此发版 bump 版本不会击穿依赖缓存
COPY src/ src/
COPY config/ config/
COPY README.md ./
COPY ictrek.app/VERSION ictrek.app/VERSION
# 单镜像：同时包含 scene-detect 与 structure 两套运行时（两者依赖相同）。
# 部署时两个容器共用本镜像，仅通过 command（scene-detect / structure）与 APP_PORT 区分，
# 因此本文件不设 ENTRYPOINT/CMD——启动命令由 compose 的 command 提供。
# 这一层只装本地项目（editable）并生成 console script；依赖已在上层就位，属秒级操作。
# extras 必须重复声明：uv sync 会把环境收敛到"请求集合"，省略会卸载掉上层装的 extras。
# --reinstall-package：避免命中 uv 缓存里的旧构建产物，保证装进去的是当前版本
RUN --mount=type=cache,target=/root/.cache/uv \
    uv sync --frozen --no-dev --extra scene-detect --extra structure \
    --reinstall-package video-instruction

ENV PATH="/app/.venv/bin:$PATH"

# 8910 = scene-detect，8911 = structure；实际监听端口由容器 APP_PORT 决定
EXPOSE 8910 8911
