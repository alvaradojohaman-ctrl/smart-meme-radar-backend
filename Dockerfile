FROM python:3.12-slim
ENV PYTHONDONTWRITEBYTECODE=1 PYTHONUNBUFFERED=1
WORKDIR /app
COPY backend/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt && useradd --create-home app
COPY backend/ .
USER app
CMD ["sh", "-c", "exec uvicorn smr.api:app --host 0.0.0.0 --port ${PORT:-8000}"]
