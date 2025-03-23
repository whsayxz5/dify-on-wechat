# encoding:utf-8

import json
import os
import requests
import plugins
from bridge.context import ContextType
from bridge.reply import Reply, ReplyType
from common.log import logger
from plugins import *
import random


@plugins.register(
    name="Autoreply",
    desire_priority=900,
    hidden=True,
    desc="关键词匹配过滤",
    version="0.1",
    author="darren",
)
class Autoreply(Plugin):
    def __init__(self):
        super().__init__()
        try:
            curdir = os.path.dirname(__file__)
            config_path = os.path.join(curdir, "config.json")
            conf = None
            if not os.path.exists(config_path):
                logger.debug(f"[autoreply]不存在配置文件{config_path}")
                conf = {"keyword": {}}
                with open(config_path, "w", encoding="utf-8") as f:
                    json.dump(conf, f, indent=4)
            else:
                logger.debug(f"[autoreply]加载配置文件{config_path}")
                with open(config_path, "r", encoding="utf-8") as f:
                    conf = json.load(f)
            # 加载关键词
            self.keyword = conf["keyword"]

            logger.info("[autoreply] {}".format(self.keyword))
            self.handlers[Event.ON_HANDLE_CONTEXT] = self.on_handle_context
            logger.info("[autoreply] inited.")
        except Exception as e:
            logger.warn("[autoreply] init failed, ignore or see https://github.com/zhayujie/chatgpt-on-wechat/tree/master/plugins/autoreply .")
            raise e

    def on_handle_context(self, e_context: EventContext):
        if e_context["context"].type != ContextType.TEXT:
            return

        content = e_context["context"].content.strip()
        logger.debug("[keyword] on_handle_context. content: %s" % content)
        
        # 存储所有匹配到的回复
        matched_replies = []

        # 遍历关键词字典
        for keyword_key, config in self.keyword.items():
            # 获取回复内容和匹配模式
            if isinstance(config, dict):
                reply_text = config.get('reply')
                match_type = config.get('match_type', 'exact')  # 默认为精确匹配
                keywords = config.get('keywords', [keyword_key])  # 如果有keywords字段，使用它；否则使用key作为关键字
            else:
                reply_text = config
                match_type = 'exact'
                keywords = [keyword_key]
            
            # 对每个关键字进行匹配检查
            is_match = False
            for keyword in keywords:
                if match_type == 'exact':
                    is_match = content == keyword
                elif match_type == 'contains':
                    is_match = keyword in content
                
                if is_match:
                    logger.info(f"[keyword] 匹配到关键字【{keyword}】，匹配模式：{match_type}")
                    break

            # 如果没有匹配到关键字，继续检查下一个配置
            if not is_match:
                continue

            # 如果匹配到关键字，将回复内容添加到matched_replies
            if isinstance(reply_text, list):
                # 如果是列表，随机选择一个回复
                matched_replies.append(random.choice(reply_text))
            else:
                matched_replies.append(reply_text)

        # 如果没有匹配到任何回复，直接返回
        if not matched_replies:
            return

        # 合并所有文本回复
        text_replies = []
        # 处理所有匹配到的回复
        for reply_text in matched_replies:
            # 判断匹配内容的类型
            if (reply_text.startswith("http://") or reply_text.startswith("https://")) and any(reply_text.endswith(ext) for ext in [".jpg", ".webp", ".jpeg", ".png", ".gif", ".img"]):
                # 如果是图片URL，单独发送
                reply = Reply()
                reply.type = ReplyType.IMAGE_URL
                reply.content = reply_text
                e_context["reply"] = reply
                e_context.action = EventAction.CONTINUE
                
            elif (reply_text.startswith("http://") or reply_text.startswith("https://")) and any(reply_text.endswith(ext) for ext in [".pdf", ".doc", ".docx", ".xls", "xlsx",".zip", ".rar"]):
                # 如果是文件，下载并单独发送
                file_path = "tmp"
                if not os.path.exists(file_path):
                    os.makedirs(file_path)
                file_name = reply_text.split("/")[-1]  # 获取文件名
                file_path = os.path.join(file_path, file_name)
                response = requests.get(reply_text)
                with open(file_path, "wb") as f:
                    f.write(response.content)
                reply = Reply()
                reply.type = ReplyType.FILE
                reply.content = file_path
                e_context["reply"] = reply
                e_context.action = EventAction.CONTINUE
            
            elif (reply_text.startswith("http://") or reply_text.startswith("https://")) and any(reply_text.endswith(ext) for ext in [".mp4"]):
                # 如果是视频，单独发送
                reply = Reply()
                reply.type = ReplyType.VIDEO_URL
                reply.content = reply_text
                e_context["reply"] = reply
                e_context.action = EventAction.CONTINUE
                
            else:
                # 如果是文本，添加到文本回复列表
                text_replies.append(reply_text)
        
        # 如果有文本回复，合并后发送
        if text_replies:
            reply = Reply()
            reply.type = ReplyType.TEXT
            reply.content = "\n\n".join(text_replies)
            e_context["reply"] = reply
            e_context.action = EventAction.BREAK_PASS
            
    def get_help_text(self, **kwargs):
        help_text = "关键词过滤"
        return help_text
