
from fastapi import FastAPI

from app.controllers.user_controller import router as user_router

app = FastAPI(
    title="OpenData Hackathon API",
    description="Backend API for our hackathon project",
    version="1.0.0",
)

app.include_router(user_router)


@app.get("/")
def root():
    return {"message": "API is running!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
