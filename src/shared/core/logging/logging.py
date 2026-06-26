from __future__ import annotations

from logging.config import dictConfig
from pathlib import Path
from typing import Any

import yaml


def get_log_config(
    level: str | None = None,
    path: str | Path | None = None,
) -> dict[str, Any]:
    config_path = Path(path) if path else Path("config/log_conf.yaml")
    with config_path.open("r", encoding="utf-8") as file:
        config = yaml.safe_load(file) or {}
    level = (level or "INFO").upper()
    if "root" in config:
        config["root"]["level"] = level
    for name in ("uvicorn.error", "uvicorn.access"):
        if name in config.get("loggers", {}):
            config["loggers"][name]["level"] = level
    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    return config


def configure_logging(
    level: str | None = None,
    path: str | Path | None = None,
) -> None:
    dictConfig(get_log_config(level, path))
