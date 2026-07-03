FROM python:3.10-slim

# Install system packages
RUN apt-get update && apt-get install -y --no-install-recommends \
    ffmpeg \
    curl \
    unzip \
    ca-certificates \
    && rm -rf /var/lib/apt/lists/*

# Download and install Bento4 (mp4decrypt)
RUN mkdir -p /tmp/bento4 && \
    curl -L https://www.bok.net/Bento4/binaries/Bento4-SDK-1-6-0-641.x86_64-unknown-linux.zip -o /tmp/bento4.zip && \
    unzip /tmp/bento4.zip -d /tmp/bento4 && \
    cp /tmp/bento4/Bento4-SDK-1-6-0-641.x86_64-unknown-linux/bin/mp4decrypt /usr/local/bin/ && \
    chmod +x /usr/local/bin/mp4decrypt && \
    rm -rf /tmp/bento4 /tmp/bento4.zip

# Set working directory
WORKDIR /app

# Install Python dependencies
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt

# Copy source code
COPY . .

# Start bot
CMD ["python", "bot.py"]
