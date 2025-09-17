#!/usr/bin/env python3
"""
Flask-based frontend hosting with direct tile serving
Replaces the broken FastAPI static file + API approach
"""
from flask import Flask, render_template_string, send_file, jsonify, request, send_from_directory
from flask_socketio import SocketIO, emit
from pathlib import Path
import json
from PIL import Image
from io import BytesIO
import sys
import os

# Add backend to path
sys.path.insert(0, str(Path(__file__).parent / 'backend'))
from backend.config import settings
from backend import pipeline

app = Flask(__name__)
app.config['SECRET_KEY'] = 'geoplace-secret-key'
socketio = SocketIO(app, cors_allowed_origins="*")

ROOT = Path(__file__).parent
DATA_DIR = ROOT / 'data'
CANVAS_PATH = DATA_DIR / 'canvas.png'
ASSETS_DIR = ROOT / 'assets'
OBJECTS_JSON = ASSETS_DIR / 'objects.json'

# Global state
modified_tiles = set()
current_jobs = {}

def ensure_canvas():
    """Ensure canvas exists"""
    if not CANVAS_PATH.exists():
        CANVAS_PATH.parent.mkdir(parents=True, exist_ok=True)
        img = Image.new('RGBA', (settings.canvas_width, settings.canvas_height), (0,0,0,0))
        img.save(CANVAS_PATH)

def load_canvas():
    """Load main canvas"""
    ensure_canvas()
    Image.MAX_IMAGE_PIXELS = 2000000000
    return Image.open(CANVAS_PATH).convert('RGBA')

def load_objects():
    """Load 3D objects list"""
    if OBJECTS_JSON.exists():
        with open(OBJECTS_JSON, 'r', encoding='utf-8') as f:
            return json.load(f)
    return []

def save_objects(objects):
    """Save 3D objects list"""
    ASSETS_DIR.mkdir(parents=True, exist_ok=True)
    with open(OBJECTS_JSON, 'w', encoding='utf-8') as f:
        json.dump(objects, f, ensure_ascii=False, indent=2)

@app.route('/')
def index():
    """Main page - redirect to paint"""
    return '<a href="/paint">Paint Tool</a> | <a href="/world">3D World</a> | <a href="/admin">Admin</a>'

@app.route('/paint')
def paint():
    """Paint tool page"""
    with open(ROOT / 'frontend' / 'paint.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace API calls with Flask routes
    content = content.replace('/api/tile/', '/tile/')
    content = content.replace('/api/paint', '/paint_api')
    content = content.replace('/api/generate', '/generate_api')
    content = content.replace('ws://127.0.0.1:8001/ws', '/socket.io/')
    
    return content

@app.route('/world')
def world():
    """3D world page"""
    with open(ROOT / 'frontend' / 'world.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace API calls with Flask routes
    content = content.replace('/api/objects.json', '/objects.json')
    content = content.replace('ws://127.0.0.1:8001/ws', '/socket.io/')
    
    return content

@app.route('/admin')
def admin():
    """Admin page"""
    with open(ROOT / 'frontend' / 'admin.html', 'r', encoding='utf-8') as f:
        content = f.read()
    
    # Replace API calls with Flask routes
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
        
        start_x = tile_x * settings.tile_px
        start_y = tile_y * settings.tile_px
        end_x = min(start_x + settings.tile_px, canvas_img.width)
        end_y = min(start_y + settings.tile_px, canvas_img.height)
        
        # Check bounds
        if start_x >= canvas_img.width or start_y >= canvas_img.height:
            # Create transparent tile
            tile_img = Image.new('RGBA', (settings.tile_px, settings.tile_px), (0, 0, 0, 0))
        else:
            # Extract tile
            tile_img = canvas_img.crop((start_x, start_y, end_x, end_y))
            
            # Pad if needed
            if tile_img.width < settings.tile_px or tile_img.height < settings.tile_px:
                padded_tile = Image.new('RGBA', (settings.tile_px, settings.tile_px), (0, 0, 0, 0))
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
        error_tile = Image.new('RGBA', (32, 32), (255, 0, 0, 128))
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
        start_x = tile_x * settings.tile_px
        start_y = tile_y * settings.tile_px
        
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
        
        tile_img = canvas_img.crop((start_x, start_y, start_x + settings.tile_px, start_y + settings.tile_px))
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
        
        job_id = f"job_{len(current_jobs)}"
        current_jobs[job_id] = {
            'status': 'queued',
            'tiles': tiles,
            'progress': 'Starting generation...'
        }
        
        # Start generation in background
        def run_generation():
            try:
                for i, (tile_x, tile_y) in enumerate(tiles):
                    current_jobs[job_id]['progress'] = f'Processing tile {i+1}/{len(tiles)}: ({tile_x}, {tile_y})'
                    
                    # Load tile image
                    tile_path = DATA_DIR / 'tiles' / f'tile_{tile_x}_{tile_y}.png'
                    if tile_path.exists():
                        with open(tile_path, 'rb') as f:
                            tile_bytes = f.read()
                        
                        # Run 3D generation pipeline
                        try:
                            from backend.workflows.generate_3d import run_complete_3d_workflow, register_3d_object
                            glb_path, metadata = run_complete_3d_workflow(tile_bytes, tile_x, tile_y)
                            register_3d_object(glb_path, metadata, tile_x, tile_y)
                            
                            # Emit progress via SocketIO
                            socketio.emit('job_progress', {
                                'job_id': job_id,
                                'tile': f'{tile_x},{tile_y}',
                                'progress': f'{i+1}/{len(tiles)}',
                                'glb_path': str(glb_path)
                            })
                            
                        except Exception as e:
                            print(f"Generation failed for tile {tile_x},{tile_y}: {e}")
                
                current_jobs[job_id]['status'] = 'completed'
                socketio.emit('job_done', {'job_id': job_id})
                
            except Exception as e:
                current_jobs[job_id]['status'] = 'failed'
                current_jobs[job_id]['error'] = str(e)
                socketio.emit('job_error', {'job_id': job_id, 'error': str(e)})
        
        import threading
        threading.Thread(target=run_generation, daemon=True).start()
        
        return jsonify({'job_id': job_id, 'tiles': tiles})
        
    except Exception as e:
        print(f"Generate API error: {e}")
        return jsonify({'ok': False, 'error': str(e)}), 500

@app.route('/objects.json')
def objects_json():
    """Serve objects JSON"""
    return jsonify(load_objects())

@app.route('/assets/<path:filename>')
def assets(filename):
    """Serve asset files"""
    return send_from_directory(ASSETS_DIR, filename)

@app.route('/data/<path:filename>')
def data_files(filename):
    """Serve data files"""
    return send_from_directory(DATA_DIR, filename)

@socketio.on('connect')
def handle_connect():
    """Handle WebSocket connection"""
    emit('hello', {
        'objects': load_objects(),
        'modified_tiles': list(modified_tiles)
    })

@socketio.on('ping')
def handle_ping():
    """Handle ping"""
    emit('pong')

if __name__ == '__main__':
    print("Starting Flask app with SocketIO...")
    print("Paint tool: http://127.0.0.1:5000/paint")
    print("3D World: http://127.0.0.1:5000/world")
    print("Admin: http://127.0.0.1:5000/admin")
    
    socketio.run(app, host='127.0.0.1', port=5000, debug=True)
