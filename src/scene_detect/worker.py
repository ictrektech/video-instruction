"""scene-detect worker CLI — 启动 Huey Consumer 处理 scene-detect 任务。

用法：
    uv run python -m scene_detect.worker [--workers 4]
"""

from __future__ import annotations

from shared.jobs import run_worker


def main() -> None:
    run_worker("scene-detect")
