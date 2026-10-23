# IPTV Proxy

This project provides an IPTV proxy server that streams content with a delay, using channel definitions from XMLTV and torrents found via Jackett.

## Features
- Streams TV channels with configurable delay
- Uses XMLTV for channel and programme definitions
- Searches torrents via Jackett API (by IMDB id)
- Streams video using ffmpeg
- HDHomeRun tuner emulation for Plex, Emby and Jellyfin Live TV / DVR
- Docker-ready deployment

## Usage
1. Copy `.env.example` to `.env` and fill in your configuration:
   - `XMLTV_URL`: URL to your XMLTV file
   - `PROVIDER_URL`: URL to your torrent provider
   - `JACKETT_HOST`: Jackett server URL
   - `JACKETT_API_KEY`: Jackett API key
   - `PREFERRED_LANGUAGE`: Preferred language for torrents (default: hun)
   - `HDHR_FRIENDLY_NAME`: Tuner name shown in Plex/Emby (default: IPTV Proxy)
   - `HDHR_TUNER_COUNT`: Number of tuners advertised (default: 4)
   - `HDHR_DEVICE_ID`: 8 hex digit device id (default: derived from the friendly name)
   - `HDHR_BASE_URL`: Address advertised to clients, e.g. `http://192.168.1.10:8045` (default: taken from the request)

2. Build and run with Docker Compose:
   ```bash
   docker-compose up --build
   ```

3. Access the playlist:
   - `http://localhost:8080/playlist.m3u`
   - Stream channels via `/channel/{channel_id}` (Matroska, add `?format=ts` for MPEG-TS)

4. Use it as an HDHomeRun tuner:
   - Plex: Live TV & DVR > Set up > enter the address manually, e.g. `192.168.1.10:8045`
   - Emby / Jellyfin: Live TV > add a tuner device > HDHomeRun, URL `http://192.168.1.10:8045`
   - Use `XMLTV_URL` as the XMLTV guide source
   - Endpoints: `/discover.json`, `/lineup.json`, `/lineup_status.json`, `/lineup.post`, `/device.xml`
   - Automatic (SSDP) discovery is not supported, add the tuner by address

## Files
- `iptv_proxy.py`: Main application
- `docker-compose.yml`: Docker Compose setup
- `Dockerfile`: Docker build instructions
- `.env.example`: Example environment configuration

## License
MIT
