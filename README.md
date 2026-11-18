# File-Sharing-Bot-Fixed

Modified on 18 November 2026 from the File Sharing Bot by [CodeXBotz](https://github.com/CodeXBotz/File-Sharing-Bot), also published at [Kiranxer/File-Sharing-Bot](https://github.com/Kiranxer/File-Sharing-Bot).

This program is free software under the GNU General Public License v3. See [LICENSE](LICENSE). The original project copyright remains with its authors; this tree changes configuration, dependency pins, bug fixes, and deployment files so the bot can run on current Python and on [Koyeb](https://www.koyeb.com/).

The bot stores posts in a private Telegram channel and gives admins special `t.me` links. Anyone with a link can receive those posts from the bot.

## What you need

- A Telegram bot token from [@BotFather](https://t.me/BotFather)
- An API ID and API hash from [my.telegram.org](https://my.telegram.org)
- A private channel where the bot is an admin and can post messages
- MongoDB (for example [MongoDB Atlas](https://www.mongodb.com/atlas)). Allow network access from the host that runs the bot. On Koyeb that usually means allowing `0.0.0.0/0`, because egress addresses change
- Your numeric Telegram user id (`OWNER_ID`)

Run a single copy of the bot. A second instance using the same token will fight over the Telegram session.

## Deploy on Koyeb

1. Push this repository to GitHub (or use the fork you deploy from).
2. In Koyeb, create a **Web service** from the GitHub repository. Koyeb detects the `Dockerfile`.
3. Leave the service at **one instance**.
4. Set the health check path to `/health` (or `/`). The process listens on the `PORT` variable Koyeb injects, default `8080`, on `0.0.0.0`. The health server starts before the Telegram login, so the check can pass while the bot is still connecting.
5. Add the environment variables below. Do not put tokens in the image or in git.
6. Deploy. When the logs say `Bot running as @your_bot`, open the bot and send `/start`.

The container runs `python -u main.py` as a non-root user. A `Procfile` (`web: python3 -u main.py`) is included for platforms that build from a Python buildpack instead of Docker. `app.json` lists the same variables for a Heroku-style deploy.

### Database channel

Create a channel, add the bot as an admin, and allow it to post. Put that channel's id in `CHANNEL_ID`.

Ids look like `-1001234567890`. If you only have the number from `https://t.me/c/1234567890/1`, you can paste `1234567890`; the bot adds the `-100` prefix.

### Force subscribe (optional)

Set `FORCE_SUB_CHANNEL` to a channel or group id, or to `@username`. Add the bot as an admin with permission to invite users via link. Leave the variable at `0` to disable the check.

Set `JOIN_REQUEST_ENABLED=true` only together with `FORCE_SUB_CHANNEL`. The bot then creates a join-request invite and treats a submitted request as access, even before someone approves it. The bot must be allowed to see join requests.

## Admin commands

| Command | What it does |
| --- | --- |
| `/start` | Welcome message, or the file when a link payload is present |
| `/batch` | Ask for the first and last database-channel posts and build one link |
| `/genlink` | Ask for one database-channel post and build a link |
| `/users` | How many users have started the bot |
| `/broadcast` | Reply to a message to copy it to every stored user |
| `/stats` | Process uptime |

Send any other private message as an admin (a file, photo, video, or text) and the bot copies it into the database channel and replies with a link. Batches are limited to 200 messages, which is also Telegram's `getMessages` page size.

## Environment variables

Required:

| Variable | Description |
| --- | --- |
| `TG_BOT_TOKEN` | Bot token from @BotFather |
| `APP_ID` | Numeric API ID from my.telegram.org |
| `API_HASH` | API hash from my.telegram.org |
| `CHANNEL_ID` | Database channel id (`-100...`) |
| `OWNER_ID` | Your numeric Telegram user id. Always treated as an admin |
| `DATABASE_URL` | MongoDB URI, `mongodb://` or `mongodb+srv://` |

Optional:

| Variable | Default | Description |
| --- | --- | --- |
| `DATABASE_NAME` | `filesharingbot` | MongoDB database name |
| `PORT` | `8080` | Health-check port. Koyeb sets this |
| `TG_BOT_WORKERS` | `4` | Pyrogram worker threads |
| `ADMINS` | empty | Extra admin ids, separated by spaces or commas |
| `FORCE_SUB_CHANNEL` | `0` | Channel/group id or `@username`. `0` disables force-sub |
| `JOIN_REQUEST_ENABLED` | `false` | `true` or `false`. A join request counts as joined |
| `START_MESSAGE` | short greeting | HTML. Placeholders below |
| `START_PIC` | empty | Public image URL. Empty sends text only |
| `FORCE_SUB_MESSAGE` | short notice | HTML. Same placeholders as the start message |
| `CUSTOM_CAPTION` | empty | Document caption. `{filename}`, `{previouscaption}` |
| `PROTECT_CONTENT` | `false` | `true` stops users from forwarding files |
| `AUTO_DELETE_TIME` | `0` | Seconds until delivered files are deleted. `0` disables it |
| `AUTO_DELETE_MSG` | notice | Shown with the file. `{time}` is the delay in seconds |
| `AUTO_DEL_SUCCESS_MSG` | notice | Shown when the file is deleted |
| `DISABLE_CHANNEL_BUTTON` | `false` | `true` does not add the Share URL button on channel posts |
| `BOT_STATS_TEXT` | uptime line | `/stats` text. `{uptime}` |
| `USER_REPLY_TEXT` | short reply | Sent when a non-admin sends an ordinary message |
| `LOG_FILE` | `filesharingbot.txt` | Path for a rotating log, or `none` for stdout only |

Boolean values accept `true`/`false`, `1`/`0`, `yes`/`no`, and `on`/`off`. The string `False` is false.

Start and force-sub placeholders: `{first}`, `{last}`, `{id}`, `{mention}`, `{username}`.

Auto-delete deadlines are stored in MongoDB, so a restart does not forget files that still need to be removed. The worker checks every few seconds.

## Local run

Python 3.10, 3.11, or 3.12:

```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp .env.example .env
# fill in .env
python main.py
```

Check the process without credentials:

```bash
python -m compileall -q .
python -m unittest discover -s tests
```

`GET /` and `GET /health` return `{"ok": true, "service": "file-sharing-bot"}`.

## Dependencies

Pins are in `requirements.txt`. The Telegram client is [Pyrofork](https://github.com/Mayuri-Chan/pyrofork) `2.3.69`, imported as `pyrogram`. The official Pyrogram package stopped at 2.0.106. `TgCrypto` 1.2.5 has no Python 3.12 wheels, so the image uses `tgcrypto-pyrofork`. MongoDB access is async via Motor. Pyrofork already includes the `ask`/`listen` helpers, so the old `pyromod` package is not installed (it would pull in official Pyrogram and clash).

## Credits

- [CodeXBotz/File-Sharing-Bot](https://github.com/CodeXBotz/File-Sharing-Bot), the original GPL-3.0 project
- [Kiranxer/File-Sharing-Bot](https://github.com/Kiranxer/File-Sharing-Bot), the public tree this fix started from
- [Dan (delivrance)](https://github.com/pyrogram/pyrogram) for Pyrogram
- [Pyrofork](https://github.com/Mayuri-Chan/pyrofork) for the maintained library
