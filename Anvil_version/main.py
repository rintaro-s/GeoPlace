"""
GeoPlace - Anvil Version
Complete rewrite using Anvil framework for better image handling and UI
"""
import anvil.server
import anvil.media
import anvil.tables as tables
from anvil.tables import app_tables
import anvil.users
import anvil.email
from anvil import *
import time
import json
import os
from pathlib import Path
import base64
from PIL import Image
import io
import threading
import queue
import requests

# Configuration
TILE_SIZE = 32
CANVAS_WIDTH = 20000
CANVAS_HEIGHT = 20000
TILES_DIR = Path("E:/files/GeoPLace-tmp/images")
ASSETS_DIR = Path("./assets")
GLB_DIR = ASSETS_DIR / "glb"

# Ensure directories exist
TILES_DIR.mkdir(parents=True, exist_ok=True)
GLB_DIR.mkdir(parents=True, exist_ok=True)

# Global state
canvas_data = {}
modified_tiles = set()
generation_jobs = {}
websocket_clients = []

class TileManager:
    """Manages tile operations and caching"""
    
    @staticmethod
    def get_tile_path(tile_x, tile_y):
        """Get the file path for a tile"""
        return TILES_DIR / f"tile_{tile_x}_{tile_y}.png"
    
    @staticmethod
    def load_tile(tile_x, tile_y):
        """Load a tile image, return as PIL Image or create transparent"""
        tile_path = TileManager.get_tile_path(tile_x, tile_y)
        
        if tile_path.exists():
            try:
                return Image.open(tile_path).convert('RGBA')
            except Exception as e:
                print(f"Error loading tile {tile_x},{tile_y}: {e}")
        
        # Return transparent tile
        return Image.new('RGBA', (TILE_SIZE, TILE_SIZE), (0, 0, 0, 0))
    
    @staticmethod
    def save_tile(tile_x, tile_y, image_data):
        """Save tile image data"""
        tile_path = TileManager.get_tile_path(tile_x, tile_y)
        
        if isinstance(image_data, list):
            # Convert pixel array to PIL Image
            img = Image.new('RGBA', (TILE_SIZE, TILE_SIZE))
            img.putdata([tuple(p) for p in image_data])
        else:
            img = image_data
        
        img.save(tile_path)
        modified_tiles.add((tile_x, tile_y))
        return tile_path
    
    @staticmethod
    def get_tile_as_media(tile_x, tile_y):
        """Get tile as Anvil Media object"""
        img = TileManager.load_tile(tile_x, tile_y)
        
        # Convert to bytes
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        buffer.seek(0)
        
        return anvil.media.from_file(
            buffer, 
            f"tile_{tile_x}_{tile_y}.png", 
            "image/png"
        )

class AIWorkflow:
    """AI pipeline for VLM -> SD -> TripoSR -> 3D"""
    
    @staticmethod
    def analyze_with_vlm(image_bytes):
        """Analyze image with LM Studio VLM"""
        try:
            base64_image = base64.b64encode(image_bytes).decode('utf-8')
            
            payload = {
                "model": "gemma-3-4b-it",
                "messages": [
                    {
                        "role": "user",
                        "content": [
                            {
                                "type": "image_url",
                                "image_url": {
                                    "url": f"data:image/png;base64,{base64_image}"
                                }
                            },
                            {
                                "type": "text",
                                "text": """この画像に写っているオブジェクトを分析して、以下の形式で回答してください：

カテゴリ: [house/tree/river/person/car/building/nature/other のいずれか]
色: [主要な色を2-3個、英語で]
サイズ: [small/medium/large のいずれか]
向き: [front/side/back/diagonal のいずれか]
特徴: [窓、屋根、葉、枝などの特徴を2-3個、日本語で]"""
                            }
                        ]
                    }
                ],
                "max_tokens": 200,
                "temperature": 0.3
            }
            
            response = requests.post(
                "http://localhost:1234/v1/chat/completions",
                headers={'Content-Type': 'application/json'},
                json=payload,
                timeout=30
            )
            
            if response.status_code == 200:
                result = response.json()
                content = result['choices'][0]['message']['content']
                return AIWorkflow.parse_vlm_response(content)
            else:
                return AIWorkflow.fallback_attributes()
                
        except Exception as e:
            print(f"VLM analysis error: {e}")
            return AIWorkflow.fallback_attributes()
    
    @staticmethod
    def parse_vlm_response(content):
        """Parse VLM response into structured data"""
        import re
        
        try:
            category_match = re.search(r'カテゴリ[：:]\s*(\w+)', content)
            colors_match = re.search(r'色[：:]\s*([^\n]+)', content)
            size_match = re.search(r'サイズ[：:]\s*(\w+)', content)
            orientation_match = re.search(r'向き[：:]\s*(\w+)', content)
            details_match = re.search(r'特徴[：:]\s*([^\n]+)', content)
            
            return {
                'category': category_match.group(1) if category_match else 'object',
                'colors': [c.strip() for c in re.split(r'[,、]', colors_match.group(1))] if colors_match else ['gray'],
                'size': size_match.group(1) if size_match else 'medium',
                'orientation': orientation_match.group(1) if orientation_match else 'front',
                'details': [d.strip() for d in re.split(r'[,、]', details_match.group(1))] if details_match else ['オブジェクト']
            }
        except:
            return AIWorkflow.fallback_attributes()
    
    @staticmethod
    def fallback_attributes():
        """Fallback attributes when VLM fails"""
        return {
            'category': 'object',
            'colors': ['gray'],
            'size': 'medium',
            'orientation': 'front',
            'details': ['シンプルなオブジェクト']
        }
    
    @staticmethod
    def generate_prompt(attributes):
        """Generate SD prompt from attributes"""
        colors = ', '.join(attributes['colors'])
        details = ', '.join(attributes['details'])
        
        return (
            f"voxel-style {attributes['category']}, {attributes['size']} size, "
            f"primary colors: {colors}, features: {details}, "
            f"low-poly, game-friendly, 3D render, {attributes['orientation']} view, "
            f"clean background, high quality, detailed"
        )
    
    @staticmethod
    def run_complete_workflow(tile_x, tile_y):
        """Run complete AI workflow for a tile"""
        workflow_id = f"tile_{tile_x}_{tile_y}_{int(time.time())}"
        
        try:
            # Load tile image
            tile_img = TileManager.load_tile(tile_x, tile_y)
            buffer = io.BytesIO()
            tile_img.save(buffer, format='PNG')
            image_bytes = buffer.getvalue()
            
            # Step 1: VLM Analysis
            print(f"[{workflow_id}] Step 1: VLM analysis...")
            attributes = AIWorkflow.analyze_with_vlm(image_bytes)
            
            # Step 2: Generate prompt
            print(f"[{workflow_id}] Step 2: Generating prompt...")
            prompt = AIWorkflow.generate_prompt(attributes)
            
            # Step 3: Stable Diffusion (placeholder - would integrate with existing SD code)
            print(f"[{workflow_id}] Step 3: SD generation...")
            # For now, use original image as placeholder
            sd_image_bytes = image_bytes
            
            # Step 4: TripoSR (placeholder - would integrate with existing TripoSR code)
            print(f"[{workflow_id}] Step 4: TripoSR generation...")
            glb_path = GLB_DIR / f"{workflow_id}.glb"
            
            # Create placeholder GLB
            with open(glb_path, 'wb') as f:
                f.write(b'GLB_PLACEHOLDER_ANVIL\n')
                f.write(sd_image_bytes)
            
            # Calculate world position
            world_x = tile_x * 1.0  # 1 tile = 1 meter
            world_z = tile_y * 1.0
            
            size_multiplier = {
                'small': 0.5,
                'medium': 1.0,
                'large': 1.5
            }.get(attributes['size'], 1.0)
            
            metadata = {
                'workflow_id': workflow_id,
                'tile_coords': [tile_x, tile_y],
                'world_position': [world_x, 0, world_z],
                'scale': size_multiplier,
                'attributes': attributes,
                'prompt': prompt,
                'timestamp': time.time()
            }
            
            # Register in objects.json
            ObjectManager.register_object(workflow_id, metadata, glb_path)
            
            return glb_path, metadata
            
        except Exception as e:
            print(f"[{workflow_id}] Workflow failed: {e}")
            # Create fallback
            fallback_path = GLB_DIR / f"{workflow_id}_fallback.glb"
            with open(fallback_path, 'wb') as f:
                f.write(b'GLB_FALLBACK_ANVIL\n')
            
            return fallback_path, {'error': str(e), 'workflow_id': workflow_id}

class ObjectManager:
    """Manages 3D objects and objects.json"""
    
    @staticmethod
    def load_objects():
        """Load objects from objects.json"""
        objects_file = GLB_DIR / 'objects.json'
        if objects_file.exists():
            try:
                with open(objects_file, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except:
                return []
        return []
    
    @staticmethod
    def save_objects(objects):
        """Save objects to objects.json"""
        objects_file = GLB_DIR / 'objects.json'
        with open(objects_file, 'w', encoding='utf-8') as f:
            json.dump(objects, f, ensure_ascii=False, indent=2)
    
    @staticmethod
    def register_object(object_id, metadata, glb_path):
        """Register a new 3D object"""
        objects = ObjectManager.load_objects()
        
        # Remove existing object with same ID
        objects = [obj for obj in objects if obj.get('id') != object_id]
        
        # Add new object
        new_object = {
            'id': object_id,
            'x': metadata['world_position'][0],
            'y': metadata['world_position'][1], 
            'z': metadata['world_position'][2],
            'rotation': [0, 0, 0],
            'scale': metadata['scale'],
            'glb_url': f'/assets/glb/{glb_path.name}',
            'metadata': metadata,
            'created_at': time.time()
        }
        
        objects.append(new_object)
        ObjectManager.save_objects(objects)
        
        print(f"Registered 3D object: {object_id} at ({new_object['x']}, {new_object['y']}, {new_object['z']})")

# Anvil Server Functions
@anvil.server.callable
def get_tile(tile_x, tile_y):
    """Get a tile as media object"""
    return TileManager.get_tile_as_media(tile_x, tile_y)

@anvil.server.callable
def save_tile_data(tile_x, tile_y, pixel_data):
    """Save tile pixel data"""
    try:
        TileManager.save_tile(tile_x, tile_y, pixel_data)
        return {'success': True, 'modified_count': len(modified_tiles)}
    except Exception as e:
        return {'success': False, 'error': str(e)}

@anvil.server.callable
def get_modified_tiles():
    """Get list of modified tiles"""
    return list(modified_tiles)

@anvil.server.callable
def start_3d_generation(tile_coords=None):
    """Start 3D generation for specified tiles or all modified tiles"""
    if tile_coords is None:
        tile_coords = list(modified_tiles)
    
    if not tile_coords:
        return {'success': False, 'message': 'No tiles to process'}
    
    job_id = f"job_{int(time.time() * 1000)}"
    generation_jobs[job_id] = {
        'status': 'queued',
        'tiles': tile_coords,
        'progress': 0,
        'total': len(tile_coords),
        'created_at': time.time()
    }
    
    # Start generation in background thread
    def run_generation():
        generation_jobs[job_id]['status'] = 'processing'
        
        for i, (tile_x, tile_y) in enumerate(tile_coords):
            try:
                glb_path, metadata = AIWorkflow.run_complete_workflow(tile_x, tile_y)
                generation_jobs[job_id]['progress'] = i + 1
                generation_jobs[job_id]['current_tile'] = f"tile_{tile_x}_{tile_y}"
            except Exception as e:
                print(f"Generation failed for tile {tile_x},{tile_y}: {e}")
        
        generation_jobs[job_id]['status'] = 'completed'
        # Clear processed tiles from modified set
        for tile_coord in tile_coords:
            modified_tiles.discard(tile_coord)
    
    threading.Thread(target=run_generation, daemon=True).start()
    
    return {'success': True, 'job_id': job_id, 'tiles': tile_coords}

@anvil.server.callable
def get_job_status(job_id):
    """Get status of a generation job"""
    return generation_jobs.get(job_id, {'status': 'not_found'})

@anvil.server.callable
def get_3d_objects():
    """Get all 3D objects for world display"""
    return ObjectManager.load_objects()

@anvil.server.callable
def get_canvas_info():
    """Get canvas information"""
    return {
        'width': CANVAS_WIDTH,
        'height': CANVAS_HEIGHT,
        'tile_size': TILE_SIZE,
        'tiles_x': CANVAS_WIDTH // TILE_SIZE,
        'tiles_y': CANVAS_HEIGHT // TILE_SIZE
    }

if __name__ == "__main__":
    print("GeoPlace Anvil Server Starting...")
    print(f"Tiles directory: {TILES_DIR}")
    print(f"Assets directory: {GLB_DIR}")
    
    # Start Anvil server
    anvil.server.wait_forever()
