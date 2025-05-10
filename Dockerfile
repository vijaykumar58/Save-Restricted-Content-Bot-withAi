# Use the official Python image as the base
FROM python:3.10.4-slim-buster

# Install base system dependencies in a single layer
# --no-install-recommends reduces the number of installed packages
# apt-get clean and rm -rf cleans up the apt cache to keep the image size down
RUN apt-get update && apt-get upgrade -y && \
    apt-get install -y --no-install-recommends \
    git \
    curl \
    wget \
    bash \
    ffmpeg \
    neofetch \
    software-properties-common \
    python3-pip \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory inside the container
WORKDIR /app

# Copy the requirements file first to leverage Docker cache
COPY requirements.txt .

# Install Python dependencies in a single layer
# Upgrade pip and install wheel first
# Install requirements from the requirements.txt file
# --no-cache-dir prevents pip from storing cache data
# pip cache purge removes any remaining pip cache
RUN pip install --upgrade pip && \
    pip install --no-cache-dir wheel && \
    pip install --no-cache-dir -r requirements.txt && \
    pip cache purge

# Copy the rest of the application code into the working directory
COPY . .

# Expose the port the application will run on
EXPOSE 5000

# Command to run the application when the container starts
# Runs Flask in the background and then starts the main python script
# Note: For production, consider using a process manager like supervisord
CMD flask run -h 0.0.0.0 -p 5000 & python3 main.py
