# File Sharing Bot
# Modified 2026-11-18: environment-only configuration, no embedded secrets.
# Based on CodeXBotz/File-Sharing-Bot (GPL-3.0),
# https://github.com/CodeXBotz/File-Sharing-Bot
# and https://github.com/Kiranxer/File-Sharing-Bot

from __future__ import annotations

import logging
import os
import re
from logging.handlers import RotatingFileHandler

from dotenv import load_dotenv

load_dotenv()

KNOWN_COMMANDS = ("start", "users", "broadcast", "batch", "genlink", "stats")
MAX_BATCH_MESSAGES = 200
START_PAYLOAD_LIMIT = 64

_USERNAME_RE = re.compile(r"^@?[A-Za-z][A-Za-z0-9_]{3,31}$")
_ADMIN_SPLIT_RE = re.compile(r"[\s,]+")
_TRUE = {"1", "true", "yes", "on"}
_FALSE = {"0", "false", "no", "off"}


def parse_bool(value: str | None, default: bool = False) -> bool:
    """Parse a boolean environment value.

    The string ``"False"`` is false. Only an empty value uses ``default``.
    """
    if value is None:
        return default
    text = value.strip().lower()
    if text == "":
        return default
    if text in _TRUE:
        return True
    if text in _FALSE:
        return False
    raise ValueError(
        f"expected true/false (or 1/0, yes/no, on/off), got {value!r}"
    )


def parse_admin_ids(value: str | None) -> list[int]:
    """Parse a space- or comma-separated list of Telegram user ids."""
    if value is None or not value.strip():
        return []
    ids: list[int] = []
    for part in _ADMIN_SPLIT_RE.split(value.strip()):
        if not part:
            continue
        try:
            ids.append(int(part))
        except ValueError as exc:
            raise ValueError(
                f"admin id {part!r} is not an integer"
            ) from exc
    return ids


def normalize_chat_id(chat_id: int) -> int:
    """Accept ids pasted without Telegram's ``-100`` channel prefix.

    Channel and supergroup ids are negative. Deployers often paste the
    positive id from ``t.me/c/<id>`` or the id with the sign dropped.
    """
    if chat_id == 0 or chat_id < 0:
        return chat_id
    text = str(chat_id)
    if text.startswith("100"):
        return int(f"-{text}")
    return int(f"-100{text}")


def parse_chat_id(value: str | None, *, allow_username: bool = False, default: int = 0):
    """Parse a chat id, ``0`` (disabled), or an optional @username."""
    if value is None:
        return default
    raw = value.strip()
    if raw.lower() in {"", "0", "none", "false", "off", "-"}:
        return default
    if raw.lstrip("-").isdigit():
        return normalize_chat_id(int(raw))
    if allow_username and _USERNAME_RE.match(raw):
        return raw if raw.startswith("@") else f"@{raw}"
    raise ValueError(f"invalid chat id {value!r}")


def _required(name: str) -> str:
    value = os.environ.get(name, "").strip()
    if not value:
        raise SystemExit(f"Missing required environment variable: {name}")
    return value


def _required_int(name: str) -> int:
    raw = _required(name)
    try:
        return int(raw)
    except ValueError as exc:
        raise SystemExit(f"{name} must be an integer, got {raw!r}") from exc


def _bool_env(name: str, default: bool) -> bool:
    try:
        return parse_bool(os.environ.get(name), default)
    except ValueError as exc:
        raise SystemExit(f"{name}: {exc}") from exc


def _int_env(name: str, default: int, *, minimum: int | None = None) -> int:
    raw = os.environ.get(name)
    if raw is None or raw.strip() == "":
        value = default
    else:
        try:
            value = int(raw.strip())
        except ValueError as exc:
            raise SystemExit(f"{name} must be an integer, got {raw!r}") from exc
    if minimum is not None and value < minimum:
        raise SystemExit(f"{name} must be >= {minimum}, got {value}")
    return value


def _optional_text(name: str, default: str | None = None) -> str | None:
    raw = os.environ.get(name)
    if raw is None:
        return default
    text = raw.strip()
    return text if text else None


TG_BOT_TOKEN = _required("TG_BOT_TOKEN")
APP_ID = _required_int("APP_ID")
API_HASH = _required("API_HASH")
try:
    CHANNEL_ID = parse_chat_id(_required("CHANNEL_ID"))
except ValueError as exc:
    raise SystemExit(f"CHANNEL_ID: {exc}") from exc
if not isinstance(CHANNEL_ID, int) or CHANNEL_ID == 0:
    raise SystemExit("CHANNEL_ID must be a numeric Telegram channel id")

OWNER_ID = _required_int("OWNER_ID")
PORT = _int_env("PORT", 8080, minimum=1)
if PORT > 65535:
    raise SystemExit(f"PORT must be between 1 and 65535, got {PORT}")

DB_URI = _required("DATABASE_URL")
if not DB_URI.startswith(("mongodb://", "mongodb+srv://")):
    raise SystemExit("DATABASE_URL must start with mongodb:// or mongodb+srv://")
DB_NAME = os.environ.get("DATABASE_NAME", "filesharingbot").strip() or "filesharingbot"

try:
    FORCE_SUB_CHANNEL = parse_chat_id(
        os.environ.get("FORCE_SUB_CHANNEL", "0"),
        allow_username=True,
    )
except ValueError as exc:
    raise SystemExit(f"FORCE_SUB_CHANNEL: {exc}") from exc

JOIN_REQUEST_ENABLE = _bool_env("JOIN_REQUEST_ENABLED", False)
if JOIN_REQUEST_ENABLE and not FORCE_SUB_CHANNEL:
    raise SystemExit(
        "JOIN_REQUEST_ENABLED requires FORCE_SUB_CHANNEL to be set"
    )

TG_BOT_WORKERS = _int_env("TG_BOT_WORKERS", 4, minimum=1)
START_PIC = _optional_text("START_PIC")
START_MSG = os.environ.get(
    "START_MESSAGE",
    "Hello {first}\n\nI can store private files in a channel and other users can access them from a special link.",
)
FORCE_MSG = os.environ.get(
    "FORCE_SUB_MESSAGE",
    "Hello {first}\n\n<b>You need to join my channel before you can use this link.</b>",
)
CUSTOM_CAPTION = _optional_text("CUSTOM_CAPTION")
PROTECT_CONTENT = _bool_env("PROTECT_CONTENT", False)
AUTO_DELETE_TIME = _int_env("AUTO_DELETE_TIME", 0, minimum=0)
AUTO_DELETE_MSG = os.environ.get(
    "AUTO_DELETE_MSG",
    "This file will be automatically deleted in {time} seconds. Save anything you need before then.",
)
AUTO_DEL_SUCCESS_MSG = os.environ.get(
    "AUTO_DEL_SUCCESS_MSG",
    "Your file has been deleted. Thank you for using this bot.",
)
DISABLE_CHANNEL_BUTTON = _bool_env("DISABLE_CHANNEL_BUTTON", False)
BOT_STATS_TEXT = os.environ.get("BOT_STATS_TEXT", "<b>BOT UPTIME</b>\n{uptime}")
USER_REPLY_TEXT = os.environ.get(
    "USER_REPLY_TEXT",
    "I only share files through links. Use a file link, or send /start.",
)

try:
    _admin_ids = parse_admin_ids(os.environ.get("ADMINS", ""))
except ValueError as exc:
    raise SystemExit(f"ADMINS: {exc}") from exc
ADMINS = list(dict.fromkeys([*_admin_ids, OWNER_ID]))

LOG_FILE_NAME = os.environ.get("LOG_FILE", "filesharingbot.txt").strip()


def _build_handlers() -> list[logging.Handler]:
    handlers: list[logging.Handler] = [logging.StreamHandler()]
    if LOG_FILE_NAME.lower() in {"", "none", "-", "stdout"}:
        return handlers
    try:
        handlers.insert(
            0,
            RotatingFileHandler(
                LOG_FILE_NAME,
                maxBytes=2_000_000,
                backupCount=2,
                encoding="utf-8",
            ),
        )
    except OSError as exc:
        logging.basicConfig(level=logging.INFO)
        logging.getLogger(__name__).warning(
            "File logging disabled (%s). Logging to stdout only.", exc
        )
        return [logging.StreamHandler()]
    return handlers


logging.basicConfig(
    level=logging.INFO,
    format="[%(asctime)s - %(levelname)s] - %(name)s - %(message)s",
    datefmt="%d-%b-%y %H:%M:%S",
    handlers=_build_handlers(),
)
logging.getLogger("pyrogram").setLevel(logging.WARNING)
logging.getLogger("aiohttp").setLevel(logging.WARNING)


def LOGGER(name: str) -> logging.Logger:
    return logging.getLogger(name)
