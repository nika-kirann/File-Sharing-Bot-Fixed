# File Sharing Bot
# Modified 2026-11-18: async Motor access instead of blocking PyMongo calls.
# Based on CodeXBotz/File-Sharing-Bot (GPL-3.0).

from __future__ import annotations

from datetime import datetime, timedelta, timezone

from motor.motor_asyncio import AsyncIOMotorClient

from config import AUTO_DELETE_TIME, DB_NAME, DB_URI

dbclient = AsyncIOMotorClient(
    DB_URI,
    serverSelectionTimeoutMS=10_000,
    tz_aware=True,
)
database = dbclient[DB_NAME]
user_data = database["users"]
join_requests = database["join_requests"]
deletions = database["deletions"]


async def prepare_database() -> None:
    """Fail fast when MongoDB is unreachable, then ensure indexes exist."""
    await dbclient.admin.command("ping")
    await deletions.create_index("delete_at")


async def present_user(user_id: int) -> bool:
    found = await user_data.find_one({"_id": user_id}, {"_id": 1})
    return found is not None


async def add_user(user_id: int) -> None:
    await user_data.update_one(
        {"_id": user_id},
        {"$setOnInsert": {"joined": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def user_count() -> int:
    return await user_data.count_documents({})


async def iter_user_ids():
    cursor = user_data.find({}, {"_id": 1})
    async for doc in cursor:
        yield doc["_id"]


async def del_user(user_id: int) -> None:
    await user_data.delete_one({"_id": user_id})


async def add_join_request(user_id: int) -> None:
    await join_requests.update_one(
        {"_id": user_id},
        {"$set": {"requested": datetime.now(timezone.utc)}},
        upsert=True,
    )


async def has_join_request(user_id: int) -> bool:
    found = await join_requests.find_one({"_id": user_id}, {"_id": 1})
    return found is not None


async def queue_deletion(chat_id: int, message_ids: list[int], notice_chat_id: int, notice_id: int) -> None:
    if AUTO_DELETE_TIME <= 0 or not message_ids:
        return
    delete_at = datetime.now(timezone.utc) + timedelta(seconds=AUTO_DELETE_TIME)
    await deletions.insert_one(
        {
            "chat_id": chat_id,
            "message_ids": [int(mid) for mid in message_ids],
            "notice_chat_id": notice_chat_id,
            "notice_id": notice_id,
            "delete_at": delete_at,
            "attempts": 0,
        }
    )


async def due_deletions(limit: int = 50) -> list[dict]:
    now = datetime.now(timezone.utc)
    return await deletions.find({"delete_at": {"$lte": now}}).to_list(length=limit)


async def drop_deletion(doc_id) -> None:
    await deletions.delete_one({"_id": doc_id})


async def reschedule_deletion(doc_id, *, attempts: int, delay: int) -> None:
    await deletions.update_one(
        {"_id": doc_id},
        {
            "$set": {
                "attempts": attempts,
                "delete_at": datetime.now(timezone.utc) + timedelta(seconds=delay),
            }
        },
    )
