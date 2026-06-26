from enum import Enum


class ErrorCodeMixin(Enum):
    """错误码混入类，提供统一的 code/message 属性。"""

    @property
    def code(self) -> int:
        return self.value[0]

    @property
    def message(self) -> str:
        return self.value[1]


class ErrorCode(ErrorCodeMixin):
    SUCCESS = (0, "操作成功")
    FAILED = (99999, "操作失败")
    EXTERNAL_SERVICE_ERROR = (10000, "外部服务调用失败：{}")


class BusinessErrorCode(ErrorCodeMixin):
    COMMON_OBJECT_NOT_FOUND = (10001, "找不到ID为 {} 的 {}")
    COMMON_UNSUPPORTED_OPERATION = (10002, "不支持的操作")
    COMMON_BULK_DELETE_IDS_IS_INVALID = (10003, "批量参数ID列表为空")
    USERNAME_EXISTS = (20101, "用户名已存在")
    ADD_USER_FAILED = (20102, "新增用户失败")
    USER_NOT_FOUND = (20103, "找不到的用户{}")
    RATE_LIMIT_EXCEEDED = (60001, "请求频率过快，请稍后再试")
