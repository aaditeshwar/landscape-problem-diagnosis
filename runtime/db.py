from functools import lru_cache

from pymongo import MongoClient

from config import DB_NAME, MONGO_URI


@lru_cache
def get_client() -> MongoClient:
    return MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)


def get_db():
    return get_client()[DB_NAME]
