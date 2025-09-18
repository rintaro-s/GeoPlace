#!/usr/bin/env python3
"""Simple mock VLM HTTP server for local testing.
Usage:
  python scripts/mock_vlm.py --port 8002
Returns JSON: category, colors, size, orientation, details
"""
from http.server import BaseHTTPRequestHandler, HTTPServer
import json
from base64 import b64decode
import argparse

class Handler(BaseHTTPRequestHandler):
    def do_POST(self):
        length = int(self.headers.get('content-length', '0'))
        body = self.rfile.read(length)
        try:
            j = json.loads(body)
            img_b64 = j.get('image_b64')
            if img_b64:
                # attempt decode to check it's valid
                _ = b64decode(img_b64[:100])
            out = {
                'category': 'sign',
                'colors': ['white','red'],
                'size': 'small',
                'orientation': 'front',
                'details': ['text:STOP']
            }
            resp = json.dumps(out).encode('utf-8')
            self.send_response(200)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(resp)))
            self.end_headers()
            self.wfile.write(resp)
        except Exception as e:
            msg = json.dumps({'error': str(e)}).encode('utf-8')
            self.send_response(500)
            self.send_header('Content-Type', 'application/json')
            self.send_header('Content-Length', str(len(msg)))
            self.end_headers()
            self.wfile.write(msg)

if __name__ == '__main__':
    p = argparse.ArgumentParser()
    p.add_argument('--port', type=int, default=8002)
    args = p.parse_args()
    server = HTTPServer(('0.0.0.0', args.port), Handler)
    print(f"Mock VLM server listening on port {args.port}")
    server.serve_forever()
