"""Асинхронный WebSocket-клиент Home Assistant.

Отвечает только за транспорт: подключение, аутентификацию и вызов команд
area_registry. Доменной логики (имена, дифф) здесь нет.
"""
import json
import logging
import asyncio

import websockets


class HAAuthError(RuntimeError):
    """Аутентификация в Home Assistant не пройдена."""


class HAClient:
    def __init__(self, ws_url: str, token: str, timeout: float = 10.0):
        self._ws_url = ws_url
        self._token = token
        self._timeout = timeout
        self._ws = None
        self._id = 0

    async def __aenter__(self) -> "HAClient":
        await self.connect()
        return self

    async def __aexit__(self, *exc) -> None:
        await self.close()

    async def connect(self) -> None:
        self._ws = await asyncio.wait_for(
            websockets.connect(self._ws_url), timeout=self._timeout
        )

        hello = json.loads(await self._recv())
        if hello.get("type") != "auth_required":
            raise HAAuthError(f"Неожиданный ответ при подключении: {hello.get('type')}")

        await self._send({"type": "auth", "access_token": self._token})
        resp = json.loads(await self._recv())
        if resp.get("type") != "auth_ok":
            raise HAAuthError("Аутентификация не пройдена (auth_invalid). Проверьте HA_TOKEN.")

        logging.info("Подключение к Home Assistant установлено, аутентификация ок.")

    async def list_areas(self) -> list[dict]:
        resp = await self._command({"type": "config/area_registry/list"})
        if not resp.get("success"):
            raise RuntimeError(f"area_registry/list завершился ошибкой: {resp.get('error')}")
        return resp.get("result", [])

    async def create_area(self, name: str, aliases: list[str]) -> dict:
        """Возвращает сырой ответ HA (с ключом success)."""
        return await self._command(
            {"type": "config/area_registry/create", "name": name, "aliases": aliases}
        )

    async def close(self) -> None:
        if self._ws is not None:
            await self._ws.close()
            self._ws = None

    # --- внутреннее ---

    def _next_id(self) -> int:
        self._id += 1
        return self._id

    async def _command(self, payload: dict) -> dict:
        cmd_id = self._next_id()
        await self._send({"id": cmd_id, **payload})
        # Ждём именно результат с нашим id (события с другим id игнорируем).
        while True:
            msg = json.loads(await self._recv())
            if msg.get("id") == cmd_id and msg.get("type") == "result":
                return msg

    async def _send(self, obj: dict) -> None:
        await self._ws.send(json.dumps(obj))

    async def _recv(self) -> str:
        return await asyncio.wait_for(self._ws.recv(), timeout=self._timeout)
