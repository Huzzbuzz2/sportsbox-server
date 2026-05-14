from playwright.sync_api import sync_playwright
import json
import time

STREAM_PAGES = [
    {'title': 'IPL 2026', 'streams': [
        {'label': 'Stream 1', 'url': 'https://go.webcric.com/watch-ipl-2026-live-cricket-streaming.htm'},
        {'label': 'Stream 2', 'url': 'https://go.webcric.com/ipl-2026-live-cricket-streaming.htm'},
        {'label': 'Stream HD', 'url': 'https://go.webcric.com/watch-ipl-live-cricket-streaming-3.htm'},
        {'label': 'Star Sports', 'url': 'https://go.webcric.com/watch-ipl-2026-on-star-sports-live-cricket-streaming.htm'},
        {'label': 'Willow HD', 'url': 'https://go.webcric.com/watch-ipl-2026-on-willow-live-cricket-streaming.htm'},
        {'label': 'Hindi', 'url': 'https://go.webcric.com/watch-ipl-2026-in-hindi-live-cricket-streaming.htm'},
    ]},
    {'title': 'PAK v BAN', 'streams': [
        {'label': 'Stream 1', 'url': 'https://go.webcric.com/watch-pakistan-vs-bangladesh-live-cricket-streaming.htm'},
        {'label': 'Stream 2', 'url': 'https://go.webcric.com/pakistan-vs-bangladesh-cricket-live-streaming.htm'},
        {'label': 'Stream 3', 'url': 'https://go.webcric.com/pakistan-vs-bangladesh-live-cricket-streaming.htm'},
    ]},
]


def scrape_m3u8(page, url):
    m3u8_url = None
    m3u8_headers = {}

    def handle_request(request):
        nonlocal m3u8_url, m3u8_headers
        if 'playlist.m3u8' in request.url and m3u8_url is None:
            m3u8_url = request.url
            m3u8_headers = request.headers
            print(f'Found m3u8: {request.url}')
            print(f'Headers: {dict(request.headers)}')

    page.on('request', handle_request)

    try:
        page.goto(url, wait_until='networkidle', timeout=30000)
        for _ in range(20):
            if m3u8_url:
                break
            time.sleep(0.5)
    except Exception as e:
        print(f'Error loading {url}: {e}')

    page.remove_listener('request', handle_request)
    return m3u8_url, m3u8_headers


def main():
    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
            viewport={'width': 390, 'height': 844},
        )

        for match in STREAM_PAGES:
            resolved_streams = []
            for stream in match['streams']:
                print(f'Scraping {stream["label"]} for {match["title"]}...')
                page = context.new_page()
                m3u8, headers = scrape_m3u8(page, stream['url'])
                page.close()

                if m3u8:
                    # Extract key headers for playback
                    playback_headers = {
                        'Referer': headers.get('referer', 'https://one.timesup.top/'),
                        'Origin': headers.get('origin', 'https://one.timesup.top'),
                        'User-Agent': headers.get('user-agent', ''),
                        'Cookie': headers.get('cookie', ''),
                    }
                    resolved_streams.append({
                        'label': stream['label'],
                        'url': m3u8,
                        'headers': playback_headers
                    })
                else:
                    print(f'No m3u8 found for {stream["label"]}')

            if resolved_streams:
                results.append({
                    'title': match['title'],
                    'streams': resolved_streams
                })

        browser.close()

    with open('streams.json', 'w') as f:
        json.dump({
            'updated': time.strftime('%Y-%m-%d %H:%M:%S'),
            'matches': results
        }, f, indent=2)

    print(f'Done. Found {len(results)} matches.')


if __name__ == '__main__':
    main()
