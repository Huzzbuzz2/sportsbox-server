from flask import Flask, jsonify
import requests
import re
import json
import os
import time
import threading

app = Flask(__name__)
CACHE_FILE = 'cache.json'
CACHE_LOCK = threading.Lock()

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://go.webcric.com/',
}

STREAM_PAGES = [
    {'name': 'IPL 2026', 'streams': [
        {'label': 'Stream 1', 'url': 'https://go.webcric.com/watch-ipl-2026-live-cricket-streaming.htm'},
        {'label': 'Stream 2', 'url': 'https://go.webcric.com/ipl-2026-live-cricket-streaming.htm'},
        {'label': 'Stream HD', 'url': 'https://go.webcric.com/watch-ipl-live-cricket-streaming-3.htm'},
        {'label': 'Hindi', 'url': 'https://go.webcric.com/watch-ipl-2026-in-hindi-live-cricket-streaming.htm'},
    ]},
    {'name': 'PAK v BAN', 'streams': [
        {'label': 'Stream 1', 'url': 'https://go.webcric.com/watch-pakistan-vs-bangladesh-live-cricket-streaming.htm'},
        {'label': 'Stream 2', 'url': 'https://go.webcric.com/pakistan-vs-bangladesh-cricket-live-streaming.htm'},
        {'label': 'Stream 3', 'url': 'https://go.webcric.com/pakistan-vs-bangladesh-live-cricket-streaming.htm'},
    ]},
]


def get_m3u8_from_page(page_url):
    """Fetch a WebCric stream page and try to find the m3u8 URL."""
    try:
        r = requests.get(page_url, headers=HEADERS, timeout=15)
        html = r.text

        # Look for direct m3u8 URL in page source
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', html)
        if m3u8:
            return m3u8.group(1)

        # Look for iframe or embed src
        iframe = re.search(r'(?:iframe|embed)[^>]+src=["\']([^"\']+)["\']', html, re.IGNORECASE)
        if iframe:
            embed_url = iframe.group(1)
            if embed_url.startswith('//'):
                embed_url = 'https:' + embed_url
            if embed_url.startswith('/'):
                embed_url = 'https://go.webcric.com' + embed_url

            # Fetch the embed page
            r2 = requests.get(embed_url, headers={**HEADERS, 'Referer': page_url}, timeout=15)
            m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', r2.text)
            if m3u8:
                return m3u8.group(1)

            # Look for id and pk to build m3u8 URL
            id_m = re.search(r'"id"\s*:\s*"?(\d+)"?', r2.text)
            pk_m = re.search(r'"pk"\s*:\s*"?([a-f0-9]{50,})"?', r2.text)
            ch_m = re.search(r'hembedplayer/([^/\s"\']+)', r2.text)
            if id_m and pk_m and ch_m:
                return f'https://muc002.myturn1.top:8088/live/{ch_m.group(1)}/playlist.m3u8?id={id_m.group(1)}&pk={pk_m.group(1)}'

    except Exception as e:
        print(f'Error fetching {page_url}: {e}')
    return None


def build_matches():
    result = []
    for match in STREAM_PAGES:
        resolved_streams = []
        for stream in match['streams']:
            m3u8 = get_m3u8_from_page(stream['url'])
            if m3u8:
                resolved_streams.append({'label': stream['label'], 'url': m3u8})
        if resolved_streams:
            result.append({'title': match['name'], 'streams': resolved_streams})
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
