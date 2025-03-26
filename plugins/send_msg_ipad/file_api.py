from urllib.parse import unquote
import json
import os
from common.log import logger
from common.tmp_dir import TmpDir
from pathlib import Path

# 注意：原来的Flask静态文件已迁移到主程序的templates目录
# 所有API端点也已集成到主程序中的admin_ui.py

def validate_data(data_list):
    """验证发送数据格式"""
    if not isinstance(data_list, list):
        raise ValueError('data_list必须为列表类型')
    if not data_list:
        raise ValueError('data_list不能为空')
    for data in data_list:
        if not isinstance(data, dict):
            raise ValueError('data_list的每个元素必须为字典类型')
        if 'message' not in data:
            raise ValueError('每个消息必须包含message')

def write_message_to_file(data_list):
    """写入消息到文件，供插件读取和发送"""
    try:
        # 对 data_list 中的每个元素进行处理
        for data in data_list:
            if 'message' in data:
                # 尝试解码 message 字段
                try:
                    decoded_message = unquote(data['message'])
                    data['message'] = decoded_message
                except Exception as e:
                    # 如果解码失败，使用原始值
                    logger.warning(f"解码 message 失败: {str(e)}, 使用原始值: {data['message']}")

        validate_data(data_list)

        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "data.json")
        with open(config_path, 'w', encoding='utf-8') as file:
            json.dump(data_list, file, ensure_ascii=False)
        logger.info(f"写入成功,写入内容{data_list}")
        return True, "发送成功"
        
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        return False, f"服务器内部错误: {str(e)}"

class FileWriter:
    """兼容原插件接口的类，不再启动Flask服务器"""
    def __init__(self):
        logger.info("文件消息写入器已初始化，使用主程序API")
