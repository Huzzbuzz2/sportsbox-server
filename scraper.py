from playwright.sync_api import sync_playwright
import json
import time
import requests
import os

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


def scrape_stream(page, url):
    m3u8_url = None
    m3u8_headers = {}
    m3u8_content = None

    def handle_request(request):
        nonlocal m3u8_url, m3u8_headers
        if 'playlist.m3u8' in request.url and m3u8_url is None:
            m3u8_url = request.url
            m3u8_headers = dict(request.headers)
            print(f'Found m3u8: {request.url}')

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

    if m3u8_url and m3u8_headers:
        try:
            # Fetch the actual m3u8 content using the real browser session headers
            r = requests.get(m3u8_url, headers=m3u8_headers, timeout=15)
            if r.status_code == 200 and '#EXTM3U' in r.text:
                m3u8_content = r.text
                print(f'Got m3u8 content ({len(m3u8_content)} bytes)')
                print(m3u8_content[:500])
            else:
                print(f'Failed to fetch m3u8 content: {r.status_code}')
                print(r.text[:200])
        except Exception as e:
            print(f'Error fetching m3u8 content: {e}')

    return m3u8_url, m3u8_headers, m3u8_content


def main():
    results = []
    playlists = {}

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
                m3u8_url, headers, content = scrape_stream(page, stream['url'])
                page.close()

                if m3u8_url:
                    stream_key = match['title'].replace(' ', '_') + '_' + stream['label'].replace(' ', '_')
                    
                    stream_data = {
                        'label': stream['label'],
                        'url': m3u8_url,
                        'headers': {
                            'Referer': headers.get('referer', ''),
                            'Origin': headers.get('origin', ''),
                            'User-Agent': headers.get('user-agent', ''),
                        }
                    }

                    if content:
                        # Save playlist content to file
                        playlist_file = f'playlists/{stream_key}.m3u8'
                        os.makedirs('playlists', exist_ok=True)
                        with open(playlist_file, 'w') as f:
                            f.write(content)
                        stream_data['playlist_file'] = playlist_file
                        stream_data['has_content'] = True
                        print(f'Saved playlist to {playlist_file}')
                    else:
                        stream_data['has_content'] = False

                    resolved_streams.append(stream_data)

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
