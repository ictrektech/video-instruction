import logging

from shared.core.request_context import get_request_id


class ExceptionOriginFilter(logging.Filter):
    """异常来源过滤器。

    将日志记录的 source_file 和 source_line 属性设置为记录的 filename 和 lineno（若未预先设置）。

    Args:
        logging (module): 标准库 logging 模块。
    """

    def filter(self, record: logging.LogRecord):
        record.source_file = getattr(record, "source_file", record.filename)
        record.source_line = getattr(record, "source_line", record.lineno)
        return True


class RequestIdFilter(logging.Filter):
    """Request ID 过滤器。

    将日志记录的 request_id 属性设置为当前请求上下文中的 request_id（若未预先设置）。
    """

    def filter(self, record: logging.LogRecord):
        record.request_id = getattr(record, "request_id", get_request_id() or "-")
        return True


class RoleFilter(logging.Filter):
    """进程角色过滤器。

    为日志记录补充角色标识（api / worker），formatter 引用 %(role)s 时
    不会因缺失字段报错。角色由 configure_logging 按进程注入。
    """

    def __init__(self, role: str = "api"):
        super().__init__()
        self.role = role

    def filter(self, record: logging.LogRecord) -> bool:
        record.role = self.role
        return True


class AccessLogDefaultsFilter(logging.Filter):
    """Access log 默认字段过滤器。

    允许 access formatter 直接引用结构化字段而不会因缺失字段导致格式化报错。
    """

    def filter(self, record: logging.LogRecord) -> bool:
        record.client_addr = getattr(record, "client_addr", "-")
        record.request_line = getattr(record, "request_line", "-")
        record.status_code = getattr(record, "status_code", 0)
        record.status_phrase = getattr(record, "status_phrase", "-")
        record.duration_ms = getattr(record, "duration_ms", 0.0)
        return True
