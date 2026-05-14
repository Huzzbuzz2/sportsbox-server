from flask import Flask, jsonify
from playwright.sync_api import sync_playwright
import json
import os
import time
import threading

app = Flask(__name__)

CACHE_FILE = 'cache.json'
CACHE_LOCK = threading.Lock()

WEBCRIC_STREAMS = [
    {'name': 'IPL 2026', 'url': 'https://go.webcric.com/watch-ipl-2026-live-cricket-streaming.htm'},
    {'name': 'IPL Stream 2', 'url': 'https://go.webcric.com/ipl-2026-live-cricket-streaming.htm'},
    {'name': 'PAK v BAN', 'url': 'https://go.webcric.com/watch-pakistan-vs-bangladesh-live-cricket-streaming.htm'},
    {'name': 'IPL Hindi', 'url': 'https://go.webcric.com/watch-ipl-2026-in-hindi-live-cricket-streaming.htm'},
]


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
    with open(CACHE_FILE, 'w') as f:
        json.dump({
            'date': time.strftime('%Y-%m-%d'),
            'matches': matches
        }, f)


def scrape_streams():
    matches = []
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        for stream in WEBCRIC_STREAMS:
            m3u8_url = None
            try:
                page = browser.new_page()

                def handle_request(request):
                    nonlocal m3u8_url
                    if 'playlist.m3u8' in request.url and m3u8_url is None:
                        m3u8_url = request.url

                page.on('request', handle_request)
                page.goto(stream['url'], wait_until='networkidle', timeout=30000)
                page.wait_for_timeout(5000)
                page.close()

                if m3u8_url:
                    matches.append({
                        'title': stream['name'],
                        'streams': [{'label': 'Stream 1', 'url': m3u8_url}]
                    })
            except Exception as e:
                print(f"Error scraping {stream['name']}: {e}")

        browser.close()
    return matches


@app.route('/matches')
def get_matches():
    with CACHE_LOCK:
        cached = load_cache()
        if cached is not None:
            return jsonify({'matches': cached, 'cached': True})

        matches = scrape_streams()
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
        matches = scrape_streams()
        if matches:
            save_cache(matches)
        return jsonify({'matches': matches, 'refreshed': True})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)