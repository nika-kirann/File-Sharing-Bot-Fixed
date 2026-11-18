# File Sharing Bot
# Modified 2026-11-18 from CodeXBotz/File-Sharing-Bot (GPL-3.0).

from aiohttp import web

from .route import routes


async def web_server():
    web_app = web.Application(client_max_size=1_048_576)
    web_app.add_routes(routes)
    return web_app
