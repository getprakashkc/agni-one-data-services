FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared code first (for better caching)
COPY shared/upstox_client/ /app/shared/upstox_client/
COPY shared/utils/ /app/shared/utils/

# Copy service requirements and install
COPY services/data-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/data-service/src/ /app/src/

# Expose port (documentation - actual mapping configured in Coolify)
EXPOSE 8001

# Run service
# Port can be configured in Coolify via DATA_SERVICE_PORT environment variable
# Coolify will also handle port mapping in the UI
CMD sh -c "python -m uvicorn src.data_service:app --host 0.0.0.0 --port ${DATA_SERVICE_PORT:-8001}"
