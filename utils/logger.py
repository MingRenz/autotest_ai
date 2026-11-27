import logging
import sys
from logging.handlers import RotatingFileHandler

from utils.paths import LOG_DIR


def get_logger(name: str = "api") -> logging.Logger:
    """同一组日志共用文件和控制台 handler。"""
    logger = logging.getLogger("autotest")
    if not logger.handlers:
        logger.setLevel(logging.INFO)
        logger.propagate = False

        file_handler = RotatingFileHandler(
            LOG_DIR / "framework.log",
            maxBytes=5 * 1024 * 1024,
            backupCount=3,
            encoding="utf-8",
            delay=True,
        )
        file_handler.setFormatter(
            logging.Formatter("%(asctime)s | %(levelname)s | %(name)s | %(message)s")
        )
        logger.addHandler(file_handler)

        console_handler = logging.StreamHandler(sys.stdout)
        console_handler.setFormatter(logging.Formatter("%(levelname)s | %(message)s"))
        logger.addHandler(console_handler)

    return logger.getChild(name)
