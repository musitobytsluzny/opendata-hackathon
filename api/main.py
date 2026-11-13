"""Development API bootstrap; business endpoints will be added separately."""
import os

import psycopg
from fastapi import FastAPI, HTTPException

app = FastAPI(title="OpenData API")


@app.get("/health")
async def health():
    return {"status": "ok", "service": "api"}


@app.get("/health/db")
async def database_health():
    try:
        async with await psycopg.AsyncConnection.connect(
            os.environ["DATABASE_URL"], connect_timeout=3
        ) as connection:
            async with connection.cursor() as cursor:
                await cursor.execute(
                    "SELECT extname, extversion FROM pg_extension "
                    "WHERE extname IN ('postgis', 'vector')"
                )
                extensions = dict(await cursor.fetchall())
                if set(extensions) != {"postgis", "vector"}:
                    raise RuntimeError("Required database extensions are missing")
        return {"status": "ok", "extensions": extensions}
    except (psycopg.Error, KeyError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error
