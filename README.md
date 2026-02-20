# IPTV Proxy

This project provides an IPTV proxy server that streams content with a delay, using channel definitions from XMLTV and torrents found via Jackett.

## Features
- Streams TV channels with configurable delay
- Uses XMLTV for channel and programme definitions
- Searches torrents via Jackett API (by IMDB id)
- Streams video using ffmpeg
- Docker-ready deployment

## Usage
1. Copy `.env.example` to `.env` and fill in your configuration:
   - `XMLTV_URL`: URL to your XMLTV file
   - `PROVIDER_URL`: URL to your torrent provider
   - `JACKETT_HOST`: Jackett server URL
   - `JACKETT_API_KEY`: Jackett API key
   - `PREFERRED_LANGUAGE`: Preferred language for torrents (default: hun)

2. Build and run with Docker Compose:
   ```bash
   docker-compose up --build
   ```

3. Access the playlist:
   - `http://localhost:8080/playlist.m3u`
   - Stream channels via `/channel/{channel_id}`

## Files
- `iptv_proxy.py`: Main application
- `docker-compose.yml`: Docker Compose setup
- `Dockerfile`: Docker build instructions
- `.env.example`: Example environment configuration

## License
MIT
