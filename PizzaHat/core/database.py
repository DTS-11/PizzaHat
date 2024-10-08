import ssl
from typing import Union

import asyncpg

from utils.config import PG_URL


async def create_db_pool() -> Union[asyncpg.pool.Pool, None]:
    ssl_object = ssl.create_default_context()
    ssl_object.check_hostname = False
    ssl_object.verify_mode = ssl.CERT_NONE

    return await asyncpg.create_pool(PG_URL, ssl=ssl_object)
