"""
Telegram 关键词监控机器人
功能：加入群组后实时监听消息，命中预设关键词时自动提醒并记录。
依赖：python-telegram-bot>=20.0
"""

import json
import os
import logging
import threading
from datetime import datetime
from dataclasses import dataclass, field, asdict
from typing import Dict, List, Optional

from telegram import Update, Message
from telegram.ext import (
    Application,
    CommandHandler,
    MessageHandler,
    filters,
    ContextTypes,
)

# ============ 配置 ============
BOT_TOKEN = os.environ.get("TELEGRAM_BOT_TOKEN", "")
DATA_FILE = os.environ.get("BOT_DATA_FILE", "bot_data.json")
MAX_HISTORY_PER_CHAT = 200  # 每个群组最多保留的命中记录数

# Web 后台配置
WEB_ENABLED = os.environ.get("WEB_ENABLED", "1") != "0"
WEB_HOST = os.environ.get("WEB_HOST", "0.0.0.0")
WEB_PORT = int(os.environ.get("WEB_PORT", "8080"))
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "")

logging.basicConfig(
    format="%(asctime)s - %(name)s - %(levelname)s - %(message)s",
    level=logging.INFO,
)
logger = logging.getLogger(__name__)


# ============ 数据模型 ============
@dataclass
class ChatData:
    keywords: List[str] = field(default_factory=list)
    history: List[Dict] = field(default_factory=list)  # 命中记录
    forward_to: Optional[str] = None  # 命中后转发的目标 chat_id
    chat_title: Optional[str] = None  # 群组/聊天名称（用于 Web 后台显示）


class DataStore:
    """基于 JSON 文件的简单持久化存储（线程安全）。"""

    def __init__(self, filepath: str):
        self.filepath = filepath
        self.chats: Dict[str, ChatData] = {}
        self.lock = threading.Lock()
        self._load()

    def _load(self):
        if os.path.exists(self.filepath):
            try:
                with open(self.filepath, "r", encoding="utf-8") as f:
                    raw = json.load(f)
                for chat_id, data in raw.items():
                    self.chats[chat_id] = ChatData(
                        keywords=data.get("keywords", []),
                        history=data.get("history", []),
                        forward_to=data.get("forward_to"),
                        chat_title=data.get("chat_title"),
                    )
                logger.info("已加载 %d 个群组的数据", len(self.chats))
            except Exception as e:
                logger.error("加载数据文件失败: %s", e)
                self.chats = {}

    def _save(self):
        raw = {cid: asdict(data) for cid, data in self.chats.items()}
        tmp = self.filepath + ".tmp"
        with open(tmp, "w", encoding="utf-8") as f:
            json.dump(raw, f, ensure_ascii=False, indent=2)
        os.replace(tmp, self.filepath)

    def get(self, chat_id: str) -> ChatData:
        with self.lock:
            if chat_id not in self.chats:
                self.chats[chat_id] = ChatData()
            return self.chats[chat_id]

    def get_all(self) -> Dict[str, ChatData]:
        """获取所有聊天数据的副本（用于 Web 后台展示）。"""
        with self.lock:
            return dict(self.chats)

    def update_chat_title(self, chat_id: str, title: str):
        """更新聊天名称（bot 收到消息时自动调用）。"""
        with self.lock:
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            if data.chat_title != title:
                data.chat_title = title
                self._save()

    def add_keyword(self, chat_id: str, keyword: str) -> bool:
        with self.lock:
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            keyword = keyword.strip()
            if not keyword or keyword in data.keywords:
                return False
            data.keywords.append(keyword)
            self._save()
            return True

    def remove_keyword(self, chat_id: str, keyword: str) -> bool:
        with self.lock:
            data = self.chats.get(chat_id)
            if not data:
                return False
            keyword = keyword.strip()
            if keyword in data.keywords:
                data.keywords.remove(keyword)
                self._save()
                return True
            return False

    def record_hit(self, chat_id: str, record: Dict):
        with self.lock:
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            data.history.insert(0, record)
            if len(data.history) > MAX_HISTORY_PER_CHAT:
                data.history = data.history[:MAX_HISTORY_PER_CHAT]
            self._save()

    def clear_history(self, chat_id: str):
        with self.lock:
            data = self.chats.get(chat_id)
            if data:
                data.history.clear()
                self._save()

    def set_forward(self, chat_id: str, target_chat_id: str) -> bool:
        with self.lock:
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            target_chat_id = target_chat_id.strip()
            if not target_chat_id:
                return False
            data.forward_to = target_chat_id
            self._save()
            return True

    def clear_forward(self, chat_id: str):
        with self.lock:
            data = self.chats.get(chat_id)
            if data:
                data.forward_to = None
                self._save()

    def ensure_chat(self, chat_id: str, title: Optional[str] = None) -> ChatData:
        """确保聊天存在，用于 Web 后台手动添加群组。"""
        with self.lock:
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData(chat_title=title)
                self.chats[chat_id] = data
                self._save()
            elif title and data.chat_title != title:
                data.chat_title = title
                self._save()
            return data


store = DataStore(DATA_FILE)


# ============ 工具函数 ============
async def is_admin(update: Update, context: ContextTypes.DEFAULT_TYPE) -> bool:
    """判断发送者是否为群组管理员或机器人所有者（私聊中默认可用）。"""
    chat = update.effective_chat
    user = update.effective_user
    if chat.type == "private":
        return True
    try:
        member = await chat.get_member(user.id)
        return member.status in ("administrator", "creator")
    except Exception:
        return False


def find_matched_keywords(text: str, keywords: List[str]) -> List[str]:
    """在文本中查找命中的关键词（不区分大小写）。"""
    if not text:
        return []
    text_lower = text.lower()
    return [kw for kw in keywords if kw.lower() in text_lower]


def format_sender(message: Message) -> str:
    """格式化发送者显示名。"""
    user = message.from_user
    if not user:
        return "未知用户"
    name = user.full_name or user.username or str(user.id)
    if user.username:
        return f"{name} (@{user.username})"
    return name


# ============ 命令处理 ============
async def cmd_start(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat = update.effective_chat
    text = (
        "👋 我是关键词监控机器人。\n\n"
        "把我加入群组后，我会实时监听消息，命中预设关键词时自动提醒，并可转发到指定聊天。\n\n"
        "📋 可用命令：\n"
        "  /add <关键词>    — 添加监控关键词（管理员）\n"
        "  /remove <关键词> — 删除监控关键词（管理员）\n"
        "  /list             — 查看当前关键词列表\n"
        "  /history          — 查看最近命中记录\n"
        "  /clear            — 清空命中记录（管理员）\n"
        "  /getid            — 获取当前聊天的 ID（用于设置转发目标）\n"
        "  /set_forward <ID> — 设置命中后转发的目标聊天（管理员）\n"
        "  /forward_info     — 查看当前转发配置\n"
        "  /clear_forward    — 清除转发目标（管理员）\n\n"
        "💡 提示：在群组中使用前，请先将我设为管理员，确保我能读取消息。"
    )
    await update.message.reply_text(text)


async def cmd_add(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ 只有群组管理员可以添加关键词。")
        return

    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("📝 用法：/add <关键词>\n例如：/add 优惠活动")
        return

    chat_id = str(update.effective_chat.id)
    if store.add_keyword(chat_id, keyword):
        await update.message.reply_text(f"✅ 已添加监控关键词：「{keyword}」")
    else:
        await update.message.reply_text(f"ℹ️ 关键词「{keyword}」已存在或无效。")


async def cmd_remove(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ 只有群组管理员可以删除关键词。")
        return

    keyword = " ".join(context.args).strip()
    if not keyword:
        await update.message.reply_text("📝 用法：/remove <关键词>")
        return

    chat_id = str(update.effective_chat.id)
    if store.remove_keyword(chat_id, keyword):
        await update.message.reply_text(f"🗑️ 已删除关键词：「{keyword}」")
    else:
        await update.message.reply_text(f"❌ 未找到关键词：「{keyword}」")


async def cmd_list(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    data = store.get(chat_id)
    if not data.keywords:
        await update.message.reply_text("📭 当前没有监控关键词。使用 /add <关键词> 添加。")
        return
    lines = [f"📋 当前监控的关键词（共 {len(data.keywords)} 个）："]
    for i, kw in enumerate(data.keywords, 1):
        lines.append(f"  {i}. {kw}")
    await update.message.reply_text("\n".join(lines))


async def cmd_history(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    data = store.get(chat_id)
    if not data.history:
        await update.message.reply_text("📭 暂无关键词命中记录。")
        return

    show = data.history[:20]
    lines = [f"📊 最近命中记录（共 {len(data.history)} 条，显示最近 {len(show)} 条）：\n"]
    for i, rec in enumerate(show, 1):
        time_str = rec.get("time", "?")
        keyword = rec.get("keyword", "?")
        sender = rec.get("sender", "?")
        preview = rec.get("preview", "")
        lines.append(f"{i}. [{time_str}] 关键词「{keyword}」— {sender}")
        if preview:
            lines.append(f"   内容：{preview}")
    await update.message.reply_text("\n".join(lines))


async def cmd_clear(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ 只有群组管理员可以清空记录。")
        return
    chat_id = str(update.effective_chat.id)
    store.clear_history(chat_id)
    await update.message.reply_text("🗑️ 已清空所有命中记录。")


async def cmd_getid(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """获取当前聊天的 ID，方便用户设置转发目标。"""
    chat = update.effective_chat
    chat_type_map = {
        "private": "私聊",
        "group": "群组",
        "supergroup": "超级群组",
        "channel": "频道",
    }
    chat_type = chat_type_map.get(chat.type, chat.type)
    title = chat.title or chat.full_name or "未命名"
    text = (
        f"🆔 当前聊天信息\n"
        f"  名称：{title}\n"
        f"  类型：{chat_type}\n"
        f"  ID：`{chat.id}`\n\n"
        f"💡 复制上面的 ID，在监控群组中发送 /set_forward <ID> 即可将命中消息转发到这里。"
    )
    await update.message.reply_text(text, parse_mode="Markdown")


async def cmd_set_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ 只有群组管理员可以设置转发目标。")
        return

    target = " ".join(context.args).strip()
    if not target:
        await update.message.reply_text(
            "📝 用法：/set_forward <目标聊天ID>\n\n"
            "💡 获取 ID 的方法：在目标私聊或群组中让机器人发送 /getid，复制返回的 ID。"
        )
        return

    # 校验 chat_id 格式（数字，可选负号）
    try:
        int(target)
    except ValueError:
        await update.message.reply_text("❌ 聊天 ID 格式不正确，应为数字（群组 ID 通常以 - 开头）。")
        return

    chat_id = str(update.effective_chat.id)

    # 尝试向目标聊天发一条测试消息，确认机器人有权限
    try:
        test_msg = await context.bot.send_message(
            chat_id=target,
            text="✅ 转发目标设置成功！此后该群组命中关键词时，消息会转发到这里。"
        )
        # 立即删除测试消息，避免打扰
        await context.bot.delete_message(chat_id=target, message_id=test_msg.message_id)
    except Exception as e:
        await update.message.reply_text(
            f"❌ 无法访问目标聊天（ID: {target}）。\n"
            f"原因：{e}\n\n"
            f"请确认：\n"
            f"1. 机器人已被加入目标聊天（群组/频道）\n"
            f"2. 机器人在目标聊天中有发消息权限\n"
            f"3. 如果是私聊，请先给机器人发过任意消息"
        )
        return

    store.set_forward(chat_id, target)
    await update.message.reply_text(f"✅ 已设置转发目标：`{target}`\n命中关键词的消息将同时转发到该聊天。", parse_mode="Markdown")


async def cmd_forward_info(update: Update, context: ContextTypes.DEFAULT_TYPE):
    chat_id = str(update.effective_chat.id)
    data = store.get(chat_id)
    if data.forward_to:
        await update.message.reply_text(
            f"📤 当前转发配置：已启用\n"
            f"  目标聊天 ID：`{data.forward_to}`\n\n"
            f"使用 /clear_forward 可取消转发。",
            parse_mode="Markdown"
        )
    else:
        await update.message.reply_text(
            "📤 当前转发配置：未设置\n\n"
            "使用 /set_forward <目标聊天ID> 设置转发目标。\n"
            "在目标聊天中发送 /getid 可获取其 ID。"
        )


async def cmd_clear_forward(update: Update, context: ContextTypes.DEFAULT_TYPE):
    if not await is_admin(update, context):
        await update.message.reply_text("⚠️ 只有群组管理员可以清除转发目标。")
        return
    chat_id = str(update.effective_chat.id)
    data = store.get(chat_id)
    if not data.forward_to:
        await update.message.reply_text("ℹ️ 当前未设置转发目标。")
        return
    store.clear_forward(chat_id)
    await update.message.reply_text("🗑️ 已清除转发目标，命中消息将不再转发。")


# ============ 消息监听 ============
async def on_message(update: Update, context: ContextTypes.DEFAULT_TYPE):
    """监听所有非命令消息，检查是否命中关键词。"""
    message = update.effective_message
    if not message or not message.text:
        return

    # 忽略机器人自己发的消息
    if message.from_user and message.from_user.is_bot:
        return

    chat_id = str(update.effective_chat.id)

    # 更新群组名称（用于 Web 后台显示）
    chat_title = update.effective_chat.title or update.effective_chat.full_name
    if chat_title:
        store.update_chat_title(chat_id, chat_title)

    data = store.get(chat_id)
    if not data.keywords:
        return

    matched = find_matched_keywords(message.text, data.keywords)
    if not matched:
        return

    sender = format_sender(message)
    now = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    preview = message.text[:100] + ("..." if len(message.text) > 100 else "")

    # 记录每一个命中的关键词
    for kw in matched:
        store.record_hit(chat_id, {
            "time": now,
            "keyword": kw,
            "sender": sender,
            "user_id": message.from_user.id if message.from_user else None,
            "preview": preview,
        })

    # 发送提醒
    kw_str = "、".join(f"「{kw}」" for kw in matched)
    reply = (
        f"🔔 检测到关键词：{kw_str}\n"
        f"👤 发送者：{sender}\n"
        f"🕐 时间：{now}\n"
        f"📝 内容：{preview}"
    )
    await message.reply_text(reply)

    # 转发到目标聊天
    if data.forward_to:
        try:
            source_title = update.effective_chat.title or update.effective_chat.full_name or "未知聊天"
            forward_notice = (
                f"📨 关键词命中转发\n"
                f"─────────────\n"
                f"🏷️ 命中关键词：{kw_str}\n"
                f"👤 发送者：{sender}\n"
                f"🏠 来源：{source_title}\n"
                f"🕐 时间：{now}\n"
                f"─────────────\n"
                f"📎 原始消息如下："
            )
            await context.bot.send_message(
                chat_id=data.forward_to,
                text=forward_notice,
            )
            await message.forward_to(chat_id=data.forward_to)
        except Exception as e:
            logger.error("转发消息失败 (目标 %s): %s", data.forward_to, e)
            # 转发失败时在原群组提示，但不中断主流程
            try:
                await message.reply_text(f"⚠️ 转发到目标聊天失败：{e}")
            except Exception:
                pass


# ============ 错误处理 ============
async def error_handler(update: object, context: ContextTypes.DEFAULT_TYPE):
    logger.error("处理更新时发生异常:", exc_info=context.error)


# ============ Bot 应用创建（供 polling 和 webhook 两种模式复用） ============
def create_application(token: str = None):
    """创建并配置 Telegram Application，注册所有命令和消息处理器。

    Args:
        token: Telegram Bot Token，为 None 时从环境变量读取

    Returns:
        配置好的 Application 实例（未启动）
    """
    if token is None:
        token = BOT_TOKEN
    application = Application.builder().token(token).build()

    # 命令
    application.add_handler(CommandHandler("start", cmd_start))
    application.add_handler(CommandHandler("add", cmd_add))
    application.add_handler(CommandHandler("remove", cmd_remove))
    application.add_handler(CommandHandler("list", cmd_list))
    application.add_handler(CommandHandler("history", cmd_history))
    application.add_handler(CommandHandler("clear", cmd_clear))
    application.add_handler(CommandHandler("getid", cmd_getid))
    application.add_handler(CommandHandler("set_forward", cmd_set_forward))
    application.add_handler(CommandHandler("forward_info", cmd_forward_info))
    application.add_handler(CommandHandler("clear_forward", cmd_clear_forward))

    # 消息监听（排除命令）
    application.add_handler(
        MessageHandler(filters.TEXT & ~filters.COMMAND, on_message)
    )

    # 错误处理
    application.add_error_handler(error_handler)

    return application


# ============ 主入口 ============
def start_web_server():
    """在后台线程启动 Flask Web 管理后台。"""
    try:
        from webapp import create_app
        app = create_app(store, admin_password=ADMIN_PASSWORD, bot_token=BOT_TOKEN)

        def run():
            # 关闭 Flask 调试模式的重载器，避免线程问题
            app.run(host=WEB_HOST, port=WEB_PORT, debug=False, use_reloader=False)

        thread = threading.Thread(target=run, daemon=True, name="web-server")
        thread.start()
        logger.info("Web 管理后台已启动：http://%s:%d", WEB_HOST, WEB_PORT)
        return thread
    except ImportError as e:
        logger.warning("无法启动 Web 后台（缺少依赖 flask）：%s", e)
        logger.warning("如需使用 Web 后台，请运行：pip install flask")
        return None
    except Exception as e:
        logger.error("启动 Web 后台失败：%s", e)
        return None


def main():
    if not BOT_TOKEN:
        print("错误：请设置环境变量 TELEGRAM_BOT_TOKEN")
        print("  export TELEGRAM_BOT_TOKEN='你的机器人Token'")
        return

    # 启动 Web 管理后台
    if WEB_ENABLED:
        start_web_server()
    else:
        logger.info("Web 管理后台已禁用（WEB_ENABLED=0）")

    application = create_application(BOT_TOKEN)

    logger.info("机器人启动中...")
    application.run_polling(allowed_updates=Update.ALL_TYPES)


if __name__ == "__main__":
    main()
