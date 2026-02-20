FROM python:3.11-slim

WORKDIR /app

COPY . /app

# Install ffmpeg and aiohttp
RUN apt-get update \
    && apt-get install -y ffmpeg \
    && pip install --no-cache-dir aiohttp python-dateutil python-dotenv \
    && apt-get clean \
    && rm -rf /var/lib/apt/lists/*

EXPOSE 8080

CMD ["python", "iptv_proxy.py"]
