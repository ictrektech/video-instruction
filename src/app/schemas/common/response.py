from typing import TypeVar

from pydantic import BaseModel, Field

from app.core.errors.error_codes import ErrorCode

T = TypeVar("T")


class ResponseDTO[T](BaseModel):
    code: int = Field(description="响应码")
    msg: str = Field(description="响应消息")
    data: T | None = Field(default=None, description="响应数据")

    @classmethod
    def ok(cls, data: T | None = None) -> "ResponseDTO[T]":
        return cls(code=ErrorCode.SUCCESS.code, msg=ErrorCode.SUCCESS.message, data=data)

    @classmethod
    def fail(cls, code: int, msg: str, data: T | None = None) -> "ResponseDTO[T]":
        return cls(code=code, msg=msg, data=data)
