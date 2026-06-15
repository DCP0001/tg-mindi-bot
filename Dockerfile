FROM python:3.11-slim

WORKDIR /app

# Install system dependencies (build-essential for compiling some python packages if needed)
RUN apt-get update && apt-get install -y --no-install-recommends \
    build-essential \
    libpq-dev \
    && rm -rf /var/lib/apt/lists/*

# Copy and install Python requirements
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy application source code
COPY . .

# Expose port for FastAPI
EXPOSE 8000

# Run the app
CMD ["python", "-m", "mindi.main"]
