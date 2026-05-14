from playwright.sync_api import sync_playwright
import json
import time
import requests
import os
import re
from bs4 import BeautifulSoup

WEBCRIC_BASE = 'https://go.webcric.com'

HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://go.webcric.com/',
}


def get_todays_matches():
    """Scrape WebCric homepage to find today's matches and stream pages."""
    try:
        r = requests.get(WEBCRIC_BASE + '/', headers=HEADERS, timeout=15)
        soup = BeautifulSoup(r.text, 'html.parser')
        matches = []

        for ul in soup.find_all('ul'):
            links = ul.find_all('a', href=True)
            stream_links = [a for a in links if '.htm' in a.get('href', '')]
            if not stream_links:
                continue

            # Get match title from previous sibling
            title = None
            for sibling in ul.previous_siblings:
                t = sibling.get_text(strip=True) if hasattr(sibling, 'get_text') else str(sibling).strip()
                if t and t not in ['\n', '']:
                    title = t
                    break

            if not title:
                continue

            # Skip nav items
            skip = ['scorecard', 'ranking', 'schedule', 'news', 'stat', 'result']
            if any(s in title.lower() for s in skip):
                continue

            streams = []
            for a in stream_links:
                href = a['href']
                if not href.startswith('http'):
                    href = WEBCRIC_BASE + '/' + href.lstrip('/')
                label = a.get_text(strip=True) or 'Stream'
                streams.append({'label': label, 'url': href})

            if streams:
                clean_title = title.encode('ascii', 'ignore').decode('ascii').strip()
                matches.append({'title': clean_title, 'streams': streams})
                print(f'Found match: {clean_title} ({len(streams)} streams)')

        return matches
    except Exception as e:
        print(f'Error fetching WebCric homepage: {e}')
        return []


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
            r = requests.get(m3u8_url, headers=m3u8_headers, timeout=15)
            if r.status_code == 200 and '#EXTM3U' in r.text:
                level2 = re.search(r'(https?://[^\s]+playlist\.m3u8[^\s]*)', r.text)
                if level2:
                    level2_url = level2.group(1)
                    r2 = requests.get(level2_url, headers=m3u8_headers, timeout=15)
                    if r2.status_code == 200 and '#EXTM3U' in r2.text:
                        base = level2_url.split('playlist.m3u8')[0]
                        fixed = []
                        for line in r2.text.splitlines():
                            if line.startswith('media_'):
                                fixed.append(base + line)
                            else:
                                fixed.append(line)
                        m3u8_content = '\n'.join(fixed)
                        m3u8_url = level2_url
                    else:
                        m3u8_content = r.text
                else:
                    m3u8_content = r.text
        except Exception as e:
            print(f'Error fetching m3u8: {e}')

    return m3u8_url, m3u8_headers, m3u8_content


def main():
    # Step 1: Get today's matches from WebCric homepage
    print('Fetching today\'s matches from WebCric...')
    todays_matches = get_todays_matches()
    print(f'Found {len(todays_matches)} matches on WebCric today')

    if not todays_matches:
        print('No matches found today')
        # Save empty results
        with open('streams.json', 'w') as f:
            json.dump({'updated': time.strftime('%Y-%m-%d %H:%M:%S'), 'matches': []}, f)
        return

    results = []

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=True)
        context = browser.new_context(
            user_agent='Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
            viewport={'width': 390, 'height': 844},
        )

        os.makedirs('playlists', exist_ok=True)

        for match in todays_matches:
            print(f'\nScraping streams for: {match["title"]}')
            resolved_streams = []

            for stream in match['streams']:
                print(f'  Scraping {stream["label"]}...')
                page = context.new_page()
                m3u8_url, headers, content = scrape_stream(page, stream['url'])
                page.close()

                if m3u8_url:
                    stream_key = match['title'].replace(' ', '_')[:30] + '_' + stream['label'].replace(' ', '_')[:20]
                    stream_key = re.sub(r'[^a-zA-Z0-9_]', '', stream_key)

                    stream_data = {
                        'label': stream['label'].encode('ascii', 'ignore').decode('ascii'),
                        'url': m3u8_url,
                        'headers': {
                            'Referer': headers.get('referer', ''),
                            'Origin': headers.get('origin', ''),
                            'User-Agent': headers.get('user-agent', ''),
                        }
                    }

                    if content:
                        playlist_file = f'playlists/{stream_key}.m3u8'
                        with open(playlist_file, 'w') as f:
                            f.write(content)
                        stream_data['playlist_file'] = playlist_file
                        stream_data['has_content'] = True
                        print(f'  Saved to {playlist_file}')
                    else:
                        stream_data['has_content'] = False

                    resolved_streams.append(stream_data)
                else:
                    print(f'  No stream found for {stream["label"]}')

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

    print(f'\nDone. Saved {len(results)} matches to streams.json')


if __name__ == '__main__':
    main()
