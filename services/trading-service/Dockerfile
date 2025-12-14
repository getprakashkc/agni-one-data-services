FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared utilities
COPY shared/utils/ /app/shared/utils/

# Copy service requirements and install
COPY services/trading-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/trading-service/src/ /app/src/

# Expose port (documentation - actual mapping configured in Coolify)
EXPOSE 8002

# Run service
# Port can be configured in Coolify via TRADING_SERVICE_PORT environment variable
# Coolify will also handle port mapping in the UI
CMD sh -c "python -m uvicorn src.trading_service:app --host 0.0.0.0 --port ${TRADING_SERVICE_PORT:-8002}"
