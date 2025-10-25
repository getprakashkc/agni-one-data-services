FROM python:3.11-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy requirements and install Python dependencies
COPY microservice_requirements.txt .
RUN pip install --no-cache-dir -r microservice_requirements.txt

# Copy application code
COPY . .

# Expose port
EXPOSE 8000 8001 8002

# Default command
CMD ["python", "data_service.py"]
