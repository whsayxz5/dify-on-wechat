import os
import logging
from logging.handlers import RotatingFileHandler

# 确保logs目录存在
os.makedirs('logs', exist_ok=True)

def setup_logger(name, log_file, level=logging.INFO, max_bytes=10*1024*1024, backup_count=5):
    """配置日志记录器

    Args:
        name: 日志记录器名称
        log_file: 日志文件名（相对于logs目录）
        level: 日志级别
        max_bytes: 日志文件最大字节数，超过后会滚动
        backup_count: 备份日志文件数量

    Returns:
        logger: 配置好的日志记录器
    """
    logger = logging.getLogger(name)
    logger.setLevel(level)
    
    # 移除已有的处理器
    for handler in logger.handlers[:]:
        logger.removeHandler(handler)
    
    # 创建控制台处理器
    console_handler = logging.StreamHandler()
    console_handler.setLevel(level)
    console_formatter = logging.Formatter(
        '[%(levelname)s][%(asctime)s][%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    console_handler.setFormatter(console_formatter)
    
    # 创建文件处理器
    file_path = os.path.join('logs', log_file)
    file_handler = RotatingFileHandler(
        file_path, 
        maxBytes=max_bytes, 
        backupCount=backup_count,
        encoding='utf-8'
    )
    file_handler.setLevel(level)
    file_formatter = logging.Formatter(
        '[%(levelname)s][%(asctime)s][%(name)s:%(lineno)d] - %(message)s',
        datefmt='%Y-%m-%d %H:%M:%S'
    )
    file_handler.setFormatter(file_formatter)
    
    # 添加处理器到记录器
    logger.addHandler(console_handler)
    logger.addHandler(file_handler)
    
    return logger

# 创建主日志记录器
main_logger = setup_logger('dify_on_wechat', 'main.log')

# 为不同组件创建日志记录器
app_logger = setup_logger('app', 'app.log')
admin_logger = setup_logger('admin', 'admin_ui.log')
channel_logger = setup_logger('channel', 'channel.log')
plugin_logger = setup_logger('plugin', 'plugin.log')
bot_logger = setup_logger('bot', 'bot.log')

# 兼容之前的日志记录
logger = main_logger 