import json
import os
import sys
import threading
import time
import urllib.error
import urllib.request

from porter.services import ModelApp, PredictionService

service1 = PredictionService(
    model=None,
    name='a-model',
    api_version='0.0.0'
)

service2 = PredictionService(
    model=None,
    name='yet-another-model',
    api_version='1.0.0'
)

service3 = PredictionService(
    model=None,
    name='yet-another-yet-another-model',
    api_version='1.0.0-alpha',
    meta={'arbitrary details': 'about the model'}
)

model_app = ModelApp([service1, service2, service3])


def get(url):
    with urllib.request.urlopen(url) as f:
        return f.read()


def run_app(model_app):
    t = threading.Thread(target=model_app.run, daemon=True)
    t.start()


class Shhh:
    """Silence flask logging."""

    def __init__(self):
        self.devnull = open(os.devnull, 'w')
        self.stdout = sys.stdout
        self.stderr = sys.stderr

    def __enter__(self):
        sys.stdout = self.devnull
        sys.stderr = self.devnull

    def __exit__(self, *exc):
        sys.stdout = self.stdout
        sys.stderr = self.stderr


if __name__ == '__main__':
    with Shhh():
        run_app(model_app)
        time.sleep(0.5)  # give app time to run
        alive_resp = json.loads(get('http://localhost:5000/-/alive').decode('utf-8'))
        ready_resp = json.loads(get('http://localhost:5000/-/alive').decode('utf-8'))
    print('GET /-/alive')
    print(json.dumps(alive_resp, indent=4))
    print('GET /-/ready')
    print(json.dumps(ready_resp, indent=4))
