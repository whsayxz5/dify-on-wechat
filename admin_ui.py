import os
import sys
import signal
import time
import json
import logging
import threading
from multiprocessing import Process
import requests
from pathlib import Path
from logging.handlers import RotatingFileHandler
from werkzeug.security import check_password_hash, generate_password_hash
from functools import wraps
from urllib.parse import unquote
from flask.cli import with_appcontext
import re
import psutil
import datetime
import secrets
import shutil
import importlib
import traceback

from flask import Flask, render_template, request, redirect, url_for, jsonify, session, abort, flash
from flask_socketio import SocketIO, emit
from flask_cors import CORS

from channel import channel_factory
from common import const
from config import load_config, conf
from plugins import instance as plugin_manager_instance
from common.tmp_dir import TmpDir
from common.log_config import admin_logger as logger

# 创建Flask应用
app = Flask(__name__, 
           static_folder='static',
           template_folder='templates')
app.config['SECRET_KEY'] = os.urandom(24)
app.config['SESSION_TYPE'] = 'filesystem'
app.config['SESSION_PERMANENT'] = True
app.config['PERMANENT_SESSION_LIFETIME'] = 86400  # 24小时

# 创建SocketIO用于实时聊天
socketio = SocketIO(app, cors_allowed_origins="*")

# 当前运行的进程实例
current_process_instance = None

# 创建一个线程锁，用于在更新联系人时防止重复操作
contact_update_lock = threading.Lock()

# 存储更新状态
global_update_status = {
    "friend_updating": False,
    "friend_last_update": None,
    "friend_update_progress": 0,
    "friend_total": 0,
    "group_updating": False,
    "group_last_update": None, 
    "group_update_progress": 0,
    "group_total": 0
}

# 添加一个信号处理函数和一个重启标志
restart_flask_server = False
original_port = 7860

def handle_restart_signal(signum, frame):
    """处理重启信号，优雅退出当前进程并重启"""
    global current_process_instance
    if current_process_instance and current_process_instance.is_alive():
        logger.info("[Admin] 接收到重启信号，正在终止当前机器人进程...")
        
        # 尝试终止进程
        current_process_instance.terminate()
        current_process_instance.join(5)  # 等待最多5秒
        
        # 检查进程是否还在运行
        if current_process_instance.is_alive():
            logger.warning("[Admin] 进程未能在5秒内终止，强制杀死...")
            current_process_instance.kill()
            current_process_instance.join(2)
    
    # 重新启动进程
    run_bot()

# 在启动应用前注册信号处理函数
signal.signal(signal.SIGUSR1, handle_restart_signal)

# 延迟更新函数
def delayed_update_contacts():
    """延迟更新联系人列表，防止机器人启动初期频繁请求导致问题"""
    try:
        logger.info("开始延迟更新联系人列表...")
        time.sleep(60 * 5)  # 延迟5分钟
        
        # 检查是否已有任务在进行
        if global_update_status['friend_updating'] or global_update_status['group_updating']:
            logger.info("已有更新任务在进行中，跳过自动更新")
            return
            
        # 更新联系人列表
        update_friend_list()
        time.sleep(5)  # 等待5秒
        
        # 再次检查，确保不会有多个任务并发
        if global_update_status['group_updating']:
            logger.info("已有群组更新任务在进行中，跳过自动更新")
            return
            
        update_group_list()
        
        logger.info("延迟更新联系人列表完成")
    except Exception as e:
        logger.error(f"延迟更新联系人列表失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())

# ================ 认证相关 ================
def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not session.get('logged_in'):
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def verify_login(username, password):
    """验证登录凭据"""
    correct_username = conf().get("web_ui_username", "dow")
    correct_password = conf().get("web_ui_password", "dify-on-wechat")
    
    return username == correct_username and password == correct_password

# ================ 微信服务管理相关 ================
def check_gewechat_online():
    """检查gewechat用户是否在线
    Returns:
        tuple: (是否在线, 错误信息)
    """
    try:
        if conf().get("channel_type") != "gewechat":
            return False, "非gewechat，无需检查"
        
        base_url = conf().get("gewechat_base_url")
        token = conf().get("gewechat_token")
        app_id = conf().get("gewechat_app_id")
        if not all([base_url, token, app_id]):
            return False, "gewechat配置不完整"

        from lib.gewechat.client import GewechatClient
        client = GewechatClient(base_url, token)
        online_status = client.check_online(app_id)
        
        if not online_status:
            return False, "获取在线状态失败"
            
        if not online_status.get('data', False):
            logger.info("Gewechat用户未在线")
            return False, "用户未登录"
            
        return True, None
        
    except Exception as e:
        logger.error(f"检查gewechat在线状态失败: {str(e)}")
        return False, f"检查在线状态出错: {str(e)}"

def get_gewechat_profile():
    """获取gewechat用户信息并下载头像，仅在用户在线时返回信息"""
    try:
        is_online, error_msg = check_gewechat_online()
        if not is_online:
            logger.info(f"Gewechat状态检查: {error_msg}")
            return None, None
            
        from lib.gewechat.client import GewechatClient
        base_url = conf().get("gewechat_base_url")
        token = conf().get("gewechat_token")
        app_id = conf().get("gewechat_app_id")
        
        client = GewechatClient(base_url, token)
        profile = client.get_profile(app_id)
        
        if not profile or 'data' not in profile:
            return None, None
            
        user_info = profile['data']
        nickname = user_info.get('nickName', '未知')
        
        # 下载头像
        avatar_url = user_info.get('bigHeadImgUrl')
        avatar_path = None
        
        if avatar_url:
            try:
                avatar_path = os.path.join('static', 'images', 'avatar.png')
                os.makedirs(os.path.dirname(avatar_path), exist_ok=True)
                response = requests.get(avatar_url)
                if response.status_code == 200:
                    with open(avatar_path, 'wb') as f:
                        f.write(response.content)
                    # 返回相对路径
                    avatar_path = '/static/images/avatar.png'
            except Exception as e:
                logger.error(f"下载头像失败: {str(e)}")
                avatar_path = None
                
        return nickname, avatar_path
    except Exception as e:
        logger.error(f"获取Gewechat用户信息失败: {str(e)}")
        return None, None

def get_qrcode_image():
    """获取登录二维码"""
    qrcode_path = os.path.join('tmp', 'login.png')
    if os.path.exists(qrcode_path):
        # 复制到静态目录
        static_path = os.path.join('static', 'images', 'login.png')
        os.makedirs(os.path.dirname(static_path), exist_ok=True)
        with open(qrcode_path, 'rb') as f_src:
            with open(static_path, 'wb') as f_dst:
                f_dst.write(f_src.read())
        return '/static/images/login.png'
    return None

def start_channel(channel_name: str):
    """启动指定的通道"""
    channel = channel_factory.create_channel(channel_name)
    available_channels = [
        "wx",
        "terminal",
        "wechatmp",
        "wechatmp_service",
        "wechatcom_app",
        "wework",
        "wechatcom_service",
        "gewechat",
        const.FEISHU,
        const.DINGTALK
    ]
    if channel_name in available_channels:
        plugin_manager_instance.load_plugins()
    channel.startup()

def run_bot():
    """运行机器人服务"""
    try:
        # 加载配置
        load_config()
        # 创建通道
        channel_name = conf().get("channel_type", "wx")
        
        # 获取gewechat用户信息
        if channel_name == "gewechat":
            get_gewechat_profile()

        start_channel(channel_name)
    except Exception as e:
        logger.error("Bot启动失败!")
        logger.exception(e)

def start_run():
    """启动机器人服务的进程"""
    global current_process_instance

    if current_process_instance is not None and current_process_instance.is_alive():
        # 杀掉当前进程
        try:
            os.kill(current_process_instance.pid, signal.SIGTERM)
            current_process_instance.join()  # 等待当前进程结束
        except Exception as e:
            logger.error(f"停止当前进程失败: {str(e)}")
    
    current_process_instance = Process(target=run_bot)
    current_process_instance.start()
    # 等待进程启动
    time.sleep(5)
    
    # 重新加载配置
    load_config()
    
    # 返回进程状态
    if not current_process_instance.is_alive():
        return False, "启动失败"
    
    return True, "启动成功"

def logout_gewechat():
    """退出gewechat登录"""
    try:
        # 检查是否是 gewechat 且在线
        if conf().get("channel_type") != "gewechat" or not check_gewechat_online()[0]:
            return False, "非gewechat或不在线，无需退出登录"

        # 调用 gewechat 退出接口
        from lib.gewechat.client import GewechatClient
        base_url = conf().get("gewechat_base_url")
        token = conf().get("gewechat_token")
        app_id = conf().get("gewechat_app_id")
        if not all([base_url, token, app_id]):
            return False, "gewechat配置不完整，无法退出登录"
        
        client = GewechatClient(base_url, token)
        result = client.logout(app_id)
        
        if not result or result.get('ret') != 200:
            logger.error(f"退出登录失败 {result}")
            return False, f"退出登录失败: {result}, 请重试"

        return True, "退出登录成功"
        
    except Exception as e:
        logger.error(f"退出登录出错: {str(e)}")
        return False, f"退出登录失败: {str(e)}"

# ================ 插件管理相关 ================
def get_plugin_list():
    """获取插件列表"""
    try:
        logger.info("开始获取插件列表...")
        plugin_list = []
        
        # 直接使用导入的实例
        # 如果实例中没有插件数据，先加载
        if not plugin_manager_instance.plugins or len(plugin_manager_instance.plugins) == 0:
            logger.warning("PluginManager实例中无插件数据，这可能是由于未正确加载godcmd初始化的实例")
            logger.warning("尝试加载插件配置数据（但不初始化插件实例）...")
            # 尝试读取配置，但不初始化插件实例
            try:
                # 仅加载配置和扫描插件，不激活它们
                plugin_manager_instance.load_config()
                plugin_manager_instance.scan_plugins()
                logger.info(f"加载配置后，发现 {len(plugin_manager_instance.plugins)} 个插件")
            except Exception as e:
                logger.error(f"尝试加载插件配置失败: {str(e)}")
                import traceback
                logger.error(traceback.format_exc())
        
        # 直接获取插件列表，与godcmd.py中的plist命令行为一致
        plugins = plugin_manager_instance.list_plugins()
        
        logger.info(f"从PluginManager获取到 {len(plugins)} 个插件")
        
        # 如果仍然没有插件，尝试检查文件系统中的插件
        if len(plugins) == 0:
            logger.warning("尝试从文件系统直接检查插件目录...")
            plugins_dir = "./plugins"
            for plugin_name in os.listdir(plugins_dir):
                plugin_path = os.path.join(plugins_dir, plugin_name)
                init_path = os.path.join(plugin_path, "__init__.py")
                if os.path.isdir(plugin_path) and os.path.isfile(init_path):
                    logger.info(f"发现插件目录: {plugin_name}")
        
        # 遍历插件
        for name, plugin_cls in plugins.items():
            try:
                # 获取插件基本信息
                plugin_info = {
                    'name': plugin_cls.name,
                    'description': getattr(plugin_cls, 'desc', None) or '无描述',
                    'author': getattr(plugin_cls, 'author', None) or '未知',
                    'version': getattr(plugin_cls, 'version', None) or '1.0',
                    'enabled': plugin_cls.enabled,  # 直接使用插件类的enabled属性
                    'priority': plugin_cls.priority,
                    'hidden': getattr(plugin_cls, 'hidden', False),
                    'has_config': False,
                    'active': name in plugin_manager_instance.instances  # 添加活动状态
                }
                
                # 检查是否有配置文件
                if hasattr(plugin_cls, 'path'):
                    config_path = os.path.join(plugin_cls.path, 'config.json')
                    plugin_info['has_config'] = os.path.exists(config_path)
                
                # 无论是否隐藏，都添加到列表中
                plugin_list.append(plugin_info)
                logger.info(f"添加插件到列表: {plugin_info['name']} (启用:{plugin_info['enabled']}, 活动:{plugin_info['active']})")
                
            except Exception as e:
                logger.warning(f"处理插件 {name} 出错: {str(e)}")
                import traceback
                logger.warning(traceback.format_exc())
                # 即使处理单个插件出错，也继续处理其他插件
        
        logger.info(f"获取到 {len(plugin_list)} 个插件")
        return plugin_list
    except Exception as e:
        logger.error(f"获取插件列表失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return []

def get_plugin_config(plugin_name):
    """获取插件配置"""
    try:
        logger.info(f"获取插件 {plugin_name} 的配置...")
        
        # 查找插件目录
        plugin_path = os.path.join("./plugins", plugin_name.lower())
        
        # 如果找不到精确匹配的目录，尝试不区分大小写查找
        if not os.path.exists(plugin_path):
            for dirname in os.listdir("./plugins"):
                if dirname.lower() == plugin_name.lower():
                    plugin_path = os.path.join("./plugins", dirname)
                    break
        
        # 检查配置文件是否存在
        config_path = os.path.join(plugin_path, 'config.json')
        if not os.path.exists(config_path):
            logger.warning(f"插件 {plugin_name} 的配置文件不存在")
            
            # 尝试查找配置模板
            template_path = os.path.join(plugin_path, 'config.json.template')
            if os.path.exists(template_path):
                try:
                    with open(template_path, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    logger.info(f"从模板创建插件 {plugin_name} 的配置")
                    
                    # 保存配置
                    with open(config_path, 'w', encoding='utf-8') as f:
                        json.dump(config, f, ensure_ascii=False, indent=4)
                    
                    return config
                except Exception as e:
                    logger.error(f"从模板创建配置失败: {str(e)}")
            
            return {}
        
        # 读取配置文件
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
            logger.info(f"成功读取插件 {plugin_name} 的配置")
            return config
            
    except Exception as e:
        logger.error(f"获取插件配置失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return None

def update_plugin_config(plugin_name, config_data):
    """更新插件配置"""
    try:
        logger.info(f"更新插件 {plugin_name} 的配置...")
        
        # 查找插件目录
        plugin_path = os.path.join("./plugins", plugin_name.lower())
        
        # 如果找不到精确匹配的目录，尝试不区分大小写查找
        if not os.path.exists(plugin_path):
            for dirname in os.listdir("./plugins"):
                if dirname.lower() == plugin_name.lower():
                    plugin_path = os.path.join("./plugins", dirname)
                    break
        
        if not os.path.exists(plugin_path):
            logger.error(f"找不到插件目录: {plugin_name}")
            return False
        
        # 配置文件路径
        config_path = os.path.join(plugin_path, 'config.json')
        
        # 保存配置
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        logger.info(f"插件 {plugin_name} 配置更新成功")
        
        # 尝试重载插件
        try:
            plugin_manager_instance.reload_plugin(plugin_name.upper())
            logger.info(f"插件 {plugin_name} 重新加载成功")
        except Exception as e:
            logger.warning(f"重新加载插件 {plugin_name} 失败: {str(e)}")
            # 仍然返回成功，因为配置已经更新
        
        return True
    except Exception as e:
        logger.error(f"更新插件配置失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return False

# ================ 聊天管理相关 ================
def retry_on_failure(func, max_retries=3):
    """错误重试机制"""
    for i in range(max_retries):
        try:
            return func()
        except Exception as e:
            if i == max_retries - 1:
                raise e
            logger.warning(f"操作失败,正在重试 ({i+1}/{max_retries}): {str(e)}")
            time.sleep(1)

def update_friend_list():
    """更新好友列表"""
    # 尝试获取锁，如果已经有更新任务在进行则直接返回
    if not contact_update_lock.acquire(blocking=False):
        logger.warning("已有更新联系人任务在进行中，忽略当前请求")
        return False
    
    try:
        if conf().get("channel_type") != "gewechat":
            logger.warning("当前渠道不支持此功能")
            return False
        
        from lib.gewechat.client import GewechatClient
        
        try:
            # 即使获取了锁，也再次检查一下状态标记，确保状态一致性
            if global_update_status['friend_updating']:
                logger.warning("全局状态显示已有更新任务在进行中，忽略当前请求")
                return False
                
            base_url = conf().get("gewechat_base_url")
            token = conf().get("gewechat_token", "")
            app_id = conf().get("gewechat_app_id")
            
            if not all([base_url, app_id]):
                logger.error("gewechat配置不完整")
                return False
            
            logger.info(f"开始更新好友列表: base_url={base_url}, app_id={app_id}")
            client = GewechatClient(base_url, token)
            
            # 获取好友列表
            logger.info("获取联系人列表...")
            contacts_json = client.fetch_contacts_list(app_id)
            if contacts_json.get("ret") != 200:
                logger.error(f"获取联系人列表失败: {contacts_json}")
                return False
            
            friends = contacts_json["data"].get("friends", [])
            logger.info(f"找到 {len(friends)} 个好友ID")
            
            # 直接检查是否有好友ID
            if not friends:
                logger.warning("未找到好友ID，创建空列表文件")
                # 保存空列表到文件
                tmp_dir = TmpDir().path()
                friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
                with open(friend_list_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False)
                return True
                
            friend_list = []
            
            # 更新全局进度状态
            global_update_status['friend_total'] = len(friends)
            global_update_status['friend_update_progress'] = 0
            global_update_status['friend_updating'] = True
            
            # 批量获取好友信息,每批20个(API限制)
            batch_size = 20
            for i in range(0, len(friends), batch_size):
                batch_friends = friends[i:i + batch_size]
                
                def get_batch_info():
                    return client.get_detail_info(app_id, batch_friends)
                
                try:
                    info_json = retry_on_failure(get_batch_info)
                    if info_json.get("ret") == 200:
                        data_list = info_json.get("data", [])
                        for friend_info in data_list:
                            if friend_info.get("nickName"):
                                friend_list.append(friend_info)
                    else:
                        logger.warning(f"获取好友信息失败: {info_json}")
                except Exception as e:
                    logger.error(f"处理好友批次时出错: {e}")
                    continue
                
                # 更新进度
                global_update_status['friend_update_progress'] = min(i + batch_size, len(friends))
                logger.info(f"已处理 {global_update_status['friend_update_progress']}/{len(friends)} 个好友")
            
            # 保存到文件
            tmp_dir = TmpDir().path()
            friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
            
            with open(friend_list_file, 'w', encoding='utf-8') as f:
                json.dump(friend_list, f, ensure_ascii=False)
            
            logger.info(f"好友列表更新成功，共{len(friend_list)}个好友")
            
            # 更新完成，重置状态
            global_update_status['friend_updating'] = False
            global_update_status['friend_last_update'] = datetime.datetime.now()
            return True
        except Exception as e:
            logger.error(f"更新好友列表时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 出错时也需要重置状态
            global_update_status['friend_updating'] = False
            return False
    finally:
        # 确保在函数结束时释放锁
        contact_update_lock.release()

def update_group_list():
    """更新群组列表"""
    # 尝试获取锁，如果已经有更新任务在进行则直接返回
    if not contact_update_lock.acquire(blocking=False):
        logger.warning("已有更新联系人任务在进行中，忽略当前请求")
        return False
    
    try:
        if conf().get("channel_type") != "gewechat":
            logger.warning("当前渠道不支持此功能")
            return False
        
        from lib.gewechat.client import GewechatClient
        
        try:
            # 即使获取了锁，也再次检查一下状态标记，确保状态一致性
            if global_update_status['group_updating']:
                logger.warning("全局状态显示已有群组更新任务在进行中，忽略当前请求")
                return False
                
            base_url = conf().get("gewechat_base_url")
            token = conf().get("gewechat_token", "")
            app_id = conf().get("gewechat_app_id")
            
            if not all([base_url, app_id]):
                logger.error("gewechat配置不完整")
                return False
            
            logger.info(f"开始更新群组列表: base_url={base_url}, app_id={app_id}")
            client = GewechatClient(base_url, token)
            
            # 获取群聊列表
            logger.info("获取联系人列表...")
            contacts_json = client.fetch_contacts_list(app_id)
            if contacts_json.get("ret") != 200:
                logger.error(f"获取联系人列表失败: {contacts_json}")
                return False
            
            chatrooms = contacts_json["data"].get("chatrooms", [])
            logger.info(f"找到 {len(chatrooms)} 个群聊ID")
            
            chatroom_list = []
            
            # 直接检查是否有群聊ID
            if not chatrooms:
                logger.warning("未找到群聊ID，创建空列表文件")
                # 保存空列表到文件
                tmp_dir = TmpDir().path()
                chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
                with open(chatroom_list_file, 'w', encoding='utf-8') as f:
                    json.dump([], f, ensure_ascii=False)
                return True
            
            # 更新全局进度状态
            global_update_status['group_total'] = len(chatrooms)
            global_update_status['group_update_progress'] = 0
            global_update_status['group_updating'] = True
            
            # 获取每个群聊的详细信息(群组API只支持单个查询)
            for i, chatroom_id in enumerate(chatrooms):
                def get_chatroom_info():
                    return client.get_chatroom_info(app_id, chatroom_id)
                
                try:
                    info_json = retry_on_failure(get_chatroom_info)
                    if info_json.get("ret") == 200:
                        room_info = info_json["data"]
                        if room_info.get("nickName"):
                            chatroom_list.append(room_info)
                    else:
                        logger.warning(f"获取群聊 {chatroom_id} 详情失败: {info_json}")
                except Exception as e:
                    logger.error(f"处理群聊 {chatroom_id} 时出错: {e}")
                    continue
                
                # 更新进度
                global_update_status['group_update_progress'] = i + 1
                if (i + 1) % 10 == 0:  # 每10个群组记录一次进度
                    logger.info(f"已处理 {i + 1}/{len(chatrooms)} 个群组")
            
            # 保存到文件
            tmp_dir = TmpDir().path()
            chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
            
            with open(chatroom_list_file, 'w', encoding='utf-8') as f:
                json.dump(chatroom_list, f, ensure_ascii=False)
            
            logger.info(f"群组列表更新成功，共{len(chatroom_list)}个群组")
            
            # 更新完成，重置状态
            global_update_status['group_updating'] = False
            global_update_status['group_last_update'] = datetime.datetime.now()
            return True
        except Exception as e:
            logger.error(f"更新群组列表时发生错误: {e}")
            import traceback
            logger.error(traceback.format_exc())
            
            # 出错时也需要重置状态
            global_update_status['group_updating'] = False
            return False
    finally:
        # 确保在函数结束时释放锁
        contact_update_lock.release()

def get_contacts():
    """获取联系人和群组列表，只读取现有文件，不触发更新"""
    # 添加内存缓存
    if hasattr(get_contacts, '_cache'):
        cache_time, cached_data = get_contacts._cache
        if time.time() - cache_time < 300:  # 5分钟缓存
            return cached_data
    
    tmp_dir = TmpDir().path()
    friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
    chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
    
    friends = []
    groups = []
    
    # 读取文件（如果文件不存在，则返回空列表）
    if os.path.exists(friend_list_file):
        try:
            with open(friend_list_file, 'r', encoding='utf-8') as f:
                friend_list = json.load(f)
                for friend in friend_list:
                    if friend.get("remark"):
                        friends.append(friend["remark"])
                    else:
                        friends.append(friend["nickName"])
        except Exception as e:
            logger.error(f"读取好友列表失败: {e}")
    else:
        logger.info("通讯录文件不存在，返回空列表")
    
    if os.path.exists(chatroom_list_file):
        try:
            with open(chatroom_list_file, 'r', encoding='utf-8') as f:
                chatroom_list = json.load(f)
                for chatroom in chatroom_list:
                    if chatroom.get("nickName"):
                        groups.append(chatroom["nickName"])
        except Exception as e:
            logger.error(f"读取群组列表失败: {e}")
    else:
        logger.info("群组详情文件不存在，返回空列表")
    
    # 更新缓存
    result = (friends, groups)
    get_contacts._cache = (time.time(), result)
    return result

def send_message(receiver_name, group_name, message):
    """发送消息到联系人或群组"""
    try:
        if conf().get("channel_type") != "gewechat":
            return False, "非gewechat，不支持发送消息"
        
        from lib.gewechat.client import GewechatClient
        base_url = conf().get("gewechat_base_url")
        token = conf().get("gewechat_token")
        app_id = conf().get("gewechat_app_id")
        
        if not all([base_url, token, app_id]):
            return False, "gewechat配置不完整"
        
        client = GewechatClient(base_url, token)
        
        # 读取缓存的通讯录文件
        tmp_dir = TmpDir().path()
        friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
        chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
        
        if receiver_name:
            # 发送个人消息时，需要先查找wxid
            if not os.path.exists(friend_list_file):
                return False, "好友通讯录文件不存在，请先更新通讯录"
            
            try:
                with open(friend_list_file, 'r', encoding='utf-8') as f:
                    friend_list = json.load(f)
                    
                # 查找匹配的好友
                friend_info = None
                for friend in friend_list:
                    if receiver_name in (friend.get("nickName"), friend.get("remark")):
                        friend_info = friend
                        break
                
                if not friend_info:
                    return False, f"未找到好友: {receiver_name}"
                
                # 获取好友wxid
                to_wxid = friend_info.get("userName")
                if not to_wxid:
                    return False, f"好友 {receiver_name} 没有有效的wxid"
                
                logger.info(f"发送个人消息给 {receiver_name}({to_wxid}): {message[:20]}...")
                result = client.post_text(app_id, to_wxid, message)
            except Exception as e:
                logger.error(f"发送个人消息时出错: {e}")
                return False, f"发送个人消息失败: {str(e)}"
                
        elif group_name:
            # 发送群组消息时，需要先查找群的chatroomId
            if not os.path.exists(chatroom_list_file):
                return False, "群组通讯录文件不存在，请先更新群组信息"
            
            try:
                with open(chatroom_list_file, 'r', encoding='utf-8') as f:
                    chatroom_list = json.load(f)
                
                # 查找匹配的群聊
                chatroom_info = None
                for chatroom in chatroom_list:
                    if chatroom.get("nickName") == group_name:
                        chatroom_info = chatroom
                        break
                
                if not chatroom_info:
                    return False, f"未找到群组: {group_name}"
                
                # 获取群聊chatroomId
                to_chatroom_id = chatroom_info.get("chatroomId")
                if not to_chatroom_id:
                    return False, f"群组 {group_name} 没有有效的chatroomId"
                
                logger.info(f"发送群组消息给 {group_name}({to_chatroom_id}): {message[:20]}...")
                result = client.post_text(app_id, to_chatroom_id, message)
            except Exception as e:
                logger.error(f"发送群组消息时出错: {e}")
                return False, f"发送群组消息失败: {str(e)}"
        else:
            return False, "接收者不能为空"
        
        if result and result.get('ret') == 200:
            return True, "消息发送成功"
        else:
            logger.error(f"API返回错误: {result}")
            return False, f"消息发送失败: {result}"
    
    except Exception as e:
        logger.error(f"发送消息失败: {str(e)}")
        return False, f"发送消息失败: {str(e)}"

def get_chat_history(contact_name=None, group_name=None, page=1, page_size=20):
    """获取聊天历史记录"""
    try:
        # 这里需要根据实际存储方式获取聊天记录
        # 此处为示例实现
        return []
    except Exception as e:
        logger.error(f"获取聊天历史失败: {str(e)}")
        return []

# ================ 自动回复管理相关 ================
def get_autoreply_config():
    """获取自动回复配置"""
    try:
        autoreply_config_path = 'plugins/autoreply/config.json'
        if os.path.exists(autoreply_config_path):
            with open(autoreply_config_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        return {"keyword": {}}
    except Exception as e:
        logger.error(f"获取自动回复配置失败: {str(e)}")
        return {"keyword": {}}

def update_autoreply_config(config_data):
    """更新自动回复配置"""
    try:
        autoreply_config_path = 'plugins/autoreply/config.json'
        os.makedirs(os.path.dirname(autoreply_config_path), exist_ok=True)
        with open(autoreply_config_path, 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        return True
    except Exception as e:
        logger.error(f"更新自动回复配置失败: {str(e)}")
        return False

# ================ 系统配置管理相关 ================
def get_system_config():
    """获取系统配置"""
    try:
        # 直接读取config.json
        if os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                return json.load(f)
        return {}
    except Exception as e:
        logger.error(f"获取系统配置失败: {str(e)}")
        return {}

def update_system_config(config_data):
    """更新系统配置"""
    try:
        with open('config.json', 'w', encoding='utf-8') as f:
            json.dump(config_data, f, ensure_ascii=False, indent=4)
        # 重新加载配置
        load_config()
        return True
    except Exception as e:
        logger.error(f"更新系统配置失败: {str(e)}")
        return False

# ================ 启动回调函数 ================
def schedule_contact_update():
    """应用启动后延迟5分钟更新联系人列表"""
    def delayed_start():
        logger.info("Flask应用已启动并接收了第一个请求，计划5分钟后更新联系人列表...")
        time.sleep(2)  # 先等待2秒，确保Flask应用完全启动
        update_thread = threading.Thread(target=delayed_update_contacts, daemon=True)
        update_thread.start()
    
    # 启动一个线程进行延迟触发，避免阻塞请求处理
    threading.Thread(target=delayed_start, daemon=True).start()

# 添加第一个请求处理函数
@app.before_request
def before_first_request_handler():
    # 检查是否已经完成初始化
    if not hasattr(app, '_initialization_done'):
        # 标记为已初始化，防止重复执行
        app._initialization_done = True
        
        # 获取插件管理器实例
        try:
            logger.info("获取插件管理器实例...")
            # 使用导入的全局实例，而不是创建新实例
            logger.info(f"插件管理器状态: 已加载 {len(plugin_manager_instance.plugins)} 个插件，激活 {len(plugin_manager_instance.instances)} 个")
        except Exception as e:
            logger.error(f"获取插件管理器实例失败: {str(e)}")
            import traceback
            logger.error(traceback.format_exc())
        
        # 检查通讯录文件是否存在
        tmp_dir = TmpDir().path()
        friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
        chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
        
        # 检查文件是否存在并有效
        friend_file_valid = os.path.exists(friend_list_file) and os.path.getsize(friend_list_file) > 10
        group_file_valid = os.path.exists(chatroom_list_file) and os.path.getsize(chatroom_list_file) > 10
        
        # 只有当文件不存在或无效时，才启动延迟更新
        if not friend_file_valid or not group_file_valid:
            logger.info("检测到通讯录或群组详情文件不存在或无效，将在5分钟后自动更新")
            schedule_contact_update()
        else:
            logger.info("已存在有效的通讯录和群组详情文件，不需要自动更新")

# ================ 路由 ================
@app.route('/')
@login_required
def index():
    """主页"""
    # 获取插件列表并计算数量
    plugin_count = len(get_plugin_list())
    logger.info(f"主页展示: 检测到 {plugin_count} 个插件")
    
    # 计算登录时长
    login_duration = "未知"
    try:
        if conf().get("channel_type") == "gewechat":
            is_online, _ = check_gewechat_online()
            if is_online:
                # 尝试获取登录时间，如果无法获取则使用进程启动时间作为替代
                login_time = None
                
                # 如果进程存在且在运行，使用进程启动时间
                if current_process_instance is not None and current_process_instance.is_alive():
                    # 获取进程创建时间
                    try:
                        process = psutil.Process(current_process_instance.pid)
                        login_time = process.create_time()
                    except (psutil.NoSuchProcess, psutil.AccessDenied, psutil.ZombieProcess):
                        logger.warning("无法获取进程创建时间")
                
                if login_time:
                    # 计算时间差
                    current_time = time.time()
                    duration_seconds = int(current_time - login_time)
                    
                    # 转换为小时和分钟
                    hours = duration_seconds // 3600
                    minutes = (duration_seconds % 3600) // 60
                    
                    # 格式化输出
                    if hours > 0:
                        login_duration = f"{hours}小时{minutes}分钟"
                    else:
                        login_duration = f"{minutes}分钟"
                    
                    logger.info(f"计算登录时长: {login_duration}")
    except Exception as e:
        logger.error(f"计算登录时长失败: {str(e)}")
        login_duration = "未知"
    
    return render_template('index.html', plugin_count=plugin_count, login_duration=login_duration)

@app.route('/chat')
@login_required
def chat():
    """聊天管理页面"""
    return render_template('chat.html')

@app.route('/mass_message')
@login_required
def mass_message():
    """群发消息页面"""
    return render_template('mass_message.html')

@app.route('/autoreply')
@login_required
def autoreply():
    """自动回复配置页面"""
    return render_template('autoreply.html')

@app.route('/plugins')
@login_required
def plugins():
    """插件管理页面"""
    return render_template('plugins.html')

@app.route('/settings')
@login_required
def settings():
    """系统设置页面"""
    return render_template('settings.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """登录页面"""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if verify_login(username, password):
            session['logged_in'] = True
            session['username'] = username
            return redirect(url_for('index'))
        else:
            flash('用户名或密码错误')
    
    return render_template('login.html')

@app.route('/logout')
def logout():
    """登出"""
    session.clear()
    return redirect(url_for('login'))

# ============== API 路由 ==============
@app.route('/api/status')
@login_required
def get_status():
    """获取系统状态"""
    # 检查进程是否存活
    is_running = current_process_instance is not None and current_process_instance.is_alive()
    
    # 获取登录状态
    nickname = None
    avatar_path = None
    is_online = False
    
    if conf().get("channel_type") == "gewechat" and is_running:
        is_online, _ = check_gewechat_online()
        if is_online:
            nickname, avatar_path = get_gewechat_profile()
    
    status_data = {
        "is_running": is_running,
        "is_online": is_online,
        "nickname": nickname,
        "avatar_path": avatar_path,
        "qrcode_path": get_qrcode_image() if not is_online else None,
        "channel_type": conf().get("channel_type")
    }
    
    return jsonify(status_data)

@app.route('/api/restart', methods=['POST'])
@login_required
def restart_service():
    """重启服务"""
    success, message = start_run()
    return jsonify({"success": success, "message": message})

@app.route('/api/logout_gewechat', methods=['POST'])
@login_required
def api_logout_gewechat():
    """退出gewechat登录"""
    success, message = logout_gewechat()
    return jsonify({"success": success, "message": message})

@app.route('/api/plugins')
@login_required
def api_get_plugins():
    """获取插件列表"""
    try:
        logger.info("API请求：获取插件列表")
        plugins = get_plugin_list()
        logger.info(f"API响应：返回 {len(plugins)} 个插件信息")
        return jsonify({"plugins": plugins})
    except Exception as e:
        logger.error(f"获取插件列表API异常: {str(e)}")
        return jsonify({"plugins": [], "error": str(e)})

@app.route('/api/plugins/<plugin_name>/config')
@login_required
def api_get_plugin_config(plugin_name):
    """获取插件配置"""
    config = get_plugin_config(plugin_name)
    return jsonify({"success": config is not None, "config": config})

@app.route('/api/plugins/<plugin_name>/config', methods=['POST'])
@login_required
def api_update_plugin_config(plugin_name):
    """更新插件配置"""
    config_data = request.json
    success = update_plugin_config(plugin_name, config_data)
    return jsonify({"success": success})

@app.route('/api/plugins/<plugin_name>/toggle', methods=['POST'])
@login_required
def api_toggle_plugin(plugin_name):
    """启用或禁用插件"""
    enable = request.json.get('enable', False)
    
    # 使用导入的全局实例
    if enable:
        # enablep命令的实现方式
        success, message = plugin_manager_instance.enable_plugin(plugin_name)
    else:
        # disablep命令的实现方式
        name = plugin_name.upper()
        if name not in plugin_manager_instance.plugins:
            return jsonify({"success": False, "message": "插件不存在"})
        
        # 直接调用disable_plugin方法，这会更新配置文件并从实例中移除
        success = plugin_manager_instance.disable_plugin(name)
        message = "插件已禁用" if success else "插件不存在"
    
    logger.info(f"插件{plugin_name}状态更新: {'启用' if enable else '禁用'}, 结果: {success}")
    
    return jsonify({"success": success, "message": message})

@app.route('/api/plugins/install', methods=['POST'])
@login_required
def api_install_plugin():
    """安装插件"""
    repo = request.json.get('repo', '')
    if not repo:
        return jsonify({"success": False, "message": "仓库地址不能为空"})
    
    # 调用插件管理器安装插件，使用导入的全局实例
    success, message = plugin_manager_instance.install_plugin(repo)
    return jsonify({"success": success, "message": message})

@app.route('/api/plugins/scan', methods=['POST'])
@login_required
def api_scan_plugins():
    """扫描并加载插件"""
    try:
        logger.info("开始扫描并加载插件...")
        
        # 使用导入的全局实例
        new_plugins = plugin_manager_instance.scan_plugins()
        failed_plugins = plugin_manager_instance.activate_plugins()
        
        result = {
            "success": True,
            "new_plugins": len(new_plugins),
            "failed_plugins": failed_plugins,
            "message": f"找到 {len(new_plugins)} 个新插件, {len(failed_plugins)} 个插件激活失败"
        }
        return jsonify(result)
    except Exception as e:
        logger.error(f"扫描插件出错: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({"success": False, "message": f"扫描插件出错: {str(e)}"})

@app.route('/api/plugins/<plugin_name>/enable', methods=['POST'])
@login_required
def api_enable_plugin(plugin_name):
    """启用插件"""
    try:
        # 使用导入的全局实例
        success, message = plugin_manager_instance.enable_plugin(plugin_name.upper())
        return jsonify({"success": success, "message": message})
    except Exception as e:
        logger.error(f"启用插件 {plugin_name} 出错: {str(e)}")
        return jsonify({"success": False, "message": f"启用插件出错: {str(e)}"})

@app.route('/api/plugins/<plugin_name>/disable', methods=['POST'])
@login_required
def api_disable_plugin(plugin_name):
    """禁用插件"""
    try:
        # 使用导入的全局实例
        success = plugin_manager_instance.disable_plugin(plugin_name.upper())
        return jsonify({"success": success, "message": "插件已禁用" if success else "禁用插件失败"})
    except Exception as e:
        logger.error(f"禁用插件 {plugin_name} 出错: {str(e)}")
        return jsonify({"success": False, "message": f"禁用插件出错: {str(e)}"})

@app.route('/api/plugins/<plugin_name>/uninstall', methods=['POST'])
@login_required
def api_uninstall_plugin(plugin_name):
    """卸载插件"""
    # 使用导入的全局实例
    success, message = plugin_manager_instance.uninstall_plugin(plugin_name)
    return jsonify({"success": success, "message": message})

@app.route('/api/plugins/<plugin_name>/priority', methods=['POST'])
@login_required
def api_set_plugin_priority(plugin_name):
    """设置插件优先级"""
    priority = request.json.get('priority', 0)
    try:
        priority = int(priority)
        # 使用导入的全局实例
        success = plugin_manager_instance.set_plugin_priority(plugin_name, priority)
        return jsonify({"success": success, "message": "设置优先级成功" if success else "设置优先级失败"})
    except Exception as e:
        logger.error(f"设置插件优先级失败: {str(e)}")
        return jsonify({"success": False, "message": f"设置优先级失败: {str(e)}"})

@app.route('/api/contacts')
@login_required
def api_get_contacts():
    """获取联系人和群组列表"""
    # 检查是否需要触发更新
    force_update = request.args.get('force_update', '').lower() == 'true'
    silent = request.args.get('silent', '').lower() == 'true'
    
    # 检查文件是否存在
    tmp_dir = TmpDir().path()
    friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
    chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
    
    # 文件状态
    friend_file_exists = os.path.exists(friend_list_file) and os.path.getsize(friend_list_file) > 10
    group_file_exists = os.path.exists(chatroom_list_file) and os.path.getsize(chatroom_list_file) > 10
    
    # 如果强制更新或文件不存在且不是静默模式，则提示用户需要更新
    needs_update = force_update or (not friend_file_exists or not group_file_exists)
    
    # 获取联系人数据（不触发更新）
    friends, groups = get_contacts()
    
    # 构建响应
    response_data = {
        "success": True, 
        "data": {
            "friends": friends, 
            "groups": groups
        }
    }
    
    # 如果需要更新且非静默模式，添加提示信息
    if needs_update and not silent:
        msg = "没有找到联系人数据，请先在聊天管理页面进行更新" if not (friend_file_exists or group_file_exists) else "建议更新联系人数据以获取最新信息"
        response_data["needs_update"] = True
        response_data["message"] = msg
    
    return jsonify(response_data)

@app.route('/api/update_friends', methods=['POST'])
@login_required
def api_update_friends():
    """更新通讯录"""
    try:
        # 先检查全局状态标志，避免创建不必要的线程
        if global_update_status['friend_updating']:
            logger.info("通讯录更新已在进行中，忽略重复请求")
            return jsonify({"success": False, "message": "通讯录更新已在进行中"})
        
        # 尝试获取锁但不阻塞，如果已有锁则直接返回
        if not contact_update_lock.acquire(blocking=False):
            logger.info("有其他更新任务正在进行，忽略当前请求")
            return jsonify({"success": False, "message": "有其他更新任务正在进行"})
            
        contact_update_lock.release()  # 立即释放锁，让实际的更新函数来获取
            
        # 在新线程中执行，避免阻塞API响应
        logger.info("手动触发通讯录更新")
        threading.Thread(target=update_friend_list, daemon=True).start()
        return jsonify({"success": True, "message": "通讯录更新已开始"})
    except Exception as e:
        logger.error(f"触发通讯录更新失败: {e}")
        return jsonify({"success": False, "message": f"触发失败: {str(e)}"})

@app.route('/api/update_rooms', methods=['POST'])
@login_required
def api_update_rooms():
    """更新群组详情"""
    try:
        # 先检查全局状态标志，避免创建不必要的线程
        if global_update_status['group_updating']:
            logger.info("群组详情更新已在进行中，忽略重复请求")
            return jsonify({"success": False, "message": "群组详情更新已在进行中"})
        
        # 尝试获取锁但不阻塞，如果已有锁则直接返回
        if not contact_update_lock.acquire(blocking=False):
            logger.info("有其他更新任务正在进行，忽略当前请求")
            return jsonify({"success": False, "message": "有其他更新任务正在进行"})
            
        contact_update_lock.release()  # 立即释放锁，让实际的更新函数来获取
        
        # 在新线程中执行，避免阻塞API响应
        logger.info("手动触发群组详情更新")
        threading.Thread(target=update_group_list, daemon=True).start()
        return jsonify({"success": True, "message": "群组详情更新已开始"})
    except Exception as e:
        logger.error(f"触发群组详情更新失败: {e}")
        return jsonify({"success": False, "message": f"触发失败: {str(e)}"})

@app.route('/api/update_status')
@login_required
def api_get_update_status():
    """获取更新状态"""
    # 检查文件是否存在
    tmp_dir = TmpDir().path()
    friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
    chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
    
    # 构建状态响应
    status_data = {
        "status": global_update_status,
        "files": {
            "friend_file_exists": os.path.exists(friend_list_file),
            "group_file_exists": os.path.exists(chatroom_list_file)
        }
    }
    
    return jsonify({"success": True, "data": status_data})

@app.route('/api/direct_send_message', methods=['POST'])
@login_required
def api_direct_send_message():
    """直接发送消息，不通过文件中转"""
    try:
        data = request.json
        receiver_names = data.get('receiver_names', [])
        group_names = data.get('group_names', [])
        content = data.get('content', '')
        
        # 验证数据
        if not content:
            return jsonify({"success": False, "message": "消息内容不能为空"}), 400
            
        if not receiver_names and not group_names:
            return jsonify({"success": False, "message": "接收者和群组不能同时为空"}), 400
        
        # 确保是列表类型
        if isinstance(receiver_names, str):
            receiver_names = [receiver_names]
        if isinstance(group_names, str):
            group_names = [group_names]
            
        results = []
        
        # 处理"所有人"选项
        if '所有人' in receiver_names:
            friends, _ = get_contacts()
            receiver_names = friends
            
        # 批量发送给个人
        for receiver in receiver_names:
            success, msg = send_message(receiver, None, content)
            results.append({
                "receiver": receiver,
                "success": success,
                "message": msg
            })
            
        # 批量发送给群组
        for group in group_names:
            success, msg = send_message(None, group, content)
            results.append({
                "receiver": f"群聊:{group}",
                "success": success,
                "message": msg
            })
            
        return jsonify({
            "success": True, 
            "message": f"处理了 {len(results)} 条消息", 
            "results": results
        })
    except Exception as e:
        logger.error(f"直接发送消息失败: {str(e)}")
        return jsonify({"success": False, "message": f"发送消息失败: {str(e)}"}), 500

@app.route('/api/chat_history')
@login_required
def api_get_chat_history():
    """获取聊天历史记录"""
    contact_name = request.args.get('contact')
    group_name = request.args.get('group')
    page = int(request.args.get('page', 1))
    page_size = int(request.args.get('page_size', 20))
    
    history = get_chat_history(contact_name, group_name, page, page_size)
    return jsonify({"success": True, "data": history})

@app.route('/api/get_autoreply_config', methods=['GET'])
@login_required
def api_get_autoreply_config():
    """获取自动回复配置"""
    try:
        config = get_autoreply_config()
        return jsonify({
            'status': 'success',
            'data': config
        })
    except Exception as e:
        logger.error(f"获取自动回复配置失败: {str(e)}")
        return jsonify({'status': 'error', 'message': '获取配置失败'}), 500

@app.route('/api/update_autoreply_config', methods=['POST'])
@login_required
def api_update_autoreply_config():
    """更新自动回复配置"""
    try:
        new_config = request.json
        if not isinstance(new_config, dict) or 'keyword' not in new_config:
            return jsonify({'status': 'error', 'message': '无效的配置格式'}), 400
            
        success = update_autoreply_config(new_config)
        if not success:
            return jsonify({'status': 'error', 'message': '更新配置失败'}), 500
            
        return jsonify({
            'status': 'success',
            'message': '配置更新成功'
        })
    except Exception as e:
        logger.error(f"更新自动回复配置失败: {str(e)}")
        return jsonify({'status': 'error', 'message': '更新配置失败'}), 500

@app.route('/api/system_config')
@login_required
def api_get_system_config():
    """获取系统配置"""
    config = get_system_config()
    return jsonify({"success": True, "data": config})

@app.route('/api/system_config', methods=['POST'])
@login_required
def api_update_system_config():
    """更新系统配置"""
    config_data = request.json
    success = update_system_config(config_data)
    return jsonify({"success": success, "message": "配置更新成功" if success else "配置更新失败"})

@app.route('/api/plugins/<plugin_name>/reload', methods=['POST'])
@login_required
def api_reload_single_plugin(plugin_name):
    """重新加载单个插件配置"""
    try:
        # 使用导入的全局实例
        name = plugin_name.upper()
        
        if name not in plugin_manager_instance.plugins:
            return jsonify({
                'success': False,
                'message': f'插件 {plugin_name} 不存在'
            })
        
        success = plugin_manager_instance.reload_plugin(name)
        if success:
            return jsonify({
                'success': True,
                'message': f'插件 {plugin_name} 配置已重载'
            })
        else:
            return jsonify({
                'success': False,
                'message': f'插件 {plugin_name} 重载失败'
            })
            
    except Exception as e:
        logger.error(f"重载插件 {plugin_name} 失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'重载插件失败: {str(e)}'
        })

@app.route('/api/plugins/reload', methods=['POST'])
@login_required
def api_reload_plugins():
    """重新加载所有插件"""
    try:
        # 使用导入的全局实例
        # 先加载配置
        plugin_manager_instance.load_config()
        # 扫描和激活插件
        plugin_manager_instance.scan_plugins()
        failed_plugins = plugin_manager_instance.activate_plugins()
        
        if failed_plugins:
            logger.warning(f"以下插件加载失败: {', '.join(failed_plugins)}")
            return jsonify({
                'success': True,
                'partial': True,
                'message': f'插件重载完成，但部分插件加载失败: {", ".join(failed_plugins)}'
            })
        
        logger.info("所有插件已重新加载")
        return jsonify({
            'success': True,
            'message': '所有插件已重新加载'
        })
    except Exception as e:
        logger.error(f"重新加载插件失败: {str(e)}")
        import traceback
        logger.error(traceback.format_exc())
        return jsonify({
            'success': False,
            'message': f'重新加载插件失败: {str(e)}'
        })

@app.route('/api/plugins/restart', methods=['POST'])
@login_required
def api_restart_plugins():
    """重启应用以刷新插件状态"""
    try:
        # 获取重启服务的结果
        success, message = start_run()
        return jsonify({"success": success, "message": message})
    except Exception as e:
        logger.error(f"重启应用失败: {str(e)}")
        return jsonify({"success": False, "message": f"重启应用失败: {str(e)}"})

@app.route('/api/plugins/<plugin_name>/update', methods=['POST'])
@login_required
def api_update_plugin(plugin_name):
    """更新插件"""
    success, message = plugin_manager_instance.update_plugin(plugin_name)
    return jsonify({"success": success, "message": message})

# ============== Socket.IO 事件 ==============
@socketio.on('connect')
def socket_connect():
    """Socket.IO连接事件"""
    if not session.get('logged_in'):
        return False
    emit('response', {'data': '已连接到实时聊天服务'})

@socketio.on('chat_message')
def handle_chat_message(data):
    """处理聊天消息"""
    if not session.get('logged_in'):
        return

    receiver = data.get('receiver')
    group = data.get('group')
    message = data.get('message')
    
    success, msg = send_message(receiver, group, message)
    
    # 将消息添加到历史记录
    if success:
        # 添加消息记录的代码
        pass
    
    # 广播消息给所有连接的客户端
    emit('chat_update', {
        'success': success,
        'message': message,
        'sender': session.get('username'),
        'receiver': receiver,
        'group': group,
        'timestamp': time.time()
    }, broadcast=True)

# 处理微信回调消息的路由
@app.route('/v2/api/callback/collect', methods=['POST'])
def handle_wechat_callback():
    """处理从gewechat服务器接收到的回调消息"""
    try:
        if not request.data:
            return jsonify({"status": "error", "message": "No data received"})
            
        callback_data = request.json
        logger.info(f"Received wechat callback: {callback_data.get('TypeName', 'unknown')}")
        
        # 广播回调消息给所有连接的WebSocket客户端
        if socketio:
            socketio.emit('wechat_callback', callback_data)
            
        # 返回成功响应给gewechat服务器
        return "success"
    except Exception as e:
        logger.error(f"Error handling wechat callback: {str(e)}")
        return jsonify({"status": "error", "message": str(e)})

# 获取联系人信息的API
@app.route('/api/contact_info', methods=['GET'])
@login_required
def api_get_contact_info():
    """获取微信联系人或群聊的详细信息"""
    wxid = request.args.get('wxid')
    if not wxid:
        return jsonify({"success": False, "message": "Missing wxid parameter"})
    
    try:
        # 在这里需要实现从wxid获取联系人名称的逻辑
        # 可能需要调用gewechat的API或者查询本地缓存
        
        # 临时实现：直接返回wxid作为名称
        name = wxid
        
        # 如果是群聊
        if wxid.endswith('@chatroom'):
            # 尝试调用gewechat客户端获取群聊名称
            from channel.gewechat.gewechat_channel import GeWeChatChannel
            channel = GeWeChatChannel()
            
            try:
                group_info = channel.client.get_chatroom_info(wxid)
                if group_info and group_info.get('ret') == 200 and group_info.get('data'):
                    name = group_info['data'].get('nickname', wxid)
            except Exception as e:
                logger.error(f"获取群聊信息失败: {e}")
        
        # 如果是个人联系人
        else:
            # 尝试调用gewechat客户端获取联系人信息
            from channel.gewechat.gewechat_channel import GeWeChatChannel
            channel = GeWeChatChannel()
            
            try:
                contact_info = channel.client.get_contact_info(wxid)
                if contact_info and contact_info.get('ret') == 200 and contact_info.get('data'):
                    name = contact_info['data'].get('nickname', wxid)
            except Exception as e:
                logger.error(f"获取联系人信息失败: {e}")
        
        return jsonify({
            "success": True,
            "data": {
                "wxid": wxid,
                "name": name
            }
        })
    except Exception as e:
        logger.error(f"获取联系人信息出错: {e}")
        return jsonify({"success": False, "message": f"获取联系人信息失败: {str(e)}"})

# ================ 启动应用 ================
if __name__ == "__main__":
    # 启动微信服务
    start_run()
    
    # 设置固定端口，不再从配置中读取
    original_port = 7860
    # 将端口保存到应用配置中，供重启时使用
    app.config['PORT'] = original_port
    logger.info(f"正在启动Web界面，端口 {original_port}...")
    print(f"正在启动Web界面，访问地址: http://localhost:{original_port}")
    
    # 添加重启监测循环
    while True:
        # 启动Flask应用
        socketio.run(app, host="0.0.0.0", port=original_port, debug=False, allow_unsafe_werkzeug=True)
        
        # 检查是否需要重启
        if restart_flask_server:
            logger.info("检测到重启标志，准备重启Flask服务器...")
            restart_flask_server = False  # 重置标志
            time.sleep(2)  # 给一些时间让旧服务器关闭
            continue
        else:
            break  # 如果不是由重启标志触发的退出，则退出循环 