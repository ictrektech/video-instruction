from __future__ import annotations

from logging.config import dictConfig
from pathlib import Path
from typing import Any

import yaml

# 文件 handler 的角色化文件名：一进程一文件，
# 避免 RotatingFileHandler 多进程共写导致的轮转竞态
_ROLE_LOG_FILENAME = {"api": "log/server.log", "worker": "log/worker.log"}


def get_log_config(
    level: str | None = None,
    path: str | Path | None = None,
    role: str = "api",
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

    # 进程角色由 dictConfig 注入的 role filter 提供（声明见 log_conf.yaml），
    # 这里只重载其取值与文件名：worker 写 log/worker.log
    config["filters"]["role"]["role"] = role
    file_handler = config.get("handlers", {}).get("server_file")
    if file_handler is not None:
        file_handler["filename"] = _ROLE_LOG_FILENAME.get(role, _ROLE_LOG_FILENAME["api"])

    log_dir = Path("log")
    log_dir.mkdir(exist_ok=True)
    return config


def configure_logging(
    level: str | None = None,
    path: str | Path | None = None,
    role: str = "api",
) -> None:
    dictConfig(get_log_config(level, path, role))
