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


def get_matches_from_webcric():
    """Scrape WebCric homepage for today's matches and their stream pages."""
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
                label = a.get_text(strip=True) or 'Stream'
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


def resolve_stream_page(page_url):
    """
    Fetch a WebCric stream page, find the timesup embed URL,
    fetch that with correct Referer, extract id+pk, build m3u8 URL.
    """
    try:
        # Step 1: fetch the stream page
        r = requests.get(page_url, headers=HEADERS, timeout=15)
        html = r.text

        # Step 2: find the timesup embed URL
        embed_match = re.search(r'(https?://[^\s"\'<>]*timesup\.top[^\s"\'<>]*)', html)
        if not embed_match:
            embed_match = re.search(r'src=["\']([^"\']*hembedplayer[^"\']*)["\']', html)
        
        if not embed_match:
            print(f'No embed URL found in {page_url}')
            return None

        embed_url = embed_match.group(1)
        if embed_url.startswith('//'):
            embed_url = 'https:' + embed_url

        print(f'Found embed URL: {embed_url}')

        # Step 3: fetch embed page with WebCric as referer
        embed_headers = {
            **HEADERS,
            'Referer': page_url,
            'Origin': WEBCRIC_BASE,
        }
        r2 = requests.get(embed_url, headers=embed_headers, timeout=15)
        embed_html = r2.text

        print(f'Embed page status: {r2.status_code}')
        print(f'Embed page snippet: {embed_html[:500]}')

        # Step 4: look for m3u8 directly
        m3u8 = re.search(r'(https?://[^\s"\'<>]+\.m3u8[^\s"\'<>]*)', embed_html)
        if m3u8:
            return m3u8.group(1)

        # Step 5: look for id and pk
        id_m = re.search(r'["\']?id["\']?\s*[:=]\s*["\']?(\d+)', embed_html)
        pk_m = re.search(r'["\']?pk["\']?\s*[:=]\s*["\']?([a-f0-9]{80,})', embed_html)
        ch_m = re.search(r'hembedplayer/([^/\s"\']+)', embed_url)

        if id_m and pk_m and ch_m:
            channel = ch_m.group(1)
            stream_id = id_m.group(1)
            pk = pk_m.group(1)
            url = f'https://muc002.myturn1.top:8088/live/{channel}/playlist.m3u8?id={stream_id}&pk={pk}'
            print(f'Built m3u8: {url}')
            return url

        print(f'Could not extract stream from embed page')
        return None

    except Exception as e:
        print(f'Error resolving {page_url}: {e}')
        return None


def build_matches():
    matches_raw = get_matches_from_webcric()
    result = []

    for match in matches_raw:
        resolved_streams = []
        for page in match['pages']:
            m3u8 = resolve_stream_page(page['url'])
            if m3u8:
                resolved_streams.append({
                    'label': page['label'].encode('ascii', 'ignore').decode('ascii'),
                    'url': m3u8
                })

        if resolved_streams:
            result.append({
                'title': match['title'],
                'streams': resolved_streams
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
