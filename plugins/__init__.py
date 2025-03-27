from .event import *
from .plugin import *
from .plugin_manager import PluginManager

# 创建全局单例实例
instance = PluginManager()

# 导出常用函数
register = instance.register
# load_plugins                = instance.load_plugins
# emit_event                  = instance.emit_event
