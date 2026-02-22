import asyncio
from aiohttp import web, ClientSession
import json
import xml.etree.ElementTree as ET
import re
import urllib.parse
import logging
from datetime import datetime, timezone
from dateutil import parser as dateutil_parser
import os
from dotenv import load_dotenv
load_dotenv()

# Configuration variables from .env
XMLTV_URL = os.getenv("XMLTV_URL")
PROVIDER_URL = os.getenv("PROVIDER_URL")
JACKETT_HOST = os.getenv("JACKETT_HOST")
JACKETT_API_KEY = os.getenv("JACKETT_API_KEY")
PREFERRED_LANGUAGE = os.getenv("PREFERRED_LANGUAGE", "hun")

# Setup logging to stdout for Docker
logging.basicConfig(
    level=logging.DEBUG,
    format='%(asctime)s %(levelname)s %(message)s',
    handlers=[logging.StreamHandler()]
)


# M3U playlist endpoint
async def playlist_m3u(request):
    async with ClientSession() as session:
        async with session.get(XMLTV_URL) as resp:
            xml_data = await resp.text()
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        logging.error(f"XMLTV parse error in playlist endpoint: {e}")
        return web.Response(status=500, text='XMLTV parse error')
    xmltv_url = XMLTV_URL
    m3u = [f'#EXTM3U url-tvg="{xmltv_url}" x-tvg-url="{xmltv_url}"']
    channel_number = 1
    for ch in root.findall('channel'):
        channel_id = ch.attrib.get('id')
        display_name = ch.find('display-name').text if ch.find('display-name') is not None else channel_id
        stream_url = str(request.url.with_path(f'/channel/{channel_id}').with_query(''))
        m3u.append(
            f'#EXTINF:0 tvg-id="{channel_id}" channel-id="{channel_id}" channel-number="{channel_number}" tvg-name="{channel_id}", {display_name}'
        )
        m3u.append(stream_url)
        channel_number += 1
    m3u_content = '\n'.join(m3u)
    return web.Response(text=m3u_content, content_type='audio/x-mpegurl')

async def fetch_xmltv_and_get_programme(channels, channel_id):
    url = XMLTV_URL
    logging.info(f"Fetching XMLTV guide from: {url}")
    async with ClientSession() as session:
        async with session.get(url) as resp:
            xml_data = await resp.text()
    # Always log and write the XMLTV response, even if empty or invalid
    import os
    from dotenv import load_dotenv
    abs_path = os.path.abspath(os.path.join(os.getcwd(), 'xmltv_dump.xml'))
    logging.debug(f"Attempting to write XMLTV dump to: {abs_path}")
    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(xml_data)
        logging.debug(f"XMLTV response written to {abs_path}")
    except Exception as e:
        logging.error(f"Failed to write XMLTV response to file: {e}")
    if not xml_data.strip():
        logging.error("XMLTV response is empty!")
    else:
        logging.debug(f"First 500 chars of XMLTV: {xml_data[:500]}")
    try:
        root = ET.fromstring(xml_data)
        # Log all programme titles and descs for debugging
        for programme in root.findall('programme'):
            title = programme.find('title').text if programme.find('title') is not None else ''
            desc = programme.find('desc').text if programme.find('desc') is not None else ''
            logging.debug(f"Programme: title='{title}', desc='{desc}'")
    except Exception as e:
        logging.error(f"XMLTV parse error: {e}")
        return web.Response(status=500, text='XMLTV parse error')
    now = datetime.now(timezone.utc)
    selected = None
    for programme in root.findall('programme'):
        start_str = programme.attrib.get('start')
        stop_str = programme.attrib.get('stop')
        try:
            start = datetime.strptime(start_str.split()[0], '%Y%m%d%H%M%S')
            stop = datetime.strptime(stop_str.split()[0], '%Y%m%d%H%M%S')
        except Exception as e:
            logging.warning(f"Invalid start/stop in programme: {e}")
            continue
        if start <= now < stop:
            selected = programme
            break
    if selected is None:
        logging.error("No currently ongoing <programme> found in XMLTV.")
        return None, None
    desc = selected.find('desc').text if selected.find('desc') is not None else ''
    logging.debug(f"Programme description: {desc}")
    imdb_match = re.search(r'IMDB:\s*(tt\d+)', desc, re.IGNORECASE)
    imdb_id = imdb_match.group(1) if imdb_match else None
    logging.debug(f"Extracted IMDB id: {imdb_id}")
    return imdb_id, selected

async def get_torrent_url(imdb_id):
    # provider_url is ignored for Jackett
    url = f"{JACKETT_HOST}/api/v2.0/indexers/all/results/torznab/api?apikey={JACKETT_API_KEY}&imdbid={imdb_id}"
    logging.debug(f"Requesting Jackett for IMDB {imdb_id}: {url}")
    async with ClientSession() as session:
        async with session.get(url) as resp:
            if resp.status != 200:
                text = await resp.text()
                logging.error(f"Jackett returned status {resp.status}: {text}")
                return None
            xml = await resp.text()
    try:
        root = ET.fromstring(xml)
    except Exception as e:
        logging.error(f"Failed to parse Jackett XML: {e}")
        return None
    items = root.findall('.//item')
    lang = PREFERRED_LANGUAGE.lower() if PREFERRED_LANGUAGE else None
    link_720p_lang = None
    link_1080p_lang = None
    link_any_lang = None
    link_720p = None
    link_1080p = None
    link_any = None
    for item in items:
        title = item.findtext('title', default='').lower()
        link = item.findtext('link')
        if not link:
            continue
        if lang and lang in title:
            if not link_any_lang:
                link_any_lang = link
            if '1080p' in title and not link_1080p_lang:
                link_1080p_lang = link
            if '720p' in title and not link_720p_lang:
                link_720p_lang = link
        if not link_any:
            link_any = link
        if '1080p' in title and not link_1080p:
            link_1080p = link
        if '720p' in title and not link_720p:
            link_720p = link
    # Prefer language-specific torrents first
    if link_720p_lang:
        logging.debug(f"Selected 720p {lang} torrent: {link_720p_lang}")
        return link_720p_lang
    if link_1080p_lang:
        logging.debug(f"Selected 1080p {lang} torrent: {link_1080p_lang}")
        return link_1080p_lang
    if link_any_lang:
        logging.debug(f"Selected fallback {lang} torrent: {link_any_lang}")
        return link_any_lang
    # Fallback to any language
    if link_720p:
        logging.debug(f"Selected 720p torrent: {link_720p}")
        return link_720p
    if link_1080p:
        logging.debug(f"Selected 1080p torrent: {link_1080p}")
        return link_1080p
    if link_any:
        logging.debug(f"Selected fallback torrent: {link_any}")
        return link_any
    logging.error("No suitable torrent found in Jackett response.")
    return None

async def get_playable_url(provider_url, torrent_url):
    get_url = f"{provider_url}/torrent/{urllib.parse.quote(torrent_url, safe='')}"
    logging.debug(f"Requesting playable file from: {get_url}")
    async with ClientSession() as session:
        async with session.get(get_url) as resp:
            data = await resp.json()
            logging.debug(f"Playable file response: {data}")
    for f in data.get('files', []):
        if (f['name'].endswith('.mp4') or f['name'].endswith('.avi') or f['name'].endswith('.mkv')) and 'sample' not in f['name'].lower():
            logging.debug(f"Selected file for streaming: {f['name']} ({f['url']})")
            return f['url']
    logging.error("No suitable file found for streaming.")
    return None


async def stream_with_delay(request):
    channel_id = request.match_info['channel_id']
    logging.info(f"Incoming stream request for channel ID: {channel_id}")
    # Fetch and parse XMLTV
    logging.info(f"Trying to fetch and parse XMLTV guide...")
    async with ClientSession() as session:
        async with session.get(XMLTV_URL) as resp:
            xml_data = await resp.text()
    # Always log and write the XMLTV response, even if empty or invalid
    import os
    abs_path = os.path.abspath(os.path.join(os.getcwd(), 'xmltv_dump.xml'))
    logging.debug(f"Attempting to write XMLTV dump to: {abs_path}")
    try:
        with open(abs_path, 'w', encoding='utf-8') as f:
            f.write(xml_data)
        logging.debug(f"XMLTV response written to {abs_path}")
    except Exception as e:
        logging.error(f"Failed to write XMLTV response to file: {e}")
    if not xml_data.strip():
        logging.error("XMLTV response is empty!")
        return web.Response(status=500, text='XMLTV response is empty!')
    else:
        logging.debug(f"First 500 chars of XMLTV: {xml_data[:500]}")
    try:
        root = ET.fromstring(xml_data)
    except Exception as e:
        logging.error(f"XMLTV parse error: {e}")
        return web.Response(status=500, text='XMLTV parse error')
    # Parse channel definitions from XMLTV
    channel_ids = set()
    for ch in root.findall('channel'):
        cid = ch.attrib.get('id')
        if cid:
            channel_ids.add(cid)
    if channel_id not in channel_ids:
        logging.error(f"Channel {channel_id} not found in XMLTV.")
        return web.Response(status=404, text='Channel not found in XMLTV')
    # ...existing code for programme selection and streaming...
    now = datetime.now(timezone.utc)
    programmes = []
    for programme in root.findall('programme'):
        if programme.attrib.get('channel') != channel_id:
            continue
        start_str = programme.attrib.get('start')
        stop_str = programme.attrib.get('stop')
        try:
            # Use dateutil to parse timezone-aware datetimes
            start = dateutil_parser.parse(start_str)
            stop = dateutil_parser.parse(stop_str)
        except Exception as e:
            logging.warning(f"Invalid start/stop in programme: {e}")
            continue
        # Use UTC now for comparison
        now_utc = datetime.now(timezone.utc)
        if stop.astimezone(timezone.utc) > now_utc:
            programmes.append((start, stop, programme))
    # Sort by start time
    programmes.sort(key=lambda x: x[0])
    # Find the first ongoing or next programme
    idx = 0
    for i, (start, stop, programme) in enumerate(programmes):
        # Ensure all comparisons are between timezone-aware UTC datetimes
        if start.astimezone(timezone.utc) <= now_utc < stop.astimezone(timezone.utc):
            idx = i
            break
        elif start.astimezone(timezone.utc) > now_utc:
            idx = i
            break
    response = web.StreamResponse(status=200, headers={
        'Content-Type': 'video/x-matroska',
        'Content-Disposition': f'inline; filename="channel_{channel_id}.mkv"'
    })
    await response.prepare(request)
    while idx < len(programmes):
        start, stop, programme = programmes[idx]
        now_utc = datetime.now(timezone.utc)
        desc = programme.find('desc').text if programme.find('desc') is not None else ''
        imdb_match = re.search(r'IMDB:\s*(tt\d+)', desc, re.IGNORECASE)
        imdb_id = imdb_match.group(1) if imdb_match else None
        if not imdb_id:
            logging.error("IMDB id not found in programme.")
            idx += 1
            continue
        # Get torrent URL
        torrent_url = await get_torrent_url(imdb_id)
        if not torrent_url:
            logging.error("Torrent not found for IMDB id.")
            idx += 1
            continue
        # Get playable file URL
        playable_url = await get_playable_url(PROVIDER_URL, torrent_url)
        if not playable_url:
            logging.error("Playable file not found in torrent info.")
            idx += 1
            continue
        # Calculate offset using UTC
        offset = 0
        if start.astimezone(timezone.utc) <= now_utc < stop.astimezone(timezone.utc):
            offset = int((now_utc - start.astimezone(timezone.utc)).total_seconds())
            if offset < 0:
                offset = 0
            logging.info(f"Calculated ffmpeg offset: {offset} seconds (now_utc={now_utc}, start={start})")
        # Stream with ffmpeg
        ffmpeg_cmd = [
            'ffmpeg',
            '-hide_banner',
            '-loglevel', 'error',
            '-ss', str(offset),
            '-i', playable_url,
            '-map', '0:v',
            '-map', '0:a',
            '-c', 'copy',
            '-f', 'matroska',
            'pipe:1'
        ]
        logging.info(f"FFmpeg command: {' '.join(ffmpeg_cmd)}")
        proc = await asyncio.create_subprocess_exec(
            *ffmpeg_cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        try:
            while True:
                chunk = await proc.stdout.read(4096)
                if not chunk:
                    break
                await response.write(chunk)
        except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
            logging.warning(f"Client disconnected from channel {channel_id}")
            break
        await proc.wait()
        logging.info(f"Finished streaming programme {idx+1}/{len(programmes)}")
        idx += 1
        # If there is a gap before the next programme, keep the connection open with black video/silence
        if idx < len(programmes):
            next_start, _, _ = programmes[idx]
            gap = (next_start - now).total_seconds()
            if gap > 0:
                logging.info(f"Gap of {gap} seconds before next programme. Sending black video/silence.")
                # Use ffmpeg to generate black video and silence for the gap duration
                ffmpeg_cmd = [
                    'ffmpeg',
                    '-hide_banner',
                    '-loglevel', 'error',
                    '-f', 'lavfi',
                    '-i', f'color=size=1280x720:rate=25:duration={int(gap)}',
                    '-f', 'lavfi',
                    '-i', f'anullsrc=channel_layout=stereo:sample_rate=44100',
                    '-shortest',
                    '-c:v', 'libx264',
                    '-preset', 'ultrafast',
                    '-c:a', 'aac',
                    '-f', 'matroska',
                    'pipe:1'
                ]
                logging.info(f"FFmpeg black video command: {' '.join(ffmpeg_cmd)}")
                proc = await asyncio.create_subprocess_exec(
                    *ffmpeg_cmd,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                try:
                    while True:
                        chunk = await proc.stdout.read(4096)
                        if not chunk:
                            break
                        await response.write(chunk)
                except (asyncio.CancelledError, ConnectionResetError, BrokenPipeError):
                    logging.warning(f"Client disconnected from channel {channel_id} during gap.")
                    break
                await proc.wait()
                logging.info(f"Finished sending black video/silence for gap.")
        now = datetime.now(timezone.utc)
    await response.write_eof()
    logging.info(f"Streaming finished for channel {channel_id}")
    return response


app = web.Application()
app.router.add_get('/channel/{channel_id}', stream_with_delay)
app.router.add_get('/playlist.m3u', playlist_m3u)

if __name__ == '__main__':
    web.run_app(app, port=8080)
