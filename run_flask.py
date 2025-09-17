#!/usr/bin/env python3
"""
Simple Flask runner that doesn't require heavy dependencies
"""
from flask import Flask, send_file, jsonify, request, send_from_directory
from pathlib import Path
import json
from PIL import Image
from io import BytesIO
import sys
import os

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))

app = Flask(__name__)

ROOT = Path(__file__).parent
DATA_DIR = ROOT / 'data'
CANVAS_PATH = DATA_DIR / 'canvas.png'
ASSETS_DIR = ROOT / 'assets'
OBJECTS_JSON = ASSETS_DIR / 'objects.json'

# Settings
TILE_SIZE = 32
CANVAS_WIDTH = 20000
CANVAS_HEIGHT = 20000

# Global state
modified_tiles = set()

def ensure_canvas():
    """Ensure canvas exists"""
    if not CANVAS_PATH.exists():
        CANVAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGBA', (CANVAS_WIDTH, CANVAS_HEIGHT), (0,0,0,0))
        img.save(CANVAS_PATH)

def load_canvas():
    """Load main canvas"""
    ensure_canvas()
    Image.MAX_IMAGE_PIXELS = 2000000000
    return Image.open(CANVAS_PATH).convert('RGBA')

@app.route('/')
def index():
    """Main page"""
    return '''
    <h1>GeoPlace Flask Server</h1>
    <ul>
        <li><a href="/paint">Paint Tool</a></li>
        <li><a href="/world">3D World</a></li>
        <li><a href="/admin">Admin</a></li>
    </ul>
    '''

@app.route('/paint')
def paint():
    """Paint tool page"""
    with open(ROOT / 'frontend' / 'paint_new.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/world')
def world():
    """3D world page"""
    with open(ROOT / 'frontend' / 'world_new.html', 'r', encoding='utf-8') as f:
        return f.read()

@app.route('/admin')
def admin():
    """Admin page"""
    with open(ROOT / 'frontend' / 'admin.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace API calls
    content = content.replace('http://127.0.0.1:8001/api/', 'http://127.0.0.1:5000/')
    content = content.replace('/api/', '/')
    
    return content

@app.route('/tile/<int:tile_x>/<int:tile_y>')
def get_tile(tile_x, tile_y):
    """Serve tile image directly"""
    try:
        # Check for individual tile file first
        tile_path = DATA_DIR / 'tiles' / f'tile_{tile_x}_{tile_y}.png'
        if tile_path.exists():
            return send_file(tile_path, mimetype='image/png')
        
        # Extract from main canvas
        canvas_img = load_canvas()
        
        start_x = tile_x * TILE_SIZE
        start_y = tile_y * TILE_SIZE
        end_x = min(start_x + TILE_SIZE, canvas_img.width)
        end_y = min(start_y + TILE_SIZE, canvas_img.height)
        
        # Check bounds
        if start_x >= canvas_img.width or start_y >= canvas_img.height:
            # Create transparent tile
            tile_img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
        else:
            # Extract tile
            tile_img = canvas_img.crop((start_x, start_y, end_x, end_y))
            
            # Pad if needed
            if tile_img.width < TILE_SIZE or tile_img.height < TILE_SIZE:
                padded_tile = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
                padded_tile.paste(tile_img, (0, 0))
                tile_img = padded_tile
        
        # Return as PNG
        buffer = BytesIO()
        tile_img.save(buffer, format='PNG', optimize=True)
        buffer.seek(0)
        
        return send_file(buffer, mimetype='image/png')
        
    except Exception as e:
        print(f"Error serving tile {tile_x},{tile_y}: {e}")
        # Return red error tile
        error_tile = Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (255, 0, 0, 128))
        buffer = BytesIO()
        error_tile.save(buffer, format='PNG')
        buffer.seek(0)
        return send_file(buffer, mimetype='image/png')

@app.route('/paint_api', methods=['POST'])
def paint_api():
    """Handle paint data submission"""
    try:
        data = request.get_json()
        tile_x = data['tile_x']
        tile_y = data['tile_y']
        pixels = data['pixels']
        
        # Load canvas
        canvas_img = load_canvas()
        
        # Apply pixel changes
        start_x = tile_x * TILE_SIZE
        start_y = tile_y * TILE_SIZE
        
        for pixel in pixels:
            px, py, r, g, b, a = pixel
            x, y = start_x + px, start_y + py
            if 0 <= x < canvas_img.width and 0 <= y < canvas_img.height:
                canvas_img.putpixel((x, y), (r, g, b, a))
        
        # Save canvas
        canvas_img.save(CANVAS_PATH)
        
        # Track modified tile
        modified_tiles.add((tile_x, tile_y))
        
        # Also save individual tile
        tile_dir = DATA_DIR / 'tiles'
        tile_dir.mkdir(parents=True, exist_ok=True)
        
        tile_img = canvas_img.crop((start_x, start_y, start_x + TILE_SIZE, start_y + TILE_SIZE))
        tile_img.save(tile_dir / f'tile_{tile_x}_{tile_y}.png')
        
        return jsonify({'ok': True, 'modified_tiles': len(modified_tiles)})
        
    except Exception as e:
        print(f"Paint API error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/generate_api', methods=['POST'])
def generate_api():
    """Handle 3D generation request"""
    try:
        data = request.get_json() or {}
        tiles = data.get('tiles') or list(modified_tiles)
        
        if not tiles:
            return jsonify({'ok': False, 'message': 'no modified tiles'})
        
        # Simple mock generation for now
        job_id = f"job_{len(modified_tiles)}"
        
        return jsonify({
            'job_id': job_id, 
            'tiles': tiles,
            'message': f'Started generation for {len(tiles)} tiles'
        })
        
    except Exception as e:
        print(f"Generate API error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/objects.json')
def objects_json():
    """Serve objects JSON"""
    if OBJECTS_JSON.exists():
        with open(OBJECTS_JSON, 'r', encoding='utf-8') as f:
            return jsonify(json.load(f))
    return jsonify([])

@app.route('/assets/<path:filename>')
def assets(filename):
    """Serve asset files"""
    return send_from_directory(ASSETS_DIR, filename)

@app.route('/data/<path:filename>')
def data_files(filename):
    """Serve data files"""
    return send_from_directory(DATA_DIR, filename)

if __name__ == '__main__':
    print("=" * 50)
    print("🚀 GeoPlace Flask Server Starting")
    print("=" * 50)
    print("Paint tool: http://127.0.0.1:5000/paint")
    print("3D World:   http://127.0.0.1:5000/world")
    print("Admin:      http://127.0.0.1:5000/admin")
    print("=" * 50)
    
    app.run(host='127.0.0.1', port=5000, debug=True)
