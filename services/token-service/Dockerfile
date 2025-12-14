FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy shared utilities first (for better caching)
COPY shared/ /app/shared/

# Copy service requirements and install
COPY services/token-service/requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy service code
COPY services/token-service/src/ /app/src/

# Expose port (documentation - actual mapping configured in Coolify)
EXPOSE 8000

# Run service
# Port can be configured in Coolify via TOKEN_SERVICE_PORT environment variable
# Coolify will also handle port mapping in the UI
CMD sh -c "python -m uvicorn src.token_service:app --host 0.0.0.0 --port ${TOKEN_SERVICE_PORT:-8000}"
