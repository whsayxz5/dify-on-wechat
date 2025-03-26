import logging
import sys
import os
from common.log_config import logger

# 保留此文件以保持兼容性，实际日志配置已移至log_config.py

# 导出日志对象，兼容旧代码
__all__ = ['logger']

def _reset_logger(log):
    for handler in log.handlers:
        handler.close()
        log.removeHandler(handler)
        del handler
    log.handlers.clear()
    log.propagate = False
    console_handle = logging.StreamHandler(sys.stdout)
    console_handle.setFormatter(
        logging.Formatter(
            "[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    
    # 确保logs目录存在
    os.makedirs('logs', exist_ok=True)
    
    file_handle = logging.FileHandler("logs/run.log", encoding="utf-8")
    file_handle.setFormatter(
        logging.Formatter(
            "[%(levelname)s][%(asctime)s][%(filename)s:%(lineno)d] - %(message)s",
            datefmt="%Y-%m-%d %H:%M:%S",
        )
    )
    log.addHandler(file_handle)
    log.addHandler(console_handle)


def _get_logger():
    log = logging.getLogger("dify_on_wechat")
    log.setLevel(logging.INFO)
    _reset_logger(log)
    return log


# 日志句柄
logger = _get_logger()
