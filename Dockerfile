FROM python:3.10.4-slim-buster

# Base system dependencies (optimized single layer)
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    bash \
    ffmpeg \
    libgl1 \
    python3-dev \
    gcc \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Install Python dependencies with precise caching
COPY requirements.txt .
RUN pip install --upgrade pip && \
    pip install --no-cache-dir wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy application files
COPY . .

# Environment setup for Flask
ENV FLASK_APP=app.py
ENV FLASK_ENV=production

# Expose both ports if needed (Flask + potential main.py services)
EXPOSE 5000

# Run both services (consider using supervisord for production)
CMD flask run --host=0.0.0.0 --port=5000 & python3 main.py