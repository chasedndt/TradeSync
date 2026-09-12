FROM python:3.11-slim

ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1

WORKDIR /app
COPY services/discord-reader/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

# Shared library: the message -> quarantine mapping lives there so it is tested
# without a bot token or a network.
COPY libs/tradesync_core /tmp/tradesync_core
RUN pip install --no-cache-dir /tmp/tradesync_core && rm -rf /tmp/tradesync_core

COPY services/discord-reader/app /app/app

# No ports: this service only makes outbound requests (Discord, state-api, Redis).
CMD ["python", "-m", "app.main"]
