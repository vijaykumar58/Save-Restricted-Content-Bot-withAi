# Use official Python slim image
FROM python:3.10.13-slim-bullseye

# Set environment variables
ENV PYTHONUNBUFFERED=1 \
    PYTHONDONTWRITEBYTECODE=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=app.py \
    FLASK_ENV=production

# Install system dependencies
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
    && rm -rf /var/lib/apt/lists/* \
    && useradd -m appuser

WORKDIR /app

# Copy requirements first for better caching
COPY requirements.txt .

# Install Python dependencies in stages
RUN pip install --upgrade pip && \
    pip install --no-cache-dir wheel

# First install all requirements except custom packages
RUN grep -vE "dropbox|ggnpyro" requirements.txt > base_requirements.txt && \
    pip install --no-cache-dir -r base_requirements.txt

# Then handle custom packages with fallback
RUN if grep -q "dropbox" requirements.txt; then \
        echo "Attempting to install custom package..." && \
        cd /tmp && \
        curl -L -o package.zip "https://www.dropbox.com/scl/fi/e0fo6fcjn8kmr5r0x6wvg/myownpyro.zip?rlkey=d1znpwckss4ullz0sg7e1qjjg&st=kmbh7wdv&dl=1" && \
        if file package.zip | grep -q "Zip archive"; then \
            pip install --no-cache-dir package.zip && \
            echo "Custom package installed successfully"; \
        else \
            echo "Warning: Downloaded file is not a valid ZIP archive" && \
            if grep -q "ggnpyro" requirements.txt; then \
                echo "Attempting fallback package..." && \
                pip install --no-cache-dir ggnpyro==1.0.0; \
            fi; \
        fi && \
        rm -f package.zip; \
    fi

# Clean up
RUN pip cache purge && \
    find /usr/local/lib/python3.10 -type d -name '__pycache__' -exec rm -r {} +

# Copy application files
COPY --chown=appuser:appuser . .

# Switch to non-root user
USER appuser

# Health check
HEALTHCHECK --interval=30s --timeout=30s --start-period=5s --retries=3 \
    CMD curl -f http://localhost:5000/ || exit 1

# Expose ports
EXPOSE 5000

# Use entrypoint script
COPY entrypoint.sh .
RUN chmod +x entrypoint.sh
ENTRYPOINT ["./entrypoint.sh"]
