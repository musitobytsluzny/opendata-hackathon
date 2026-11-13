
from fastapi import FastAPI

app = FastAPI(
    title="OpenData Hackathon API",
    description="Backend API for our hackathon project",
    version="1.0.0",
)


@app.get("/")
def root():
    return {"message": "API is running!"}


@app.get("/health")
def health_check():
    return {"status": "ok"}
