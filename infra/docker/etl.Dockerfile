FROM python:3.13-slim-bookworm
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app/etl
COPY etl/requirements.txt ./
RUN pip install --no-cache-dir -r requirements.txt
COPY etl/ ./
CMD ["python", "main.py"]
