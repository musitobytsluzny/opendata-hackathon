FROM python:3.13-slim-bookworm

ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app

COPY mcp/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY --chown=10001:10001 mcp/ ./

RUN groupadd --system --gid 10001 app \
    && useradd --system --uid 10001 --gid app --home-dir /app app

USER 10001:10001
EXPOSE 8000
CMD ["uvicorn", "main:app", "--host", "0.0.0.0", "--port", "8000"]
