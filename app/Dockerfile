FROM python:3.12-slim

# Set working directory
WORKDIR /app_src

# Install system deps
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application code
COPY . /app_src/app

# Set PYTHONPATH so `from app.xxx import ...` works
ENV PYTHONPATH=/app_src

# Default command (overridden by docker-compose per service)
CMD ["uvicorn", "app.main:app", "--host", "0.0.0.0", "--port", "8000"]
