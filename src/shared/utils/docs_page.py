"""内置前端文档页面（供 VOS 应用 iframe 嵌入）。

页面源文件位于 ``shared/static/integration.html``，随包分发；
两个服务（scene-detect / structure）均通过 ``mount_docs()`` 在 ``/doc``
路径下提供，Traefik 的 ``/app/com.ictrek.video-structure`` 前缀剥掉后即落到这里。
"""

from __future__ import annotations

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_docs(application: FastAPI) -> None:
    """在应用上挂载 ``/doc`` 静态文档路由（``GET /doc/integration.html``）。

    使用 ``check_dir=False``：文档页是附属能力，静态目录缺失时应返回 404，
    而不是在应用启动阶段抛异常导致整个服务起不来。
    """
    static_dir = Path(__file__).resolve().parent.parent / "static"
    application.mount(
        "/doc",
        StaticFiles(directory=str(static_dir), check_dir=False),
        name="docs",
    )
