"""
统一日志配置：控制台 + 文件双输出。

使用方式：
    from app.utils.log_config import get_logger
    logger = get_logger(__name__)
    logger.info("message")
    logger.error("something went wrong", exc_info=True)
"""

import logging
import os
import sys


def get_logger(name: str) -> logging.Logger:
    """返回已配置的 logger 实例。

    日志同时输出到：
      1. 控制台（stderr，INFO 级别）
      2. 文件（logs/app.log，DEBUG 级别，自动创建目录）
    """
    logger = logging.getLogger(name)

    # 避免重复添加 handler
    if logger.handlers:
        return logger

    logger.setLevel(logging.DEBUG)

    # 日志格式
    fmt = logging.Formatter(
        "[%(asctime)s] %(levelname)-7s %(name)s | %(message)s",
        datefmt="%H:%M:%S",
    )

    # 控制台 handler（INFO 及以上）
    console = logging.StreamHandler(sys.stderr)
    console.setLevel(logging.INFO)
    console.setFormatter(fmt)
    logger.addHandler(console)

    # 文件 handler（DEBUG 及以上）
    try:
        log_dir = os.path.join(os.path.dirname(__file__), "..", "..", "logs")
        log_dir = os.path.abspath(log_dir)
        os.makedirs(log_dir, exist_ok=True)
        log_path = os.path.join(log_dir, "app.log")
        file_handler = logging.FileHandler(log_path, encoding="utf-8")
        file_handler.setLevel(logging.DEBUG)
        file_handler.setFormatter(fmt)
        logger.addHandler(file_handler)
    except Exception:
        # 文件日志创建失败不阻塞主流程
        pass

    return logger
