"""Application entry point for `serve` command."""


def main() -> None:
    import uvicorn

    from app.core.logging import get_log_config
    from app.core.settings import settings

    uvicorn.run(
        "app.main:app",
        host="localhost",
        port=settings.app_port,
        log_config=get_log_config(),
        access_log=True,
        reload=settings.app_env == "dev",
    )


if __name__ == "__main__":
    main()
