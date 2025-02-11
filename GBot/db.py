import os
import asyncio
from aiomysql.sa import create_engine


class DataBaseEntryPoint:
    async def __aenter__(self, loop=None):
        if loop is None:
            loop = asyncio.get_event_loop()
        engine = await create_engine(
            user=os.environ["DB_USER"],
            db=os.environ["DB_USER"],
            host=os.environ["DB_HOST"],
            port=3306,
            password=os.environ["DB_PASSWORD"],
            charset="utf8",
            autocommit=True,
            loop=loop
        )
        self._connection = await engine.acquire()
        return self

    async def __aexit__(self, *args, **kwargs):
        await self._connection.close()

    async def execute(self, query, *args, **kwargs):
        return await self._connection.execute(query, *args, **kwargs)
