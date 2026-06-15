"""Загрузка конфигурации подключения к Home Assistant.

Секреты берутся из переменных окружения (файл .env), в код не зашиваются.
См. .env.example.
"""
import os
from dataclasses import dataclass
from urllib.parse import urlparse, urlunparse

try:
    from dotenv import load_dotenv
except ImportError:  # python-dotenv не установлен — полагаемся на окружение
    load_dotenv = None


@dataclass
class Config:
    base_url: str
    token: str

    @property
    def ws_url(self) -> str:
        """ws(s)://<host>/api/websocket, выведенный из base_url (http->ws, https->wss)."""
        parsed = urlparse(self.base_url)
        scheme = "wss" if parsed.scheme == "https" else "ws"
        return urlunparse((scheme, parsed.netloc, "/api/websocket", "", "", ""))


def load_config() -> Config:
    """Читает HA_BASE_URL и HA_TOKEN. Бросает RuntimeError, если чего-то нет."""
    if load_dotenv is not None:
        load_dotenv()

    base_url = os.environ.get("HA_BASE_URL", "").strip()
    token = os.environ.get("HA_TOKEN", "").strip()

    if not base_url:
        raise RuntimeError("HA_BASE_URL не задан. Создайте .env по образцу .env.example.")
    if not token:
        raise RuntimeError("HA_TOKEN не задан. Создайте .env по образцу .env.example.")

    return Config(base_url=base_url, token=token)
