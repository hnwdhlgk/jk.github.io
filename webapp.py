"""
Web 管理后台 + Telegram Webhook（Flask）
提供浏览器界面管理关键词、转发配置和命中记录，
同时通过 Webhook 模式接收 Telegram 消息更新。
与 Telegram bot 共享同一个 DataStore。
"""
import os
import asyncio
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
    jsonify,
)

from telegram import Update

logger = logging.getLogger(__name__)


def create_app(data_store, admin_password: str = None, bot_token: str = None):
    """创建 Flask 应用（含 Web 管理后台和 Telegram Webhook）。

    Args:
        data_store: 共享的 DataStore 实例
        admin_password: 管理员登录密码，为 None 时从环境变量读取或随机生成
        bot_token: Telegram bot token
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

    # Bot Token
    if bot_token is None:
        bot_token = os.environ.get("TELEGRAM_BOT_TOKEN", "")
    app.config["BOT_TOKEN"] = bot_token

    store = data_store

    # ============ Telegram Bot 初始化（Webhook 模式） ============
    tg_application = None
    if bot_token:
        try:
            from bot import create_application
            tg_application = create_application(bot_token)
            # 初始化 application（不启动 polling）
            asyncio.run(tg_application.initialize())
            logger.info("Telegram bot 已初始化（Webhook 模式）")

            # 如果设置了 WEBHOOK_URL 环境变量，自动设置 webhook
            webhook_url = os.environ.get("WEBHOOK_URL", "")
            if webhook_url:
                async def _set_webhook():
                    await tg_application.bot.set_webhook(
                        url=f"{webhook_url.rstrip('/')}/webhook/{bot_token}"
                    )
                asyncio.run(_set_webhook())
                logger.info("Webhook 已设置为：%s/webhook/%s", webhook_url.rstrip('/'), bot_token)
        except Exception as e:
            logger.error("初始化 Telegram bot 失败：%s", e)
            tg_application = None
    else:
        logger.warning("未设置 TELEGRAM_BOT_TOKEN，Telegram bot 功能不可用")

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
        if data.chat_title:
            return f"{data.chat_title} ({chat_id})"
        return chat_id

    def safe_int(value: str) -> bool:
        try:
            int(value)
            return True
        except (ValueError, TypeError):
            return False

    # ============ Telegram Webhook 端点 ============
    @app.route("/webhook/<token>", methods=["POST"])
    def telegram_webhook(token):
        """接收 Telegram 推送的消息更新。"""
        if token != app.config["BOT_TOKEN"]:
            abort(403)
        if tg_application is None:
            abort(503, description="Bot not initialized")

        try:
            data = request.get_json(force=True)
            update = Update.de_json(data, tg_application.bot)
            # 在新的事件循环中处理更新
            asyncio.run(tg_application.process_update(update))
            return jsonify({"ok": True})
        except Exception as e:
            logger.error("处理 webhook 更新失败：%s", e)
            return jsonify({"ok": False, "error": str(e)}), 500

    @app.route("/webhook/status")
    def webhook_status():
        """查看 webhook 状态（公开访问，方便排查）。"""
        info = {
            "bot_initialized": tg_application is not None,
            "bot_token_set": bool(app.config["BOT_TOKEN"]),
        }
        if tg_application is not None:
            try:
                wh_info = asyncio.run(tg_application.bot.get_webhook_info())
                info["webhook_url"] = wh_info.url
                info["pending_update_count"] = wh_info.pending_update_count
                info["last_error"] = wh_info.last_error_message
            except Exception as e:
                info["webhook_error"] = str(e)
        return jsonify(info)

    @app.route("/set-webhook")
    @login_required
    def set_webhook_page():
        """设置 webhook 的页面（需登录）。"""
        webhook_url = os.environ.get("WEBHOOK_URL", "")
        current_wh = ""
        if tg_application is not None:
            try:
                wh_info = asyncio.run(tg_application.bot.get_webhook_info())
                current_wh = wh_info.url or ""
            except Exception:
                pass
        return render_template(
            "webhook.html",
            webhook_url=webhook_url,
            current_webhook=current_wh,
            bot_token=app.config["BOT_TOKEN"],
        )

    @app.route("/set-webhook", methods=["POST"])
    @login_required
    def set_webhook_action():
        """设置 webhook URL。"""
        if tg_application is None:
            flash("Bot 未初始化，无法设置 webhook。", "error")
            return redirect(url_for("set_webhook_page"))

        url = request.form.get("webhook_url", "").strip()
        if not url:
            flash("请输入 webhook URL。", "error")
            return redirect(url_for("set_webhook_page"))

        try:
            full_url = f"{url.rstrip('/')}/webhook/{app.config['BOT_TOKEN']}"
            asyncio.run(tg_application.bot.set_webhook(url=full_url))
            flash(f"Webhook 已设置为：{full_url}", "success")
        except Exception as e:
            flash(f"设置 webhook 失败：{e}", "error")

        return redirect(url_for("set_webhook_page"))

    @app.route("/delete-webhook", methods=["POST"])
    @login_required
    def delete_webhook():
        """删除 webhook，切回 polling 模式（如果需要）。"""
        if tg_application is not None:
            try:
                asyncio.run(tg_application.bot.delete_webhook())
                flash("Webhook 已删除。", "success")
            except Exception as e:
                flash(f"删除 webhook 失败：{e}", "error")
        return redirect(url_for("set_webhook_page"))

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


# ============ 直接运行入口（本地开发用） ============
if __name__ == "__main__":
    from bot import store, BOT_TOKEN, ADMIN_PASSWORD, WEB_HOST, WEB_PORT

    app = create_app(store, admin_password=ADMIN_PASSWORD, bot_token=BOT_TOKEN)
    logger.info("Web 管理后台 + Telegram Webhook 启动中...")
    logger.info("访问 http://%s:%d", WEB_HOST, WEB_PORT)
    app.run(host=WEB_HOST, port=WEB_PORT, debug=False, use_reloader=False)
