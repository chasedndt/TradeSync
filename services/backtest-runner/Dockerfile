FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app

COPY services/backtest-runner/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Install shared library
COPY libs/tradesync_core /tmp/tradesync_core
RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core

COPY services/backtest-runner/app /app/app

ENTRYPOINT ["python", "-m", "app.main"]
