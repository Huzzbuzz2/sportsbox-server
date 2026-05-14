from flask import Flask, jsonify
import requests
import json

app = Flask(__name__)

STREAMS_URL = 'https://raw.githubusercontent.com/Huzzbuzz2/sportsbox-server/main/streams.json'


@app.route('/matches')
def get_matches():
    try:
        r = requests.get(STREAMS_URL, timeout=10)
        data = r.json()
        return jsonify({'matches': data.get('matches', []), 'cached': True})
    except Exception as e:
        return jsonify({'matches': [], 'error': str(e)})


@app.route('/health')
def health():
    return jsonify({'status': 'ok'})


if __name__ == '__main__':
    app.run(host='0.0.0.0', port=5000)
