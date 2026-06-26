from __future__ import annotations

from logging.config import dictConfig
from pathlib import Path
from typing import Any

import yaml

from app.core.settings import settings


def get_log_config(path: str | Path | None = None) -> dict[str, Any]:
    # 优先使用 settings 中的配置路径
    config_path = Path(path) if path else Path(settings.log_config_path)
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    level = settings.log_level.upper()
    if "root" in config:
        config["root"]["level"] = level
    for name in ("uvicorn.error", "uvicorn.access"):
        if name in config.get("loggers", {}):
            config["loggers"][name]["level"] = level
    # 确保日志目录存在（给文件 handler 用）
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    return config


def configure_logging(path: str | Path | None = None) -> None:
    dictConfig(get_log_config(path))
