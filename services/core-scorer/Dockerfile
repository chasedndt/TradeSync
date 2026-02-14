FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/core-scorer/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY libs/tradesync_core /tmp/tradesync_core
RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core

COPY services/core-scorer/app /app/app

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
