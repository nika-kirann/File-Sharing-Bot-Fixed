# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0),
# https://github.com/CodeXBotz/File-Sharing-Bot
# Upstream publication used here: https://github.com/Kiranxer/File-Sharing-Bot

import asyncio
import logging

from pyrogram import idle

from bot import Bot

log = logging.getLogger(__name__)


async def main() -> None:
    bot = Bot()
    try:
        await bot.start()
        await idle()
    finally:
        await bot.stop()


if __name__ == "__main__":
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        log.info("Process exiting")
    except SystemExit as exc:
        code = exc.code if isinstance(exc.code, int) else 1
        raise SystemExit(code) from None
