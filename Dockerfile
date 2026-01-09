FROM python:3.12-slim

WORKDIR /app

# Install system dependencies
RUN apt-get update && apt-get install -y --no-install-recommends \
    gcc \
    && rm -rf /var/lib/apt/lists/*

# Copy project files
COPY pyproject.toml .
COPY src/ src/

# Install the package
RUN pip install --no-cache-dir .

# Create directories for profiles and sessions
RUN mkdir -p /app/profiles /app/sessions

# Set environment variables
ENV PYTHONUNBUFFERED=1

# Default command
CMD ["tg-bot", "--help"]
