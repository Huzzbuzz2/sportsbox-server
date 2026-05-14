from flask import Flask, jsonify
import requests
import re
import json
import os
import time
import threading
from bs4 import BeautifulSoup

app = Flask(__name__)
CACHE_FILE = 'cache.json'
CACHE_LOCK = threading.Lock()

WEBCRIC_BASE = 'https://go.webcric.com'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://go.webcric.com/',
    'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
    'Accept-Language': 'en-GB,en;q=0.9',
}

# Known embed channel mappings for WebCric streams
EMBED_CHANNELS = [
    'webcricn02',
    'webcricn03', 
    'webcricn04',
    'webcricn05',
    'webcricn06',
]

EMBED_BASE = 'https://one.timesup.top/hembedplayer'


def try_embed(channel, stream_id='6'):
    """Try to fetch a timesup embed page and extract m3u8 URL."""
    embed_url = f'{EMBED_BASE}/{channel}/{stream_id}/850/480'
    try:
        headers = {
            **HEADERS,
            'Referer': f'{WEBCRIC_BASE}/',
            'Origin': WEBCRIC_BASE,
        }
        r = requests.get(embed_url, headers=headers, timeout=15)
        print(f'Embed {embed_url} status: {r.status_code}')
        print(f'Embed snippet: {r.text[:300]}')

        # Look for m3u8
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', r.text)
        if m3u8:
            return m3u8.group(1)

        # Look for id and pk
        id_m = re.search(r'["\']?id["\']?\s*[:=]\s*["\']?(\d+)', r.text)
        pk_m = re.search(r'["\']?pk["\']?\s*[:=]\s*["\']?([a-f0-9]{80,})', r.text)
        if id_m and pk_m:
            stream_url = f'https://muc002.myturn1.top:8088/live/{channel}/playlist.m3u8?id={id_m.group(1)}&pk={pk_m.group(1)}'
            print(f'Built URL: {stream_url}')
            return stream_url

    except Exception as e:
        print(f'Error fetching embed {embed_url}: {e}')
    return None


def get_webcric_matches():
    """Scrape WebCric homepage for today's matches."""
    try:
        r = requests.get(WEBCRIC_BASE + '/', headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        matches = []

        for ul in soup.find_all('ul'):
            links = ul.find_all('a', href=True)
            stream_links = [a for a in links if '.htm' in a.get('href', '')]
            if not stream_links:
                continue

            title = 'Cricket Match'
            for sibling in ul.previous_siblings:
                t = sibling.get_text(strip=True) if hasattr(sibling, 'get_text') else str(sibling).strip()
                if t and t not in ['\n', '']:
                    title = t
                    break

            skip = ['scorecard', 'ranking', 'schedule', 'news', 'stat']
            if any(s in title.lower() for s in skip):
                continue

            pages = []
            for a in stream_links:
                href = a['href']
                if not href.startswith('http'):
                    href = WEBCRIC_BASE + '/' + href.lstrip('/')
                label = a.get_text(strip=True).encode('ascii', 'ignore').decode('ascii') or 'Stream'
                pages.append({'label': label, 'url': href})

            if pages:
                matches.append({
                    'title': title.encode('ascii', 'ignore').decode('ascii').strip(),
                    'pages': pages
                })

        return matches
    except Exception as e:
        print(f'Error fetching WebCric: {e}')
        return []


def build_matches():
    matches_raw = get_webcric_matches()
    result = []

    # Try to resolve streams via embed channels
    resolved_embeds = {}
    for i, channel in enumerate(EMBED_CHANNELS):
        url = try_embed(channel)
        if url:
            resolved_embeds[i] = url

    print(f'Resolved embeds: {resolved_embeds}')

    for match_idx, match in enumerate(matches_raw):
        streams = []
        for page_idx, page in enumerate(match['pages']):
            # Map stream pages to embed channels
            embed_idx = page_idx % len(EMBED_CHANNELS)
            if embed_idx in resolved_embeds:
                streams.append({
                    'label': page['label'],
                    'url': resolved_embeds[embed_idx]
                })
            else:
                # Fall back to passing the page URL directly
                streams.append({
                    'label': page['label'],
                    'url': page['url']
                })

        if streams:
            result.append({
                'title': match['title'],
                'streams': streams
            })

    return result


def load_cache():
    try:
        with open(CACHE_FILE, 'r') as f:
            data = json.load(f)
        if data.get('date') == time.strftime('%Y-%m-%d'):
            return data.get('matches', [])
    except Exception:
        pass
    return None


def save_cache(matches):
    try:
        with open(CACHE_FILE, 'w') as f:
            json.dump({'date': time.strftime('%Y-%m-%d'), 'matches': matches}, f)
    except Exception as e:
        print(f'Cache error: {e}')


@app.route('/matches')
def get_matches():
    with CACHE_LOCK:
        cached = load_cache()
        if cached is not None:
            return jsonify({'matches': cached, 'cached': True})
        matches = build_matches()
        if matches:
            save_cache(matches)
        return jsonify({'matches': matches, 'cached': False})


@app.route('/refresh')
def refresh():
    with CACHE_LOCK:
        try:
            os.remove(CACHE_FILE)
        except Exception:
            pass
        matches = build_matches()
        if matches:
            save_cache(matches)
        return jsonify({'matches': matches, 'refreshed': True})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
