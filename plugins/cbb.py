# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

import logging

from pyrogram import __version__
from pyrogram.types import CallbackQuery, InlineKeyboardButton, InlineKeyboardMarkup

from bot import Bot
from config import OWNER_ID

log = logging.getLogger(__name__)


async def _show_panel(message, text: str, reply_markup) -> None:
    media = message.photo or message.video or message.document or message.animation or message.audio
    if media:
        await message.edit_caption(caption=text, reply_markup=reply_markup)
        return
    await message.edit_text(
        text,
        disable_web_page_preview=True,
        reply_markup=reply_markup,
    )


@Bot.on_callback_query()
async def cb_handler(client: Bot, query: CallbackQuery):
    try:
        await query.answer()
    except Exception:
        pass

    data = query.data
    if data == "about":
        text = (
            "<b>About this bot</b>\n"
            f"○ Owner: <a href='tg://user?id={OWNER_ID}'>Owner</a>\n"
            "○ Language: <code>Python 3</code>\n"
            f"○ Library: <a href='https://github.com/Mayuri-Chan/pyrofork'>Pyrofork {__version__}</a>\n"
            "○ Original project: "
            "<a href='https://github.com/CodeXBotz/File-Sharing-Bot'>CodeXBotz File-Sharing-Bot</a>\n"
            "○ This build: "
            "<a href='https://github.com/nika-kirann/File-Sharing-Bot-Fixed'>File-Sharing-Bot-Fixed</a>"
        )
        buttons = InlineKeyboardMarkup(
            [[InlineKeyboardButton("Close", callback_data="close")]]
        )
        try:
            await _show_panel(query.message, text, buttons)
        except Exception:
            log.exception("Could not edit the about panel")
            await query.message.reply(text, reply_markup=buttons, quote=True)
    elif data == "close":
        try:
            await query.message.delete()
        except Exception:
            pass
        replied = query.message.reply_to_message
        if replied is not None:
            try:
                await replied.delete()
            except Exception:
                pass
