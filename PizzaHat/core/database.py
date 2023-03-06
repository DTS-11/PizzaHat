import os
import ssl

import asyncpg
from dotenv import load_dotenv

load_dotenv()

async def create_db_pool():
    ssl_object = ssl.create_default_context()
    ssl_object.check_hostname = False
    ssl_object.verify_mode = ssl.CERT_NONE

    return await asyncpg.create_pool(
        dsn=os.getenv("PG_URL"),
        ssl=ssl_object
    )
