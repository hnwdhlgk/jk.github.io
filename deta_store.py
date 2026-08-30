"""
Deta Base 数据存储（用于 Deta Space 部署）
提供与 DataStore 完全相同的接口，使用 Deta Base 持久化存储。
在 Deta Space 环境中，DETA_PROJECT_KEY 环境变量会自动注入。
"""
import os
import logging
import threading
from typing import Dict, Optional

logger = logging.getLogger(__name__)

MAX_HISTORY_PER_CHAT = 200


class DetaDataStore:
    """基于 Deta Base 的持久化存储（线程安全）。

    接口与 bot.DataStore 完全兼容，可直接替换。
    """

    def __init__(self, project_key: str = None):
        try:
            from deta import Deta
        except ImportError:
            raise ImportError("请安装 deta 库：pip install deta")

        if project_key is None:
            project_key = os.environ.get("DETA_PROJECT_KEY", "")
        if not project_key:
            raise ValueError(
                "未设置 DETA_PROJECT_KEY 环境变量。"
                "在 Deta Space 中会自动注入，本地测试需手动设置。"
            )

        self.deta = Deta(project_key)
        self.db = self.deta.Base("bot_data")
        self.chats: Dict[str, object] = {}
        self.lock = threading.Lock()
        self._load_all()

    def _load_all(self):
        """从 Deta Base 加载所有数据到内存。"""
        from bot import ChatData
        try:
            res = self.db.fetch()
            for item in res.items:
                cid = item["key"]
                self.chats[cid] = ChatData(
                    keywords=item.get("keywords", []),
                    history=item.get("history", []),
                    forward_to=item.get("forward_to"),
                    chat_title=item.get("chat_title"),
                )
            logger.info("已从 Deta Base 加载 %d 个群组的数据", len(self.chats))
        except Exception as e:
            logger.error("从 Deta Base 加载数据失败：%s", e)

    def _save(self, chat_id: str):
        """保存单个聊天数据到 Deta Base。"""
        from bot import ChatData
        data = self.chats.get(chat_id)
        if data is None:
            return
        try:
            record = {
                "key": chat_id,
                "keywords": data.keywords,
                "history": data.history,
                "forward_to": data.forward_to,
                "chat_title": data.chat_title,
            }
            self.db.put(record)
        except Exception as e:
            logger.error("保存数据到 Deta Base 失败：%s", e)

    def get(self, chat_id: str):
        from bot import ChatData
        with self.lock:
            if chat_id not in self.chats:
                self.chats[chat_id] = ChatData()
            return self.chats[chat_id]

    def get_all(self) -> Dict[str, object]:
        with self.lock:
            return dict(self.chats)

    def update_chat_title(self, chat_id: str, title: str):
        with self.lock:
            from bot import ChatData
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            if data.chat_title != title:
                data.chat_title = title
                self._save(chat_id)

    def add_keyword(self, chat_id: str, keyword: str) -> bool:
        with self.lock:
            from bot import ChatData
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            keyword = keyword.strip()
            if not keyword or keyword in data.keywords:
                return False
            data.keywords.append(keyword)
            self._save(chat_id)
            return True

    def remove_keyword(self, chat_id: str, keyword: str) -> bool:
        with self.lock:
            data = self.chats.get(chat_id)
            if not data:
                return False
            keyword = keyword.strip()
            if keyword in data.keywords:
                data.keywords.remove(keyword)
                self._save(chat_id)
                return True
            return False

    def record_hit(self, chat_id: str, record: Dict):
        with self.lock:
            from bot import ChatData
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            data.history.insert(0, record)
            if len(data.history) > MAX_HISTORY_PER_CHAT:
                data.history = data.history[:MAX_HISTORY_PER_CHAT]
            self._save(chat_id)

    def clear_history(self, chat_id: str):
        with self.lock:
            data = self.chats.get(chat_id)
            if data:
                data.history.clear()
                self._save(chat_id)

    def set_forward(self, chat_id: str, target_chat_id: str) -> bool:
        with self.lock:
            from bot import ChatData
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData()
                self.chats[chat_id] = data
            target_chat_id = target_chat_id.strip()
            if not target_chat_id:
                return False
            data.forward_to = target_chat_id
            self._save(chat_id)
            return True

    def clear_forward(self, chat_id: str):
        with self.lock:
            data = self.chats.get(chat_id)
            if data:
                data.forward_to = None
                self._save(chat_id)

    def ensure_chat(self, chat_id: str, title: Optional[str] = None):
        with self.lock:
            from bot import ChatData
            data = self.chats.get(chat_id)
            if data is None:
                data = ChatData(chat_title=title)
                self.chats[chat_id] = data
                self._save(chat_id)
            elif title and data.chat_title != title:
                data.chat_title = title
                self._save(chat_id)
            return data
