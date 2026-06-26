# 开发规范

## 目录

- [项目结构](#项目结构)
- [新增资源 —— 黄金路径](#新增资源--黄金路径)
- [各层规范](#各层规范)
- [错误处理](#错误处理)
- [测试](#测试)
- [日志](#日志)

---

## 项目结构

```
src/app/
├── api/
│   ├── routes.py              # 路由注册中心
│   ├── deps/                  # 依赖注入（认证等）
│   └── endpoints/             # 路由处理器
├── core/
│   ├── settings/              # 配置（pydantic-settings）
│   ├── security/              # JWT、密码
│   ├── errors/                # 错误码、异常定义
│   ├── logging/               # 日志配置
│   └── request_context.py     # 请求上下文
├── db/
│   └── session.py             # 数据库引擎、会话
├── models/                    # SQLModel ORM 模型
├── schemas/                   # 请求/响应 DTO
├── services/                  # 业务逻辑层
├── crud/                      # 数据访问层
├── middlewares/               # 中间件注册
└── infrastructure/            # 基础设施外部服务
```

---

## 新增资源 —— 黄金路径

以新增 `resume` 资源为例，按以下顺序添加：

### 1. Model — `src/app/models/resume.py`

```python
from datetime import datetime
from sqlmodel import Field, SQLModel
from app.models.mixins.base import BaseMixin


class Resume(BaseMixin, table=True):
    __tablename__ = "sys_resume"  # type: ignore[reportAssignmentType]

    id: int | None = Field(default=None, primary_key=True)
    user_id: int = Field(index=True, description="用户 ID")
    title: str = Field(max_length=200, description="简历标题")
    content: str | None = Field(default=None, description="简历内容")
    status: int = Field(default=1, description="状态：1=启用 0=禁用")
```

**规则：**
- 必须继承 `BaseMixin`（自动获得 `create_time`、`update_time`、`deleted`）
- 设置 `table=True`
- 显式指定 `__tablename__`，前缀 `sys_`
- `id` 字段固定写法：`id: int | None = Field(default=None, primary_key=True)`
- 每个字段加 `description=`

然后在 `src/app/models/__init__.py` 中导出：

```python
from app.models.resume import Resume
```

### 2. Schema — `src/app/schemas/resume.py`

```python
from pydantic import BaseModel, Field


class CreateResumeCommand(BaseModel):
    title: str = Field(description="简历标题", min_length=1, max_length=200)
    content: str | None = Field(default=None, description="简历内容")

class ResumeDTO(BaseModel):
    id: int = Field(description="简历 ID")
    title: str = Field(description="简历标题")
    content: str | None = Field(default=None, description="简历内容")
```

**命名规则：**
- `*Command` — 传入 service 层的命令（输入）
- `*DTO` — 返回给客户端的数据（输出）

### 3. CRUD — `src/app/crud/resume.py`

```python
from sqlmodel import col, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models.resume import Resume


async def get_resume_by_id(session: AsyncSession, resume_id: int) -> Resume | None:
    result = await session.execute(select(Resume).where(col(Resume.id) == resume_id))
    return result.scalar_one_or_none()

async def create_resume(session: AsyncSession, resume: Resume) -> Resume:
    session.add(resume)
    await session.commit()
    await session.refresh(resume)
    return resume
```

**规则：**
- 模块级函数，非类方法
- 首参固定为 `session: AsyncSession`
- 查询返回 `Model | None`，创建返回 `Model`
- 在 `src/app/crud/__init__.py` 中导出

### 4. Service — `src/app/services/resume_service.py`

```python
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.errors.error_codes import BusinessErrorCode
from app.core.errors.exceptions import ApiException
from app.crud.resume import create_resume, get_resume_by_id
from app.models.resume import Resume
from app.schemas.resume import CreateResumeCommand, ResumeDTO


async def create(session: AsyncSession, cmd: CreateResumeCommand) -> ResumeDTO:
    resume = Resume(
        user_id=1,  # 从当前用户获取
        title=cmd.title,
        content=cmd.content,
    )
    resume = await create_resume(session, resume)
    if resume.id is None:
        raise ApiException(BusinessErrorCode.ADD_USER_FAILED)
    return ResumeDTO(id=resume.id, title=resume.title, content=resume.content)


async def get(session: AsyncSession, resume_id: int) -> ResumeDTO:
    resume = await get_resume_by_id(session, resume_id)
    if not resume:
        raise ApiException(BusinessErrorCode.COMMON_OBJECT_NOT_FOUND, "简历", str(resume_id))
    return ResumeDTO(id=resume.id, title=resume.title, content=resume.content)
```

**规则：**
- 每个 service 为一个独立的模块级函数
- 签名为 `async def action(session: AsyncSession, cmd: *Command) -> *DTO`
- 业务异常直接 `raise ApiException(...)`，不 try-catch
- endpoint 中通过模块引用调用（如 `resume_service.create(session, cmd)`）

### 5. Endpoint — `src/app/api/endpoints/resume.py`

```python
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps.auth import get_current_user
from app.db.session import get_session
from app.schemas.common.response import ResponseDTO
from app.schemas.resume import CreateResumeCommand, ResumeDTO
from app.services import resume_service


router = APIRouter()


@router.post("/create", response_model=ResponseDTO[ResumeDTO])
async def create_resume(
    command: CreateResumeCommand,
    session: AsyncSession = Depends(get_session),
    current_user: ... = Depends(get_current_user),
) -> ResponseDTO[ResumeDTO]:
    dto = await resume_service.create(session, command)
    return ResponseDTO.ok(dto)
```

**规则：**
- 创建 `router = APIRouter()` — 不在此处加 prefix/tag
- 通过模块导入 service 函数：`from app.services import xxx_service`
- `response_model` 和返回类型统一使用 `ResponseDTO[*DTO]`
- 成功返回 `ResponseDTO.ok(dto)`

### 6. 注册路由 — `src/app/api/routes.py`

```python
api_router.include_router(resume.router, prefix="/resume", tags=["resume"])
```

**规则：** prefix 和 tags 在 `routes.py` 集中指定，不在 endpoint 模块中指定。

### 7. 数据迁移

```bash
uv run alembic revision --autogenerate -m "add resume table"
uv run alembic upgrade head
```

---

## 各层规范

### Model

| 要求 | 说明 |
|------|------|
| 基类 | 必须继承 `BaseMixin` |
| `table=True` | 必须设置 |
| `__tablename__` | 显式指定，格式 `sys_<表名>` |
| 主键 | `id: int \| None = Field(default=None, primary_key=True)` |
| 索引 | 频繁查询字段加 `index=True` |
| 描述 | 每个字段加 `description=` |

**自动填充字段**（由 `db/session.py` 的 `before_flush` 事件自动处理）：

| 字段 | 说明 |
|------|------|
| `create_time` | 新增时自动设置 |
| `update_time` | 新增和更新时自动设置 |
| `deleted` | 默认为 `False`（软删除标记） |

### Schema

| 类型 | 后缀 | 用途 |
|------|------|------|
| 输入命令 | `*Command` | 客户端传入的原始请求字段，传给 service |
| 输出数据 | `*DTO` | 返回给客户端的数据对象 |
| 认证用户 | `CurrentUser` | 由 auth 依赖注入返回 |

### CRUD

- **模块级函数**（非类），统一首参 `session: AsyncSession`
- 查询风格：`select(Model).where(col(Model.field) == value)`
- 创建三件套：`session.add()` → `await session.commit()` → `await session.refresh()`
- 所有函数在 `src/app/crud/__init__.py` 中 re-export

### Service

- **模块级函数**（非类），和 CRUD 层保持一致
- 函数签名：`async def action(session: AsyncSession, cmd: *Command) -> *DTO`
- 业务异常用 `raise ApiException(BusinessErrorCode.*)` 上报
- 不直接在 service 中处理 HTTP 或 DB 会话生命周期

### Endpoint

- 每个资源一个独立 `.py` 文件
- `router = APIRouter()` — 仅创建 bare router
- 通过模块 import service：`from app.services import xxx_service`
- prefix 和 tags 在 `routes.py` 中指定
- `response_model` 和返回类型注解都用 `ResponseDTO[*DTO]`
- 调用 service 时通过模块限定：`await xxx_service.action(session, cmd)`
- state-mutating 操作用 `@router.post`，只读操作用 `@router.get`

---

## 错误处理

### 错误码定义

`src/app/core/errors/error_codes.py`：

```python
class BusinessErrorCode(ErrorCodeMixin):
    COMMON_OBJECT_NOT_FOUND = (10001, "找不到ID为 {} 的 {}")
    USERNAME_EXISTS = (20101, "用户名已存在")
    # 新增：CONTENT_NOT_FOUND = (30101, "找不到ID为 {} 的 {}")
```

- 系统级错误码放在 `ErrorCode`，业务级放在 `BusinessErrorCode`
- 错误码 = `(int_code, str_message)`，message 可用 `{}` 占位

### 抛出异常

```python
raise ApiException(BusinessErrorCode.COMMON_OBJECT_NOT_FOUND, "资源名", str(id))
```

异常会自动被 `error_handler` 捕获，返回 HTTP 200 + `ResponseDTO.fail(code=err.code, msg=err.message)`。

---

## 测试

### 单元测试

```python
class TestResume:
    def test_create_resume_dto(self) -> None:
        dto = ResumeDTO(id=1, title="My Resume", content="...")
        assert dto.title == "My Resume"
```

- 类命名 `Test*`，方法命名 `test_*`
- 单元测试不标记 `@pytest.mark.integration`

### 集成测试

```python
@pytest.mark.integration
class TestResumeAPI:
    async def test_create_resume(self) -> None:
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            resp = await client.post("/api/resume/create", json={...})
        assert resp.status_code == 200
```

- 标记 `@pytest.mark.integration`（运行：`pytest -m integration`）
- 跳过集成测试：`pytest -m "not integration"`
- 使用 `httpx.AsyncClient` + `ASGITransport`

---

## 日志

### Logger 命名

```python
from logging import getLogger

logger = getLogger(__name__)  # 格式: app.<module>
```

- HTTP 访问日志使用专用 logger：`getLogger("app.access")`
- 不要用 `print()`（ruff 规则 `T20` 会拦截）

### 日志配置

日志格式在 `config/log_conf.yaml` 中定义，支持三个 formatter：
- **default**：带 Rich 高亮的控制台输出 `[request_id] [file:line] | message`
- **access**：结构化访问日志
- **file**：标准文件日志（RotatingFileHandler，10MB，保留 5 份）
