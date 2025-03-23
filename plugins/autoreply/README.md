# 目的
关键字匹配并回复

# 试用场景
目前是在微信公众号下面使用过。

# 使用步骤
1. 复制 `config.json.template` 为 `config.json`
2. 在关键字 `keyword` 新增需要关键字匹配的内容
3. 重启程序做验证

# 验证结果
![结果](test-keyword.png)

# 功能说明
1. 支持两种关键字匹配模式：
   - exact: 精确匹配（默认模式）
   - contains: 包含匹配

2. 支持多关键字共享回复：
   - 可以为一组关键字配置相同的回复内容
   - 如果一个关键字匹配到多个回复，会逐个发送所有回复

3. 支持多种类型的回复：
   - 文本消息：普通文本内容
   - 图片：支持.jpg、.webp、.jpeg、.png、.gif、.img格式的图片URL
   - 视频：支持.mp4格式的视频URL
   - 文件：支持.pdf、.doc、.docx、.xls、.xlsx、.zip、.rar格式的文件URL
   - 混合类型：支持在一个回复中包含多种类型的内容

# 配置示例
```json
{
    "keyword": {
        "问候语": {
            "keywords": ["你好", "hello", "hi"],
            "match_type": "exact",
            "reply": "你好！很高兴见到你"
        },
        "天气": {
            "keywords": ["天气怎么样", "查天气"],
            "match_type": "contains",
            "reply": "今天天气不错！"
        },
        "图片示例": {
            "keywords": ["图片"],
            "match_type": "contains",
            "reply": "https://example.com/image.jpg"
        },
        "多类型回复": {
            "keywords": ["资料"],
            "match_type": "contains",
            "reply": [
                "这是一份完整的资料包：",
                "https://example.com/image.jpg",
                "https://example.com/document.pdf",
                "https://example.com/video.mp4"
            ]
        }
    }
}
```

# 插件化说明
本项目已支持插件化开发，详细信息请参考[开发说明.md](开发说明.md)文件。插件化具有以下优势：

1. 模块化设计：将功能解耦，便于维护和扩展
2. 灵活配置：每个插件可以独立配置和管理
3. 优先级控制：可以自由调整插件的处理顺序
4. 独立开发：支持在独立仓库中开发和维护插件