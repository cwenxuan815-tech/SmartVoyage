"""全局日志对象：控制台 + 文件双通道，propagate=False 防止重复输出。"""
import logging
import os

from SmartVoyage.config import Config


def setup_logger(name: str = "SmartVoyage", log_file: str = None) -> logging.Logger:
    log_file = log_file or Config().log_file
    os.makedirs(os.path.dirname(os.path.abspath(log_file)), exist_ok=True)

    logger = logging.getLogger(name)
    logger.setLevel(logging.DEBUG)
    logger.propagate = False

    formatter = logging.Formatter('%(name)s - %(asctime)s - %(levelname)s - %(message)s')

    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    console_handler.setLevel(logging.INFO)

    file_handler = logging.FileHandler(filename=log_file, encoding="utf-8", mode="a")
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.DEBUG)

    if not logger.handlers:
        logger.addHandler(console_handler)
        logger.addHandler(file_handler)
    return logger


logger = setup_logger('SmartVoyage', Config().log_file)
