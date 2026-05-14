from flask import Flask, jsonify, Response, request
import requests
import json
import re

app = Flask(__name__)

STREAMS_URL = 'https://raw.githubusercontent.com/Huzzbuzz2/sportsbox-server/main/streams.json'

PROXY_HEADERS = {
    'User-Agent': 'Mozilla/5.0 (Linux; Android 11; Mobile) AppleWebKit/537.36 Chrome/120.0.0.0 Mobile Safari/537.36',
    'Referer': 'https://one.timesup.top/',
    'Origin': 'https://one.timesup.top',
}


@app.route('/matches')
def get_matches():
    try:
        r = requests.get(STREAMS_URL, timeout=10)
        data = r.json()
        matches = data.get('matches', [])

        # Replace stream URLs with proxied versions
        for match in matches:
            for stream in match.get('streams', []):
                original_url = stream.get('url', '')
                if original_url:
                    stream['url'] = request.host_url + 'proxy/playlist?url=' + requests.utils.quote(original_url)

        return jsonify({'matches': matches, 'cached': True})
    except Exception as e:
        return jsonify({'matches': [], 'error': str(e)})


@app.route('/proxy/playlist')
def proxy_playlist():
    url = request.args.get('url', '')
    if not url:
        return 'No URL', 400

    try:
        r = requests.get(url, headers=PROXY_HEADERS, timeout=15)
        content = r.text

        # Fix relative segment URLs to go through our proxy
        base = url.split('playlist.m3u8')[0]
        fixed = []
        for line in content.splitlines():
            if line.startswith('media_'):
                segment_url = base + line
                proxied = request.host_url + 'proxy/segment?url=' + requests.utils.quote(segment_url)
                fixed.append(proxied)
            elif line.startswith('https://') and 'playlist.m3u8' in line:
                proxied = request.host_url + 'proxy/playlist?url=' + requests.utils.quote(line)
                fixed.append(proxied)
            else:
                fixed.append(line)

        return Response('\n'.join(fixed), mimetype='application/vnd.apple.mpegurl')
    except Exception as e:
        return str(e), 500


@app.route('/proxy/segment')
def proxy_segment():
    url = request.args.get('url', '')
    if not url:
        return 'No URL', 400

    try:
        r = requests.get(url, headers=PROXY_HEADERS, timeout=15, stream=True)
        return Response(
            r.iter_content(chunk_size=8192),
            content_type='video/MP2T'
        )
    except Exception as e:
        return str(e), 500


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
