#!/bin/bash
# 查看日志文件

if [ $# -eq 0 ]; then
    echo "可用日志文件:"
    ls -l logs/*.log | awk '{print NR, $9}'
    echo ""
    echo "用法: ./tail_log.sh [文件名] [行数]"
    echo "示例: ./tail_log.sh admin_ui.log 50"
    echo "或直接指定序号: ./tail_log.sh 1 50"
    echo ""
    echo "默认显示管理界面日志:"
    tail -f logs/admin_ui.log -n 50
    exit 0
fi

# 获取日志文件
LOG_FILE=$1
if [[ "$LOG_FILE" =~ ^[0-9]+$ ]]; then
    # 如果输入的是数字，则按序号选择文件
    LOG_FILE=$(ls -1 logs/*.log | sed -n "${LOG_FILE}p")
    if [ -z "$LOG_FILE" ]; then
        echo "无效的日志序号"
        exit 1
    fi
elif [[ "$LOG_FILE" != logs/* ]]; then
    # 如果输入的不是logs/开头的文件，则添加前缀
    LOG_FILE="logs/$LOG_FILE"
fi

# 获取行数，默认50行
LINES=50
if [ $# -ge 2 ]; then
    LINES=$2
fi

# 检查文件是否存在
if [ ! -f "$LOG_FILE" ]; then
    echo "日志文件 $LOG_FILE 不存在"
    exit 1
fi

# 查看日志
echo "正在查看 $LOG_FILE 的最后 $LINES 行..."
tail -f "$LOG_FILE" -n $LINES

