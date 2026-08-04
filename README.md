# video-instruction

> 🚀 **GitHub Template** — 点击 "Use this template" 即可创建新项目。
>
> 首次克隆后运行以下命令初始化（将自动重命名项目）：
> ```bash
> bash scripts/init-project.sh
> ```

`video-instruction` 提供两个面向视频理解的 FastAPI 服务：

- `scene-detection`：视频场景切分，默认监听 `8910`。
- `structure`：视频结构化与场景描述，默认监听 `8911`。

项目使用 Python 3.13、FastAPI、uv、FFmpeg / ffprobe，并通过 Docker Compose 提供开发和生产部署。

## 目录

- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [服务说明](#服务说明)
- [配置](#配置)
- [命令](#命令)
- [部署](#部署)
- [项目结构](#项目结构)
- [测试](#测试)

## 技术栈

- **框架**: FastAPI
- **包管理**: uv
- **配置**: pydantic-settings
- **任务状态**: SQLite + Huey 封装
- **视频处理**: FFmpeg / ffprobe、PySceneDetect
- **图像处理**: Pillow、NumPy
- **大模型调用**: OpenAI 兼容 `/v1` API
- **构建**: Hatchling
- **代码质量**: Ruff、pytest、pre-commit

## 快速开始

### 前置条件

- Docker & Docker Compose
- 或本地安装 Python 3.13、uv、FFmpeg / ffprobe

### Docker 开发

```bash
# 按本机照片库路径调整 docker/.env.dev 里的 UPLOAD_LOCATION
make dev OPTS=-d

# 查看日志
make dev-logs

# 停止
make dev-down
```

开发 compose 会启动 `scene-detection` 和 `structure`，并把源码挂载进容器，便于调试和快速验证。

开发模式特性：

- 源码、测试、配置和日志目录通过 volume 挂载。
- `debugpy` 已安装在开发镜像中，便于远程调试。
- 两个服务各自使用独立 `.venv` 卷，避免依赖环境互相污染。
- `UPLOAD_LOCATION` 下的 `photos` 目录会以只读方式挂载到容器内 `/photos`。

### 本地运行

```bash
uv sync

# 场景切分服务
uv run scene-detect

# 视频结构化服务
uv run structure
```

本地默认端口：

| 服务 | 地址 |
|------|------|
| `scene-detection` | `http://localhost:8910` |
| `structure` | `http://localhost:8911` |

## 服务说明

### scene-detection

场景切分服务读取视频文件，输出场景边界、时间范围和基础元数据。生产镜像为：

```text
swr.cn-southwest-2.myhuaweicloud.com/ictrek/video-instruction-detection:${IMAGE_TAG:-latest}
```

### structure

结构化服务读取视频文件和场景信息，抽帧生成九宫格图，并调用兼容 OpenAI `/v1` 的多模态模型生成场景描述。生产镜像为：

```text
swr.cn-southwest-2.myhuaweicloud.com/ictrek/video-instruction-structure:${IMAGE_TAG:-latest}
```

## 配置

常用环境变量：

| 变量 | 默认值 | 说明 |
|------|--------|------|
| `IMAGE_TAG` | `latest` | 镜像标签 |
| `SCENE_DETECTION_PORT` | `8910` | 场景切分服务宿主机端口 |
| `STRUCTURE_PORT` | `8911` | 结构化服务宿主机端口 |
| `UPLOAD_LOCATION` | 见 `docker/.env.*` | 本仓库独立 compose 使用的照片库根目录，服务内挂载为 `/photos` |
| `TASK_MAX_CONCURRENCY` | `2` | 单服务任务最大并发 |
| `TASK_QUEUE_LIMIT` | `20` | 任务队列长度限制 |
| `LLM_BASE_URL` | `http://10.144.144.232:21436/v1` | 结构化服务调用的大模型 API 地址 |
| `LLM_API_KEY` | `sk-fake` | 大模型 API Key |
| `LLM_MODEL_NAME` | `minicpm-v:latest` | 大模型名称 |
| `LLM_MAX_CONCURRENCY` | `20` | 场景描述并发数 |

## 命令

| 命令 | 说明 |
|------|------|
| `make dev` | 启动开发栈，加 `OPTS=-d` 后台运行 |
| `make dev-down` | 停止开发栈 |
| `make dev-logs` | 查看开发日志 |
| `make dev-build` | 构建开发镜像 |
| `make dev-ps` | 查看开发服务状态 |
| `make build` | 构建生产镜像，并打平台版本标签 |
| `make tag` | 将当前构建版本标记为 `latest-$(PLATFORM)` |
| `make push` | 推送版本标签和平台 latest 标签 |
| `make prod` | 启动本仓库生产栈，加 `OPTS=-d` 后台运行 |
| `make prod-down` | 停止生产栈 |
| `make prod-logs` | 查看生产日志 |
| `uv run pytest` | 运行所有测试 |
| `uv run pytest -m "not integration"` | 运行非集成测试 |
| `uv run pytest -m integration` | 运行集成测试 |
| `uv run ruff check` | 代码检查 |
| `uv run ruff format` | 代码格式化 |
| `uv run pre-commit run --all-files` | 运行 pre-commit 检查 |

## 部署

### 构建镜像

```bash
# 构建并打版本标签
make build

# 推送版本标签和平台 latest 标签
make push
```

### 独立生产部署

本仓库生产 compose 位于 `docker/docker-compose.yml`：

```bash
# 按环境调整 docker/.env.prod
make prod OPTS=-d
```

独立部署时，视频资源通过 `UPLOAD_LOCATION` 挂载到容器内 `/photos`。

## 项目结构

```text
.
├── config/
│   └── log_conf.yaml           # 日志配置
├── .github/
│   └── workflows/ci.yml        # CI：Ruff 和 pytest
├── .dockerignore
├── .pre-commit-config.yaml
├── data/                       # 本地任务状态与运行数据
├── docker/
│   ├── Dockerfile              # 生产镜像
│   ├── Dockerfile.dev          # 开发镜像
│   ├── docker-compose.yml      # 生产编排
│   ├── docker-compose.dev.yml  # 开发编排
│   └── docker-compose.test.yml # 测试编排
├── docs/                       # API 文档和设计说明
├── log/                        # 本地日志输出
├── scripts/                    # 项目辅助脚本
├── src/
│   ├── scene_detect/           # 场景切分服务
│   │   ├── api/                # 路由与接口入口
│   │   ├── core/               # 服务配置
│   │   ├── schemas/            # 请求/响应模型
│   │   ├── services/           # 场景检测与任务逻辑
│   │   ├── __main__.py         # `uv run scene-detect` 入口
│   │   └── worker.py           # 场景切分 worker 入口
│   ├── structure/              # 视频结构化服务
│   │   ├── api/                # 路由与接口入口
│   │   ├── core/               # 服务配置
│   │   ├── schemas/            # 结构化、描述与任务模型
│   │   ├── services/           # 抽帧、缓存、LLM 与结构化逻辑
│   │   ├── __main__.py         # `uv run structure` 入口
│   │   └── worker.py           # 结构化 worker 入口
│   └── shared/                 # 共享响应、任务、回调、日志与工具
│       ├── core/               # ffprobe、日志、请求上下文等
│       ├── jobs/               # Huey 任务队列封装
│       ├── middlewares/        # 通用中间件
│       ├── schemas/            # 通用 DTO
│       └── utils/              # 通用工具
├── tests/                      # 测试
│   ├── scene_detect/
│   ├── shared/
│   └── structure/
├── uv.lock
├── Makefile
└── pyproject.toml
```

## 测试

```bash
# 运行所有测试
uv run pytest

# 代码检查
uv run ruff check
```
