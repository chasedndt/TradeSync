FROM python:3.11-slim

WORKDIR /app

COPY requirements.txt /app/

# Install build tools, then our Python deps, then clean up.
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential gcc \
    && pip install --no-cache-dir -r requirements.txt \
    && apt-get purge -y --auto-remove build-essential gcc \
    && rm -rf /var/lib/apt/lists/*

COPY app /app/app
COPY sources /app/sources

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8080"]
