"""
WSGI 入口文件
- 本地运行 / PythonAnywhere 部署：直接使用
- Vercel 部署：作为 Serverless Function 入口（vercel.json 中配置）

Vercel 无服务器环境注意事项：
- 文件系统只读，仅 /tmp 可写，数据文件放在 /tmp
- 冷启动时 /tmp 数据会清空，因此支持从环境变量加载初始配置
- 环境变量 INITIAL_KEYWORDS：逗号分隔的初始关键词，冷启动时自动加载
- 环境变量 DEFAULT_CHAT_ID：默认群组 ID，用于加载初始关键词和转发配置
"""
import sys
import os

# 项目路径
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 检测是否在 Vercel 环境中运行
IS_VERCEL = os.environ.get("VERCEL", "") == "1" or os.path.exists("/var/task")

# Vercel 环境下，数据文件放在 /tmp（唯一可写目录）
if IS_VERCEL:
    os.environ.setdefault("BOT_DATA_FILE", "/tmp/bot_data.json")

from bot import store, BOT_TOKEN, ADMIN_PASSWORD
from webapp import create_app


def load_initial_config():
    """从环境变量加载初始配置（Vercel 冷启动后恢复关键词等配置）。"""
    default_chat_id = os.environ.get("DEFAULT_CHAT_ID", "")
    if not default_chat_id:
        return

    # 确保群组存在
    store.ensure_chat(default_chat_id)

    # 初始关键词：INITIAL_KEYWORDS=关键词1,关键词2,关键词3
    initial_keywords = os.environ.get("INITIAL_KEYWORDS", "")
    if initial_keywords:
        keywords = [kw.strip() for kw in initial_keywords.split(",") if kw.strip()]
        for kw in keywords:
            store.add_keyword(default_chat_id, kw)

    # 初始转发目标：INITIAL_FORWARD_TO=目标chat_id
    initial_forward = os.environ.get("INITIAL_FORWARD_TO", "")
    if initial_forward:
        store.set_forward(default_chat_id, initial_forward)


# Vercel 环境下加载初始配置
if IS_VERCEL:
    try:
        load_initial_config()
    except Exception as e:
        import logging
        logging.getLogger(__name__).warning("加载初始配置失败：%s", e)

# 创建 Flask 应用（同时作为 WSGI application 和 Telegram webhook 接收端）
application = create_app(store, admin_password=ADMIN_PASSWORD, bot_token=BOT_TOKEN)
