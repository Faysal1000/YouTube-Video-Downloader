# Use a modern Python image
FROM python:3.11-slim

# Install system dependencies: ffmpeg and nodejs (for yt-dlp EJS challenges)
RUN apt-get update && apt-get install -y \
    ffmpeg \
    curl \
    && curl -fsSL https://deb.nodesource.com/setup_20.x | bash - \
    && apt-get install -y nodejs \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

# Set the working directory to /app
WORKDIR /app

# Copy the server directory contents and the requirements file
COPY server/ /app/server/

# Set working directory to the server folder
WORKDIR /app/server

# Install Python dependencies
RUN pip install --no-cache-dir -r requirements.txt

# Create downloads directory
RUN mkdir -p downloads

# Set environment variables
ENV PORT=8080
ENV PYTHONUNBUFFERED=1

# Run the server using uvicorn (bind to 0.0.0.0 for Docker)
CMD uvicorn server:app --host 0.0.0.0 --port $PORT