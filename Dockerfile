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

# Set up a new non-root user (Hugging Face Spaces requirement)
RUN useradd -m -u 1000 user
USER user

# Set environment variables for the new user profile
ENV HOME=/home/user \
    PATH=/home/user/.local/bin:$PATH \
    PORT=7860 \
    PYTHONUNBUFFERED=1

# Set the working directory to the user's space
WORKDIR $HOME/app

# Copy the server directory contents and the requirements file with proper ownership
COPY --chown=user:user server/ $HOME/app/server/
COPY --chown=user:user version.json $HOME/app/version.json

# Set working directory to the server folder
WORKDIR $HOME/app/server

# Install Python dependencies as the user
RUN pip install --no-cache-dir -r requirements.txt

# Create downloads directory with proper permissions
RUN mkdir -p downloads && chmod -R 777 downloads

# Expose the port
EXPOSE 7860

# Run the server
CMD ["sh", "-c", "uvicorn server:app --host 0.0.0.0 --port $PORT"]