# file_api服务

## 简介
此项目  在 [仓库地址](https://github.com/Isaac20231231/send_msg) 基础上调整
     
支持 ipad 协议
itchat和ntchat和ipad 

首次安装后需要  执行执行   更新群成员\和更新好友列表
如
<img src="update_list.jpg" width="600" >

当群成员或者好友列表有更改时 请执行  更新群成员\和更新好友列表 刷新通讯录信息

最好配合定时任务 每天执行一次


`file_api` 插件用于[chatgpt-on-wechat](https://github.com/hanfangyuan4396/dify-on-wechat)项目。<br>
实现手动发送消息通知到微信功能，写入json消息数据到data.jaon文件里，

## python版本

python3.11 目前发现有低版本不兼容的问题，建议使用大于3.10版本


## 安装

此插件作为微信聊天机器人系统的一部分，需要将其放置在正确的插件目录下：

### 安装方法（三种方式）

下载插件,访问插件[仓库地址](https://github.com/wang-zhibo/send_msg)

#### 第一种:手动下载压缩包,将`send_msg` 文件夹复制到您的聊天机器人的 `plugins` 目录中（注意需要修改文件夹名称，会自动带上main分支）。

#### 第二种:微信执行命令

   ```sh
   #installp https://github.com/wang-zhibo/send_msg_ipad.git
   #scanp
   ```

#### 第三种:进入`plugins` 目录克隆

```sh
git clone https://github.com/wang-zhibo/send_msg_ipad.git
```

### 注意事项

1. 确保 `__init__.py`,`file_api.py`和`send_msg.py` 文件位于 `send_msg` 文件夹中。
2. 安装插件相关依赖 `pip install -r requirements.txt`。

```sh
cd plugins/send_msg
pip install -r requirements.txt
```

## data.json文件介绍

`file_api` 服务数据依赖于 `data.json` 文件进行写入。

   ```data.json
 {
  "data_list":[
  {
    "receiver_name": ["微信备注名1"],
    "message": "发送消息",
    "group_name": []
  },
  {
    "receiver_name": ["微信备注名1","微信备注名2"],
    "message": "发送消息",
    "group_name": []
  },
  {
    "receiver_name": [],
    "message": "发送消息",
    "group_name": ["群名1","群名2"]
  },
  {
    "receiver_name": ["微信备注名1"],
    "message": "发送消息",
    "group_name": ["群名1","群名2"]
  }
  ]
}
   ```

### 参数说明:

    - `receiver_name`: 接收者的微信备注名，可以是多个
    - `message`: 消息内容
    - `group_name`: 群聊名称，可以是多个

发送个人消息时，`group_name`为空，填写`receiver_name`,`message`即可。多个时列表逗号分隔即可<br>
发送群聊消息时，`group_name`,`message`必填,`receiver_name`可选<br>
填写`微信备注名`时(支持多个)，发送@某人消息，填写`所有人`发送@所有人消息,不填写不@。

## 使用

安装并正确配置插件后，您可以通过以下方式使用：<br>
打开postman，请求api接口"http://127.0.0.1:5688/send_message"<br>
注意:
127.0.0.1是本机ip，如果是部署服务器要改成服务器ip地址，5688是端口号，如果修改了端口号要改成对应的端口号（端口号可以在run_fastapi_app()
修改端口启动）
发送消息到微信

```json
{
  "receiver_name": ["微信备注名1"],
  "message": "这是一条测试消息",
  "group_name": []
}
```

成功返回：

```json
{
  "message": "发送成功",
  "status": "success"
}
```
异常返回参考send_msg.py文件里的validate_data函数
<img src="API截图.png" width="600" >
<img src="微信消息截图.png" width="600">

# send_msg插件介绍

## 注意事项
发送个人消息时，一定要有好友关系，否则无法发送消息。<br>
发送群聊消息时，如果出现找不到群聊的情况，要把微信群聊设置成通讯录群聊。

## 第一种使用

send_msg.py插件采用watchdog监听文件变化，和file_api服务相互使用，<br>
file_api负责写入文件，send_msg负责监听文件，有内容时触发发送消息到微信。

### 命令说明

send_msg支持以下命令：

- `$start watchdog` 开启监听
- `$stop watchdog` 停止监听
- `$check watchdog` 查看监听状态

<img src="文件监听命令示例.png" width="600">

### 使用方法

插件默认不启动监听，需要手动启动监听，监听文件为data.json文件，当data.json文件有内容时，触发发送消息到微信。
启动方式看上方,成功效果如下
<img src="监听文件效果.png" width="600">

## 第二种使用

send_msg.py插件可以使用微信命令来发送消息到微信，不需要file_api服务，<br>
发送消息分两种方式，一种是发送个人消息，一种是发送群聊消息。

### 命令说明

send_msg支持以下命令(支持一次性发多人,单人时列表只填一个即可)：

- `$send_msg [微信备注名1,微信备注名2] 消息内容` 发送个人消息
- `$send_msg [微信备注名1,微信备注名2] 消息内容 group[群聊名称1,群聊名称2]` 发送群聊消息,并且@某人
- `$send_msg [所有人] 消息内容 group[群聊名称1,群聊名称2]` 发送群聊消息,并且@所有人
- `$send_msg [] 消息内容 group[群聊名称1,群聊名称2]` 发送群聊消息，不@任何人 注意:$send_msg后面是2个空格
  <img src="微信发送消息命令示例.png" width="600">
  <img src="微信命令发送消息成功示例.png" width="600">

## 更新日志
### V2.3 （2024-09-05）
- 1.增加channel判断，兼容win版本机器人的ntchat发送消息（https://github.com/Tishon1532/chatgpt-on-wechat-win），
- 支持itchat和ntchat两种channel类型，注意ntchat目前还没解决群聊@所有人的场景，只能@单个人，另外ntchat的receiver_name只支持填写微信名字

