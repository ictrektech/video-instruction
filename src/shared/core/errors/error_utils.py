import traceback
from pathlib import Path


def exc_origin(exc: BaseException):
    """
    获取异常发生点（raise 位置）的文件名和行号。
    失败时返回 (None, None)。
    """
    tb = exc.__traceback__
    if not tb:
        return None, None
    frames = traceback.extract_tb(tb)
    if not frames:
        return None, None
    last = frames[-1]  # raise 点
    last_path = Path(last.filename)
    parts = last_path.parts
    filename = "/".join(parts[-2:]) or last.filename
    return filename, last.lineno
