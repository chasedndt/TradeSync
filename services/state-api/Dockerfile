FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc && rm -rf /var/lib/apt/lists/*

WORKDIR /app
COPY services/state-api/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY libs/tradesync_core /tmp/tradesync_core
RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core

COPY services/state-api/app /app/app
COPY config/features/market-feature-catalog-v1.json /app/config/features/market-feature-catalog-v1.json
COPY config/regime/regime-rulebook-v1.json /app/config/regime/regime-rulebook-v1.json

EXPOSE 8000
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
