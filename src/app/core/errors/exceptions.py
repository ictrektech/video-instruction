from typing import Any

from app.core.errors.error_codes import ErrorCodeMixin


class ApiException(Exception):
    def __init__(self, error_code: ErrorCodeMixin, *args: Any) -> None:
        self.error_code = error_code
        self.args_data = args
        super().__init__(self.message)

    @property
    def code(self) -> int:
        return self.error_code.code

    @property
    def message(self) -> str:
        if self.args_data:
            return self.error_code.message.format(*self.args_data)
        return self.error_code.message
