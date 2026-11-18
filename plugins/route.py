# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

from aiohttp import web

routes = web.RouteTableDef()


@routes.get("/", allow_head=True)
@routes.get("/health", allow_head=True)
async def health(_request: web.Request) -> web.Response:
    return web.json_response({"ok": True, "service": "file-sharing-bot"})
