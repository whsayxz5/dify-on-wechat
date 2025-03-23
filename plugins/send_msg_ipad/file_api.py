from urllib.parse import unquote
from flask import Flask, request, jsonify, send_from_directory
import json
from common.log import logger
import threading
import os
from common.tmp_dir import TmpDir

app = Flask(__name__, static_folder='static')

@app.route('/')
def index():
    return send_from_directory(app.static_folder, 'index.html')

@app.route('/get_contacts', methods=['GET'])
def get_contacts():
    try:
        tmp_dir = TmpDir().path()
        friend_list_file = os.path.join(tmp_dir, "contact_friend.json")
        chatroom_list_file = os.path.join(tmp_dir, "contact_room.json")
        
        friends = []
        groups = []
        
        if os.path.exists(friend_list_file):
            with open(friend_list_file, 'r', encoding='utf-8') as f:
                friend_list = json.load(f)
                for friend in friend_list:
                    if friend.get("remark"):
                        friends.append(friend["remark"])
                    else:
                        friends.append(friend["nickName"])
                
        if os.path.exists(chatroom_list_file):
            with open(chatroom_list_file, 'r', encoding='utf-8') as f:
                chatroom_list = json.load(f)
                for chatroom in chatroom_list:
                    if chatroom.get("nickName"):
                        groups.append(chatroom["nickName"])
        
        return jsonify({
            'status': 'success',
            'data': {
                'friends': friends,
                'groups': groups
            }
        })
    except Exception as e:
        logger.error(f"获取联系人列表失败: {str(e)}")
        return jsonify({'status': 'error', 'message': '获取联系人列表失败'}), 500


def validate_data(data_list):
    if not isinstance(data_list, list):
        raise ValueError('data_list必须为列表类型')
    if not data_list:
        raise ValueError('data_list不能为空')
    for data in data_list:
        if not isinstance(data, dict):
            raise ValueError('data_list的每个元素必须为字典类型')
        if 'message' not in data:
            raise ValueError('每个消息必须包含message')


@app.route('/send_message', methods=['POST'])
def send_message():
    try:
        data_list = request.json.get('data_list', [])
        
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

        try:
            validate_data(data_list)
        except ValueError as e:
            return jsonify({'status': 'error', 'message': str(e)}), 400

        curdir = os.path.dirname(__file__)
        config_path = os.path.join(curdir, "data.json")
        with open(config_path, 'w', encoding='utf-8') as file:
            json.dump(data_list, file, ensure_ascii=False)
        logger.info(f"写入成功,写入内容{data_list}")

        return jsonify({'status': 'success', 'message': '发送成功'}), 200
    except Exception as e:
        logger.error(f"处理请求时发生错误: {str(e)}")
        return jsonify({'status': 'error', 'message': '服务器内部错误'}), 500


class FileWriter:
    def __init__(self):
        super().__init__()
        self.flask_thread = threading.Thread(target=self.run_flask_app)
        self.flask_thread.start()

    def run_flask_app(self):
        app.run(host='0.0.0.0', port=5688, debug=False)
