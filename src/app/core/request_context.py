from contextvars import ContextVar

request_id: ContextVar[str | None] = ContextVar("request_id", default=None)
request_user_id: ContextVar[int | None] = ContextVar("request_user_id", default=None)
request_username: ContextVar[str | None] = ContextVar("request_username", default=None)


def set_request_id(value: str | None) -> None:
    request_id.set(value)


def get_request_id() -> str | None:
    return request_id.get()


def clear_request_id() -> None:
    request_id.set(None)


def set_request_user(user_id: int | None, username: str | None) -> None:
    request_user_id.set(user_id)
    request_username.set(username)


def get_request_user_id() -> int | None:
    return request_user_id.get()


def get_request_username() -> str | None:
    return request_username.get()


def clear_request_user() -> None:
    request_user_id.set(None)
    request_username.set(None)
