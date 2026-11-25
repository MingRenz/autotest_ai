import logging
import sys
from logging.handlers import RotatingFileHandler

from utils.paths import LOG_DIR

_FILE_FORMAT = "%(asctime)s | %(levelname)s | %(name)s | %(message)s"
_CONSOLE_FORMAT = "%(levelname)s | %(message)s"
_DATE_FORMAT = "%Y-%m-%d %H:%M:%S"

# 这些 logger 默认 propagate=False，需要显式挂载报告采集 handler。
LOGGER_NAMES = ("http", "fixtures", "rate_limit")


class AllureLogHandler(logging.Handler):
    """按测试用例收集自定义 logger 日志，由 conftest fixture 负责挂载/卸载。"""

    def __init__(self):
        super().__init__()
        self.lines = []
        self.setFormatter(logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT))

    def emit(self, record: logging.LogRecord) -> None:
        try:
            self.lines.append(self.format(record))
        except Exception:
            self.handleError(record)

    def text(self) -> str:
        return "\n".join(self.lines)


def get_logger(name: str = "api") -> logging.Logger:
    """返回文件 + stdout 双通道 logger；重复调用不会重复挂 handler。"""
    logger = logging.getLogger(name)
    if logger.handlers:
        return logger

    logger.setLevel(logging.INFO)
    logger.propagate = False

    file_handler = RotatingFileHandler(
        LOG_DIR / "framework.log",
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    file_handler.setFormatter(
        logging.Formatter(_FILE_FORMAT, datefmt=_DATE_FORMAT)
    )

    # 显式指定 stdout，避免 Allure 把正常 INFO 日志归入 stderr。
    console_handler = logging.StreamHandler(sys.stdout)
    console_handler.setFormatter(
        logging.Formatter(_CONSOLE_FORMAT, datefmt=_DATE_FORMAT)
    )

    logger.addHandler(file_handler)
    logger.addHandler(console_handler)
    return logger
