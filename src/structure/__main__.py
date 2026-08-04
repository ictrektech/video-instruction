"""Application entry point for `structure` command."""

from shared.utils.system import limit_opencv_threads


def main() -> None:
    limit_opencv_threads()

    import uvicorn

    from shared.core.logging import get_log_config
    from structure.core.settings import settings

    uvicorn.run(
        "structure.main:app",
        host="0.0.0.0",  # noqa: S104 — uvicorn dev server, container-bound
        port=settings.app_port,
        log_config=get_log_config(
            level=settings.log_level,
            path=settings.log_config_path,
        ),
        access_log=True,
        reload=settings.app_env == "dev",
        # 只监听 src/
        reload_dirs=["src"],
    )


if __name__ == "__main__":
    main()
