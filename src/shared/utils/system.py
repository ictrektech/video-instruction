"""系统级工具函数（OpenMP 线程限制等）。"""

from __future__ import annotations

import os


def limit_opencv_threads() -> None:
    """限制 OpenCV/OpenMP 线程池，避免因 OpenCV 默认多线程策略创建数百个空闲线程。

    在进程入口尽早调用；setdefault 不会覆盖已设的环境变量。
    """
    os.environ.setdefault("OMP_NUM_THREADS", "1")
    os.environ.setdefault("OPENCV_OPENMP_NUM_THREADS", "1")
    try:
        import cv2

        cv2.setNumThreads(1)
    except ImportError:
        pass
