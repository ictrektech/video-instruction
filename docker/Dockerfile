FROM python:3.13-slim

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

# Build arg: service name → install only that service's extra deps
ARG SERVICE=all

# Install dependencies first (layer caching)
COPY pyproject.toml uv.lock ./
RUN uv sync --frozen --no-dev --no-install-project

# Copy application code
COPY src/ src/
COPY config/ config/
COPY README.md ./
# Install service-specific extras (or all if SERVICE=all)
RUN if [ "$SERVICE" = "all" ]; then \
      uv sync --frozen --no-dev --all-extras; \
    else \
      uv sync --frozen --no-dev --extra "$SERVICE"; \
    fi

ENV PATH="/app/.venv/bin:$PATH"

EXPOSE 8910
