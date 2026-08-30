"""
WSGI 入口文件（PythonAnywhere 部署用）
PythonAnywhere 的 Web 配置中，WSGI 文件路径指向此文件。
"""
import sys
import os

# 项目路径（根据实际情况修改，PythonAnywhere 通常是 /home/你的用户名/项目名）
# 这里用相对路径，假设 wsgi.py 在项目根目录
project_home = os.path.dirname(os.path.abspath(__file__))
if project_home not in sys.path:
    sys.path.insert(0, project_home)

# 设置环境变量（也可以在 PythonAnywhere 的 Web 配置中设置）
# os.environ.setdefault("TELEGRAM_BOT_TOKEN", "你的BotToken")
# os.environ.setdefault("ADMIN_PASSWORD", "你的后台密码")
# os.environ.setdefault("WEBHOOK_URL", "https://你的用户名.pythonanywhere.com")

from bot import store, BOT_TOKEN, ADMIN_PASSWORD
from webapp import create_app

# 创建 Flask 应用（同时作为 WSGI application 和 Telegram webhook 接收端）
application = create_app(store, admin_password=ADMIN_PASSWORD, bot_token=BOT_TOKEN)
