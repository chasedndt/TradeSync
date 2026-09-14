FROM python:3.11-slim

WORKDIR /app

# Install dependencies
COPY services/market-data/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY services/market-data/app/ ./app/
# Pure shared calculations (liquidity heatmap walls, estimated liquidation map); no signing code is imported.
COPY libs/tradesync_core/tradesync_core/ ./tradesync_core/
COPY config/features/market-feature-catalog-v1.json ./config/features/market-feature-catalog-v1.json

# Expose port
EXPOSE 8005

# Run the application
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8005"]
