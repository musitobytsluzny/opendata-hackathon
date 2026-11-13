from fastapi import FastAPI, HTTPException
from sqlalchemy import text
from sqlalchemy.exc import SQLAlchemyError

from app.controllers.auth_controller import router as auth_router
from app.controllers.chat_controller import router as chat_router
from app.controllers.user_controller import router as user_router
from app.database.connection import engine

app = FastAPI(
    title="OpenData Hackathon API",
    description="Backend API for our hackathon project",
    version="1.0.0",
)

app.include_router(user_router)
app.include_router(auth_router)
app.include_router(chat_router)


@app.get("/")
def root():
    return {"message": "API is running!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}


@app.get("/health/db")
def database_health():
    try:
        with engine.connect() as connection:
            extensions = dict(
                connection.execute(
                    text(
                        "SELECT extname, extversion FROM pg_extension "
                        "WHERE extname IN ('postgis', 'vector')"
                    )
                ).all()
            )
        if set(extensions) != {"postgis", "vector"}:
            raise RuntimeError("Required database extensions are missing")
        return {"status": "ok", "extensions": extensions}
    except (SQLAlchemyError, RuntimeError) as error:
        raise HTTPException(status_code=503, detail="Database is not ready") from error
