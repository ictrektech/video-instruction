# video-structure

> 🚀 **GitHub Template** — 点击 "Use this template" 即可创建新项目。
>
> 首次克隆后运行以下命令初始化（将自动重命名项目）：
> ```bash
> bash scripts/init-project.sh
> ```

## 目录

- [技术栈](#技术栈)
- [快速开始](#快速开始)
- [项目结构](#项目结构)
- [开发规范](#开发规范)
- [命令](#命令)
- [测试](#测试)
- [部署](#部署)

---

video-structure - 视频结构化服务：场景检测 + 九宫格抽帧 + 可选 VLM 场景描述，
基于 Python 3.13 + FastAPI，任务队列用 Huey（SQLite），视频解码依赖 ffmpeg/ffprobe。

## 技术栈

- **框架**: FastAPI + uvicorn
- **配置**: pydantic-settings
- **任务队列**: Huey（SQLite 存储，服务内嵌 worker）
- **场景检测**: PySceneDetect（extra `scene-detect`，ffmpeg 解码 + OpenCV）
- **结构化抽帧**: ffmpeg + Pillow / numpy（extra `structure`）
- **场景描述**: OpenAI 兼容接口调用 VLM（可选）
- **包管理**: uv（astral-sh）
- **构建**: Hatchling

## 快速开始

### 前置条件

- Docker & Docker Compose（推荐，一键启动全部依赖）
- 或本地安装 Python 3.13、PostgreSQL 18、Redis 7

### 方式一：Docker 开发（推荐）

```bash
# 复制环境配置
cp src/.example.env src/.env

# 启动开发栈（PostgreSQL + Redis + 应用）
make dev OPTS=-d

# 查看日志
make dev-logs

# 停止
make dev-down
```

开发模式特性：
- 源码通过 volume 挂载，修改即生效（uvicorn --reload）
- debugpy 远程调试端口 `5678`
- PostgreSQL 暴露端口 `6432`，Redis 暴露端口 `6380`
- 独立的 `.venv` 卷，避免跨平台兼容问题

### 方式二：本地开发

```bash
# 安装依赖
uv sync

# 复制环境配置并修改数据库连接地址
cp src/.example.env src/.env

# 启动服务（自动 reload）
uv run serve
```

服务默认运行在 `http://localhost:8910`，API 文档在 `http://localhost:8910/docs`。

## 项目结构

```
.
├── docs/                       # 开发文档
│   └── development-guide.md    # 开发规范
├── src/
│   ├── main.py                 # ASGI 入口（供 uvicorn 直接使用）
│   └── app/
│       ├── __main__.py         # `uv run serve` / `CMD ["serve"]` 入口
│       ├── main.py             # FastAPI 应用工厂
│       ├── api/
│       │   ├── routes.py       # 路由注册
│       │   ├── deps/           # 依赖注入（认证等）
│       │   └── endpoints/      # 路由处理器
│       ├── core/
│       │   ├── settings/       # 配置管理（pydantic-settings）
│       │   ├── security/       # JWT、密码加密
│       │   ├── errors/         # 异常定义与错误码
│       │   ├── logging/        # 日志配置（YAML + filters）
│       │   └── request_context.py
│       ├── db/                 # 数据库会话与初始化
│       ├── models/             # SQLModel 数据模型
│       ├── schemas/            # 请求/响应 DTO
│       ├── services/           # 业务逻辑层
│       ├── crud/               # 数据访问层
│       ├── middlewares/        # 中间件（限流、错误处理、上下文）
│       ├── infrastructure/     # Redis 客户端、令牌桶限流
│       └── utils/              # 工具函数
├── config/
│   └── log_conf.yaml           # 日志配置
├── docker/
│   ├── Dockerfile              # 生产镜像（多阶段构建）
│   ├── Dockerfile.dev          # 开发镜像（debugpy + dev 依赖）
│   ├── docker-compose.yml      # 生产编排
│   └── docker-compose.dev.yml  # 开发编排（profiles 模式）
├── alembic/                    # 数据库迁移
├── tests/                      # 测试
├── .dockerignore
├── .example.env
├── Makefile
├── pyproject.toml
└── .github/workflows/          # CI/CD
```

## 开发规范

参考 [docs/development-guide.md](docs/development-guide.md)，涵盖：

- **新增资源的黄金路径**：Model → Schema → CRUD → Service → Endpoint → Route
- **各层规范**：Model、Schema、CRUD、Service、Endpoint 的约定
- **错误处理**：错误码定义、`ApiException` 用法
- **测试与日志**：测试分类、logger 命名

## 命令

### 开发命令

| 命令 | 说明 |
|------|------|
| `uv run serve` | 启动服务（热重载） |
| `uv run pytest` | 运行测试 |
| `uv run pytest -m "not integration"` | 仅运行单元测试 |
| `uv run pytest -m integration` | 运行集成测试 |
| `uv run ruff check` | 代码检查 |
| `uv run ruff format` | 代码格式化 |
| `uv run alembic upgrade head` | 执行数据库迁移 |
| `uv run pre-commit run --all-files` | 运行 pre-commit 检查 |

### Makefile 命令

| 命令 | 说明 |
|------|------|
| `make dev` | 启动开发栈（加 `OPTS=-d` 后台运行） |
| `make dev-down` | 停止开发栈 |
| `make dev-logs` | 查看开发日志 |
| `make dev-build` | 构建开发镜像 |
| `make dev-ps` | 查看开发服务状态 |
| `make dev-reset` | 重置开发栈（清数据重建） |
| `make build` | 构建生产镜像 |
| `make prod` | 启动生产栈 |
| `make prod-down` | 停止生产栈 |
| `make prod-logs` | 查看生产日志 |

## 测试

```bash
# 运行所有测试
uv run pytest

# 仅运行单元测试（不依赖 PostgreSQL/Redis）
uv run pytest -m "not integration"

# 运行集成测试
uv run pytest -m integration
```

## 部署

### 构建镜像

```bash
# 构建并打版本标签
make build

# 推送至 registry（需先配置 REGISTRY）
make push
```

### 生产部署

```bash
# 启动生产栈
make prod OPTS=-d

# 查看日志
make prod-logs
```

> **注意**: 镜像仓库地址默认为 `registry.example.com`，使用前需在 `Makefile` 中修改 `REGISTRY` 变量。正式环境建议配置外部 PostgreSQL 和 Redis，而非使用容器内的服务。
