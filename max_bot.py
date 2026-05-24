"""
MAX Business webhook server.
Receives POST events from MAX platform, replies via MAX Bot API.
"""
import asyncio
import logging

import httpx
import uvicorn
from fastapi import FastAPI, Request
from fastapi.responses import JSONResponse

logger = logging.getLogger(__name__)

_BASE_URL = "https://platform-api.max.ru"


class MaxBot:
    def __init__(self, token: str, port: int = 8000):
        self._token = token
        self._port = port
        self._message_handler = None
        self.app = FastAPI()
        self._setup_routes()

    def on_message(self, handler):
        self._message_handler = handler
        return handler

    async def send_text(self, chat_id: str, text: str) -> None:
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE_URL}/messages",
                params={"chat_id": chat_id},
                headers={"Authorization": self._token},
                json={"text": text},
            )
            logger.info("send_text -> %s %s", resp.status_code, resp.text[:200])

    async def register_webhook(self, url: str) -> bool:
        """Register webhook URL with MAX Bot API."""
        async with httpx.AsyncClient(timeout=30) as client:
            resp = await client.post(
                f"{_BASE_URL}/subscriptions",
                headers={"Authorization": self._token},
                json={"url": url, "update_types": ["message_created", "bot_started"]},
            )
            logger.info("register_webhook -> %s %s", resp.status_code, resp.text[:300])
            return resp.status_code == 200

    def _extract_message(self, data: dict) -> tuple[str, str] | None:
        """Extract chat_id and text from MAX Bot API webhook payload."""
        logger.debug("Extracting message from payload: %s", str(data)[:500])

        update_type = data.get("update_type", "")

        # Format 1: MAX Bot API standard format
        # {"update_type": "message_created", "message": {"recipient": {"chat_id": ...}, "body": {"text": ...}}}
        if update_type == "message_created":
            msg = data.get("message", {})
            text = (msg.get("body") or {}).get("text", "")
            recipient = msg.get("recipient") or {}
            chat_id = str(recipient.get("chat_id") or recipient.get("chatId") or "")
            if not chat_id:
                sender = msg.get("sender") or {}
                chat_id = str(sender.get("user_id") or "")
            if chat_id and text:
                return chat_id, text

        # Format 2: bot_started event - greet the user
        if update_type == "bot_started":
            msg = data.get("message", {})
            recipient = msg.get("recipient") or {}
            chat_id = str(recipient.get("chat_id") or recipient.get("chatId") or "")
            if not chat_id:
                sender = msg.get("sender") or {}
                chat_id = str(sender.get("user_id") or "")
            if chat_id:
                return chat_id, "/start"

        # Format 3: older ICQ-style {"events": [{"type": "newMessage", "payload": {...}}]}
        for event in data.get("events", []):
            if event.get("type") == "newMessage":
                p = event.get("payload", {})
                chat_id = (p.get("chat") or {}).get("chatId") or str(p.get("chatId", ""))
                text = p.get("text", "")
                if chat_id and text:
                    return str(chat_id), text

        # Format 4: single event at root
        if data.get("type") == "newMessage":
            p = data.get("payload", {})
            chat_id = (p.get("chat") or {}).get("chatId") or str(p.get("chatId", ""))
            text = p.get("text", "")
            if chat_id and text:
                return str(chat_id), text

        return None

    def _setup_routes(self):
        @self.app.post("/")
        @self.app.post("/webhook")
        async def webhook(request: Request):
            try:
                data = await request.json()
            except Exception:
                data = {}

            logger.info("Webhook payload: %s", str(data)[:500])

            result = self._extract_message(data)
            if result and self._message_handler:
                chat_id, text = result
                asyncio.create_task(self._safe_handle(chat_id, text))

            return JSONResponse({"ok": True})

    async def _safe_handle(self, chat_id: str, text: str) -> None:
        try:
            await self._message_handler(chat_id, text)
        except Exception:
            logger.exception("Handler error chat_id=%s", chat_id)

    async def start(self) -> None:
        cfg = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self._port,
            log_level="warning",
        )
        server = uvicorn.Server(cfg)
        await server.serve()
