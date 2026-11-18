"""Regression tests that do not need Telegram or MongoDB."""

from __future__ import annotations

import os
import subprocess
import sys
import unittest

os.environ["TG_BOT_TOKEN"] = "123456789:AAEaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa"
os.environ["APP_ID"] = "123456"
os.environ["API_HASH"] = "0123456789abcdef0123456789abcdef"
os.environ["CHANNEL_ID"] = "-1001234567890"
os.environ["OWNER_ID"] = "100"
os.environ["DATABASE_URL"] = "mongodb://127.0.0.1:27017"
os.environ["DATABASE_NAME"] = "filesharingbot_test"
os.environ["LOG_FILE"] = "none"
os.environ["FORCE_SUB_CHANNEL"] = "0"
os.environ["PROTECT_CONTENT"] = "False"
os.environ["JOIN_REQUEST_ENABLED"] = "False"
os.environ["AUTO_DELETE_TIME"] = "0"
os.environ["ADMINS"] = ""

from config import (  # noqa: E402
    OWNER_ID,
    normalize_chat_id,
    parse_admin_ids,
    parse_bool,
    parse_chat_id,
)
from helper_func import (  # noqa: E402
    PayloadError,
    decode,
    decode_payload,
    encode,
    encode_payload,
    flood_seconds,
    get_message_id,
    get_readable_time,
    telegram_share_url,
)
from plugins.useless import _fallback_filter  # noqa: E402


class _Chat:
    def __init__(self, chat_id, username=None):
        self.id = chat_id
        self.username = username


class _Client:
    def __init__(self):
        self.db_channel = _Chat(-1001234567890, "Archive")


class _Message:
    def __init__(self, text=None, origin=None, legacy=False):
        self.text = text
        if not legacy:
            self.forward_origin = origin


class _Origin:
    def __init__(self, chat=None, message_id=None, sender_user_name=None):
        self.chat = chat
        self.message_id = message_id
        self.sender_user_name = sender_user_name


class _User:
    def __init__(self, user_id, text):
        self.id = user_id
        self.text = text
        self.from_user = self


def _base_env() -> dict[str, str]:
    env = {
        "PATH": os.environ.get("PATH", ""),
        "HOME": os.environ.get("HOME", ""),
        "TG_BOT_TOKEN": "123456789:AAEaaaaaaaaaaaaaaaaaaaaaaaaaaaaaaa",
        "APP_ID": "123456",
        "API_HASH": "0123456789abcdef0123456789abcdef",
        "CHANNEL_ID": "-1001234567890",
        "OWNER_ID": "42",
        "DATABASE_URL": "mongodb://localhost:27017",
        "LOG_FILE": "none",
    }
    return env


class ParseTests(unittest.TestCase):
    def test_false_string_is_false(self):
        self.assertFalse(parse_bool("False"))
        self.assertFalse(parse_bool("false"))
        self.assertFalse(parse_bool("0"))
        self.assertFalse(parse_bool("off"))
        self.assertTrue(parse_bool("True"))
        self.assertTrue(parse_bool("yes"))
        self.assertFalse(parse_bool("", False))
        self.assertTrue(parse_bool(None, True))
        with self.assertRaises(ValueError):
            parse_bool("maybe")

    def test_admins_accept_commas_and_spaces(self):
        self.assertEqual(parse_admin_ids("1, 2  3"), [1, 2, 3])
        self.assertEqual(parse_admin_ids("  "), [])
        with self.assertRaises(ValueError):
            parse_admin_ids("1, abc")

    def test_channel_id_prefix(self):
        self.assertEqual(normalize_chat_id(-1001234567890), -1001234567890)
        self.assertEqual(normalize_chat_id(1234567890), -1001234567890)
        self.assertEqual(normalize_chat_id(1001234567890), -1001234567890)
        self.assertEqual(parse_chat_id("0"), 0)
        self.assertEqual(parse_chat_id("@Archive", allow_username=True), "@Archive")
        self.assertEqual(parse_chat_id("archive", allow_username=True), "@archive")


class LinkTests(unittest.TestCase):
    def test_roundtrip_and_large_ids_keep_precision(self):
        channel_id = -1001234567890
        message_id = 18237
        token = encode_payload([message_id], channel_id)
        self.assertEqual(decode_payload(token, channel_id), [message_id])
        self.assertLessEqual(len(token), 64)
        # Integer division is the inverse of the multiplication used in the token.
        divisor = abs(channel_id)
        self.assertEqual((message_id * divisor) // divisor, message_id)

    def test_batch_range_and_descending(self):
        channel_id = -10099
        token = encode_payload([3, 5], channel_id)
        self.assertEqual(decode_payload(token, channel_id), [3, 4, 5])
        token = encode_payload([5, 3], channel_id)
        self.assertEqual(decode_payload(token, channel_id), [5, 4, 3])

    def test_batch_limit(self):
        channel_id = -10099
        token = encode_payload([1, 500], channel_id)
        with self.assertRaises(PayloadError):
            decode_payload(token, channel_id)

    def test_padding_and_reject_garbage(self):
        self.assertEqual(decode(encode("get-10")), "get-10")
        with self.assertRaises(PayloadError):
            decode_payload("%%%", -10099)

    def test_share_url_encodes_start_parameter(self):
        link = "https://t.me/filesharebot?start=abc"
        shared = telegram_share_url(link)
        self.assertTrue(shared.startswith("https://t.me/share/url?url="))
        self.assertNotIn("?start=", shared)
        self.assertIn("start%3Dabc", shared)

    def test_message_id_from_origin_and_links(self):
        client = _Client()
        origin = _Origin(chat=_Chat(-1001234567890), message_id=55)
        self.assertEqual(get_message_id(client, _Message(origin=origin)), 55)
        other = _Origin(chat=_Chat(-100777), message_id=4)
        self.assertEqual(get_message_id(client, _Message(origin=other)), 0)
        self.assertEqual(
            get_message_id(client, _Message(text="https://t.me/c/1234567890/55")),
            55,
        )
        self.assertEqual(
            get_message_id(client, _Message(text="https://telegram.dog/archive/9")),
            9,
        )
        self.assertEqual(get_message_id(client, _Message(text="hello")), 0)

        class Legacy:
            forward_from_chat = _Chat(-1001234567890)
            forward_from_message_id = 7
            text = None

        self.assertEqual(get_message_id(client, Legacy()), 7)

    def test_readable_time_uses_total_seconds(self):
        self.assertEqual(get_readable_time(0), "0s")
        self.assertEqual(get_readable_time(61), "1m:1s")
        self.assertEqual(get_readable_time(90_061), "1days, 1h:1m:1s")

    def test_flood_wait_value(self):
        class Modern:
            value = 3

        class Legacy:
            x = 4

        self.assertEqual(flood_seconds(Modern()), 3)
        self.assertEqual(flood_seconds(Legacy()), 4)
        self.assertEqual(flood_seconds(RuntimeError("nope")), 1)


class HandlerFilterTests(unittest.TestCase):
    def test_fallback_ignores_admins_and_real_commands(self):
        self.assertFalse(_fallback_filter(None, None, _User(5, "/start")))
        self.assertFalse(_fallback_filter(None, None, _User(5, "/start@bot payload")))
        self.assertFalse(_fallback_filter(None, None, _User(OWNER_ID, "a file")))
        self.assertTrue(_fallback_filter(None, None, _User(5, "hello")))
        self.assertTrue(_fallback_filter(None, None, _User(5, "/unknown")))


class HealthTests(unittest.IsolatedAsyncioTestCase):
    async def test_health_endpoints(self):
        from aiohttp import ClientSession, web

        from plugins import web_server

        app = await web_server()
        runner = web.AppRunner(app)
        await runner.setup()
        site = web.TCPSite(runner, "127.0.0.1", 0)
        await site.start()
        port = site._server.sockets[0].getsockname()[1]
        try:
            async with ClientSession() as session:
                for path in ("/", "/health"):
                    async with session.get(f"http://127.0.0.1:{port}{path}") as response:
                        self.assertEqual(response.status, 200)
                        body = await response.json()
                        self.assertTrue(body["ok"])
                async with session.head(f"http://127.0.0.1:{port}/health") as response:
                    self.assertEqual(response.status, 200)
        finally:
            await runner.cleanup()


class ConfigProcessTests(unittest.TestCase):
    def test_missing_env_exits(self):
        env = {"PATH": os.environ.get("PATH", ""), "HOME": os.environ.get("HOME", "")}
        result = subprocess.run(
            [sys.executable, "-c", "import config"],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertNotEqual(result.returncode, 0)
        self.assertIn("TG_BOT_TOKEN", result.stderr + result.stdout)

    def test_documented_defaults_and_no_extra_admin(self):
        env = _base_env()
        env.update(
            {
                "CHANNEL_ID": "1234567890",
                "PROTECT_CONTENT": "False",
                "JOIN_REQUEST_ENABLED": "False",
                "ADMINS": "5, 6",
                "AUTO_DELETE_TIME": "",
            }
        )
        code = (
            "import config;"
            "print(config.CHANNEL_ID);"
            "print(config.PROTECT_CONTENT);"
            "print(config.JOIN_REQUEST_ENABLE);"
            "print(config.AUTO_DELETE_TIME);"
            "print(','.join(map(str, config.ADMINS)))"
        )
        result = subprocess.run(
            [sys.executable, "-c", code],
            cwd=os.path.dirname(os.path.dirname(__file__)),
            env=env,
            capture_output=True,
            text=True,
        )
        self.assertEqual(result.returncode, 0, result.stderr)
        lines = result.stdout.strip().splitlines()
        self.assertEqual(lines, ["-1001234567890", "False", "False", "0", "5,6,42"])


if __name__ == "__main__":
    unittest.main()
