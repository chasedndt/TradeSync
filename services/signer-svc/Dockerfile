FROM python:3.11-slim

WORKDIR /app

COPY services/signer-svc/requirements.txt /app/
RUN pip install --no-cache-dir -r requirements.txt

COPY libs/tradesync_core /tmp/tradesync_core
# The signing extra, installed only here.
RUN pip install --no-cache-dir "/tmp/tradesync_core[signing]" && rm -rf /tmp/tradesync_core

COPY services/signer-svc/app /app/app

# Unprivileged. The one process in this system that may hold a key should not
# also be root inside its container.
RUN useradd --create-home --uid 10001 signer && chown -R signer:signer /app
USER signer

CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8006"]
