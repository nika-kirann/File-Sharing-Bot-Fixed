# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).
# The health server binds before Telegram login so platform checks pass
# during startup. Sessions stay in memory for ephemeral container disks.

from __future__ import annotations

import asyncio
import logging
from datetime import datetime, timezone

from aiohttp import web
from pyrogram import Client
from pyrogram.enums import ParseMode
from pyrogram.errors import FloodWait

from config import (
    API_HASH,
    APP_ID,
    CHANNEL_ID,
    FORCE_SUB_CHANNEL,
    JOIN_REQUEST_ENABLE,
    LOGGER,
    PORT,
    TG_BOT_TOKEN,
    TG_BOT_WORKERS,
)
from database.database import prepare_database
from helper_func import deletion_worker, flood_seconds
from plugins import web_server

log = LOGGER(__name__)


class Bot(Client):
    def __init__(self):
        super().__init__(
            name="filesharingbot",
            api_id=APP_ID,
            api_hash=API_HASH,
            bot_token=TG_BOT_TOKEN,
            workers=TG_BOT_WORKERS,
            plugins={"root": "plugins"},
            parse_mode=ParseMode.HTML,
            in_memory=True,
            skip_updates=True,
        )
        self.LOGGER = LOGGER
        self.web_runner: web.AppRunner | None = None
        self.delete_task: asyncio.Task | None = None
        self.invitelink: str | None = None
        self.force_sub_id: int = 0

    async def _start_web(self) -> None:
        app = await web_server()
        runner = web.AppRunner(app, access_log=None)
        await runner.setup()
        await web.TCPSite(runner, "0.0.0.0", PORT).start()
        self.web_runner = runner
        log.info("Health server listening on 0.0.0.0:%s", PORT)

    async def _export_invite(self, chat_id) -> str:
        if JOIN_REQUEST_ENABLE:
            invite = await self.create_chat_invite_link(
                chat_id=chat_id,
                creates_join_request=True,
            )
            return invite.invite_link

        chat = await self.get_chat(chat_id)
        link = chat.invite_link
        if link:
            return link
        await self.export_chat_invite_link(chat_id)
        chat = await self.get_chat(chat_id)
        if not chat.invite_link:
            raise RuntimeError("Telegram did not return an invite link")
        return chat.invite_link

    async def start(self):
        await self._start_web()
        try:
            await super().start()
        except Exception:
            log.exception(
                "Telegram login failed. Check TG_BOT_TOKEN, APP_ID, API_HASH, "
                "and that this host can reach Telegram on port 443."
            )
            raise
        self.start_time = datetime.now(timezone.utc)
        me = await self.get_me()
        self.username = me.username
        self.me_id = me.id

        try:
            await prepare_database()
        except Exception:
            # Do not log the exception: MongoDB errors can echo DATABASE_URL.
            log.error(
                "Database connection failed. Check DATABASE_URL, DATABASE_NAME, "
                "and that this host is allowed to reach MongoDB."
            )
            raise SystemExit(1) from None

        if FORCE_SUB_CHANNEL:
            try:
                try:
                    self.invitelink = await self._export_invite(FORCE_SUB_CHANNEL)
                except FloodWait as exc:
                    await asyncio.sleep(flood_seconds(exc))
                    self.invitelink = await self._export_invite(FORCE_SUB_CHANNEL)
                force_chat = await self.get_chat(FORCE_SUB_CHANNEL)
                self.force_sub_id = force_chat.id
            except Exception as exc:
                log.error(
                    "Cannot use FORCE_SUB_CHANNEL (%s): %s. The bot must be an "
                    "admin there with permission to invite users via link.",
                    FORCE_SUB_CHANNEL,
                    exc,
                )
                raise SystemExit(1) from None
        else:
            self.force_sub_id = 0

        try:
            db_channel = await self.get_chat(CHANNEL_ID)
            self.db_channel = db_channel
            probe = await self.send_message(chat_id=db_channel.id, text="fsb:ok")
            try:
                await probe.delete()
            except Exception:
                log.warning("Posted a startup check to the database channel but could not delete it")
        except Exception as exc:
            log.error(
                "Cannot use CHANNEL_ID (%s): %s. Add the bot as an admin in that "
                "channel with permission to post messages.",
                CHANNEL_ID,
                exc,
            )
            raise SystemExit(1) from None

        self.delete_task = asyncio.create_task(deletion_worker(self))
        log.info("Bot running as @%s", self.username)

    async def stop(self, *args):
        task = self.delete_task
        self.delete_task = None
        if task is not None:
            task.cancel()
            try:
                await task
            except asyncio.CancelledError:
                pass
        runner = self.web_runner
        self.web_runner = None
        if runner is not None:
            await runner.cleanup()
        try:
            await super().stop()
        except Exception:
            logging.getLogger(__name__).info("Telegram client stopped")
