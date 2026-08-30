"""
Web 管理后台（Flask）
提供浏览器界面管理关键词、转发配置和命中记录。
与 Telegram bot 共享同一个 DataStore。
"""

import os
import secrets
import logging
from functools import wraps
from urllib.parse import urlparse

from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    session,
    flash,
    abort,
)

logger = logging.getLogger(__name__)


def create_app(data_store, admin_password: str = None, bot_token: str = None):
    """创建 Flask 应用。

    Args:
        data_store: 共享的 DataStore 实例
        admin_password: 管理员登录密码，为 None 时从环境变量读取或随机生成
        bot_token: Telegram bot token，用于通过 API 获取群组名称等（可选）
    """
    app = Flask(
        __name__,
        template_folder=os.path.join(os.path.dirname(__file__), "templates"),
        static_folder=os.path.join(os.path.dirname(__file__), "static"),
    )
    app.secret_key = os.environ.get("FLASK_SECRET_KEY", secrets.token_hex(32))

    # 确定管理员密码
    if admin_password is None:
        admin_password = os.environ.get("ADMIN_PASSWORD", "")
    if not admin_password:
        admin_password = secrets.token_urlsafe(8)
        logger.info("=" * 60)
        logger.info("未设置 ADMIN_PASSWORD，已自动生成管理员密码：")
        logger.info("  密码：%s", admin_password)
        logger.info("  请妥善保存，或设置环境变量 ADMIN_PASSWORD 自定义密码")
        logger.info("=" * 60)
    app.config["ADMIN_PASSWORD"] = admin_password
    app.config["BOT_TOKEN"] = bot_token

    store = data_store

    # ============ 登录装饰器 ============
    def login_required(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            if not session.get("logged_in"):
                return redirect(url_for("login", next=request.path))
            return f(*args, **kwargs)
        return decorated_function

    # ============ 工具函数 ============
    def get_chat_display(chat_id: str, data) -> str:
        """获取聊天的显示名称。"""
        if data.chat_title:
            return f"{data.chat_title} ({chat_id})"
        return chat_id

    def safe_int(value: str) -> bool:
        """检查字符串是否为合法的 chat_id（整数，可选负号）。"""
        try:
            int(value)
            return True
        except (ValueError, TypeError):
            return False

    # ============ 路由 ============
    @app.route("/")
    def index():
        if session.get("logged_in"):
            return redirect(url_for("chat_list"))
        return redirect(url_for("login"))

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            password = request.form.get("password", "")
            if password == app.config["ADMIN_PASSWORD"]:
                session["logged_in"] = True
                session.permanent = True
                next_page = request.args.get("next", "")
                # 防止开放重定向
                if next_page and urlparse(next_page).netloc == "":
                    return redirect(next_page)
                return redirect(url_for("chat_list"))
            flash("密码错误，请重试。", "error")
        return render_template("login.html")

    @app.route("/logout")
    def logout():
        session.clear()
        flash("已退出登录。", "success")
        return redirect(url_for("login"))

    @app.route("/chats")
    @login_required
    def chat_list():
        all_chats = store.get_all()
        # 按最近命中时间排序
        chat_items = []
        for cid, data in all_chats.items():
            last_hit = data.history[0]["time"] if data.history else "无"
            chat_items.append({
                "chat_id": cid,
                "title": data.chat_title or "未命名",
                "keyword_count": len(data.keywords),
                "history_count": len(data.history),
                "forward_to": data.forward_to,
                "last_hit": last_hit,
            })
        chat_items.sort(key=lambda x: x["last_hit"], reverse=True)
        return render_template("chat_list.html", chats=chat_items)

    @app.route("/chats/add", methods=["POST"])
    @login_required
    def chat_add():
        chat_id = request.form.get("chat_id", "").strip()
        title = request.form.get("title", "").strip() or None
        if not chat_id or not safe_int(chat_id):
            flash("请输入有效的聊天 ID（数字）。", "error")
            return redirect(url_for("chat_list"))
        store.ensure_chat(chat_id, title)
        flash(f"已添加聊天 {chat_id}。", "success")
        return redirect(url_for("chat_detail", chat_id=chat_id))

    @app.route("/chats/<chat_id>")
    @login_required
    def chat_detail(chat_id):
        if not safe_int(chat_id):
            abort(404)
        data = store.get(chat_id)
        display_name = get_chat_display(chat_id, data)
        return render_template(
            "chat_detail.html",
            chat_id=chat_id,
            display_name=display_name,
            data=data,
        )

    # ---- 关键词管理 ----
    @app.route("/chats/<chat_id>/keywords/add", methods=["POST"])
    @login_required
    def keyword_add(chat_id):
        keyword = request.form.get("keyword", "").strip()
        if not keyword:
            flash("关键词不能为空。", "error")
        elif store.add_keyword(chat_id, keyword):
            flash(f"已添加关键词：{keyword}", "success")
        else:
            flash(f"关键词「{keyword}」已存在或无效。", "error")
        return redirect(url_for("chat_detail", chat_id=chat_id))

    @app.route("/chats/<chat_id>/keywords/<keyword>/delete", methods=["POST"])
    @login_required
    def keyword_delete(chat_id, keyword):
        if store.remove_keyword(chat_id, keyword):
            flash(f"已删除关键词：{keyword}", "success")
        else:
            flash("删除失败，关键词不存在。", "error")
        return redirect(url_for("chat_detail", chat_id=chat_id))

    # ---- 转发配置 ----
    @app.route("/chats/<chat_id>/forward/set", methods=["POST"])
    @login_required
    def forward_set(chat_id):
        target = request.form.get("forward_to", "").strip()
        if not target:
            store.clear_forward(chat_id)
            flash("已清除转发目标。", "success")
        elif not safe_int(target):
            flash("转发目标 ID 格式不正确（应为数字）。", "error")
        else:
            store.set_forward(chat_id, target)
            flash(f"已设置转发目标：{target}", "success")
        return redirect(url_for("chat_detail", chat_id=chat_id))

    @app.route("/chats/<chat_id>/forward/clear", methods=["POST"])
    @login_required
    def forward_clear(chat_id):
        store.clear_forward(chat_id)
        flash("已清除转发目标。", "success")
        return redirect(url_for("chat_detail", chat_id=chat_id))

    # ---- 命中记录 ----
    @app.route("/chats/<chat_id>/history/clear", methods=["POST"])
    @login_required
    def history_clear(chat_id):
        store.clear_history(chat_id)
        flash("已清空命中记录。", "success")
        return redirect(url_for("chat_detail", chat_id=chat_id))

    # ============ 错误处理 ============
    @app.errorhandler(404)
    def page_not_found(e):
        return render_template("login.html", error="页面不存在"), 404

    return app
