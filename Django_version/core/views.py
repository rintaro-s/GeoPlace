from django.shortcuts import render
from django.http import JsonResponse, HttpResponse
from django.views.decorators.csrf import csrf_exempt
from django.views.decorators.http import require_http_methods
from django.conf import settings
import json
import os
from PIL import Image
import io

def serve_static_file(request, file_path):
    """Serve original HTML files directly from frontend directory"""
    try:
        frontend_path = os.path.join(settings.BASE_DIR, '..', 'frontend', file_path)
        with open(frontend_path, 'r', encoding='utf-8') as f:
            content = f.read()
        return HttpResponse(content, content_type='text/html')
    except FileNotFoundError:
        return HttpResponse("File not found", status=404)

# API endpoints that match the original backend expectations
@csrf_exempt
@require_http_methods(["GET"])
def get_tile(request, tile_x, tile_y):
    """Serve tile images - prioritize data/tiles, then E: drive, with detailed logging"""
    import logging
    logger = logging.getLogger(__name__)
    
    try:
        # Priority order: E: drive first (since data/tiles doesn't exist), then local data
        possible_paths = [
            os.path.join(r'E:\files\GeoPLace-tmp\images', f"tile_{tile_x}_{tile_y}.png"),
            os.path.join(settings.BASE_DIR, '..', 'data', 'tiles', f"tile_{tile_x}_{tile_y}.png"),
        ]
        
        logger.info(f"Requesting tile {tile_x},{tile_y}")
        
        for i, tile_path in enumerate(possible_paths):
            logger.info(f"Checking path {i+1}: {tile_path}")
            if os.path.exists(tile_path):
                logger.info(f"Found tile at: {tile_path}")
                try:
                    with open(tile_path, 'rb') as f:
                        image_data = f.read()
                    logger.info(f"Successfully read {len(image_data)} bytes from {tile_path}")
                    response = HttpResponse(image_data, content_type='image/png')
                    response['Cache-Control'] = 'no-cache'
                    return response
                except Exception as read_error:
                    logger.error(f"Error reading file {tile_path}: {read_error}")
                    continue
            else:
                logger.info(f"File not found: {tile_path}")
        
        # If no real tile found, create a distinctive test tile
        logger.info(f"No real tile found for {tile_x},{tile_y}, creating test tile")
        
        # Create a VERY bright, unmistakable test pattern
        img = Image.new('RGB', (32, 32), (255, 0, 255))  # Bright magenta background
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        
        # Bright yellow border
        draw.rectangle([0, 0, 31, 31], outline=(255, 255, 0), width=3)
        
        # Bright cyan center
        draw.rectangle([8, 8, 23, 23], fill=(0, 255, 255))
        
        # Add coordinate text in black
        try:
            draw.text((2, 2), f"{tile_x}", fill=(0, 0, 0))
            draw.text((2, 20), f"{tile_y}", fill=(0, 0, 0))
        except:
            pass
            
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        logger.info(f"Created test tile for {tile_x},{tile_y} - {len(buffer.getvalue())} bytes")
        
        response = HttpResponse(buffer.getvalue(), content_type='image/png')
        response['Cache-Control'] = 'no-cache'
        return response
            
    except Exception as e:
        logger.error(f"Critical error in get_tile({tile_x},{tile_y}): {e}")
        # Fallback - return a bright red error tile
        img = Image.new('RGB', (32, 32), (255, 0, 0))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        draw.text((2, 12), "ERR", fill=(255, 255, 255))
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return HttpResponse(buffer.getvalue(), content_type='image/png')

@csrf_exempt
@require_http_methods(["POST"])
def paint_tile(request):
    """Handle tile painting requests"""
    try:
        data = json.loads(request.body)
        tile_x = data.get('tile_x')
        tile_y = data.get('tile_y')
        pixels = data.get('pixels', [])
        
        # Create tile image from pixel data
        if pixels:
            img = Image.new('RGBA', (32, 32))
            pixel_data = []
            for pixel in pixels:
                pixel_data.append(tuple(pixel))
            img.putdata(pixel_data)
            
            # Save to E:\files\GeoPLace-tmp\images
            tile_filename = f"tile_{tile_x}_{tile_y}.png"
            tile_path = os.path.join(r'E:\files\GeoPLace-tmp\images', tile_filename)
            
            # Ensure directory exists
            os.makedirs(os.path.dirname(tile_path), exist_ok=True)
            img.save(tile_path)
        
        return JsonResponse({'success': True})
        
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["POST"])
def generate_3d(request):
    """Handle 3D generation requests"""
    try:
        data = json.loads(request.body)
        # For now, just return a mock job ID
        return JsonResponse({
            'success': True,
            'job_id': 'mock_job_123',
            'message': '3D generation started'
        })
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@csrf_exempt
@require_http_methods(["GET"])
def get_objects_json(request):
    """Return 3D objects list"""
    # Return empty list for now - can be expanded later
    return JsonResponse([])

@csrf_exempt
@require_http_methods(["GET"])
def get_canvas_image(request):
    """Generate and serve a composite canvas image from tiles"""
    try:
        # Create a smaller test canvas (1000x1000) for faster loading
        canvas_size = 1000
        tile_size = 32
        tiles_per_side = canvas_size // tile_size
        
        # Create the canvas
        canvas = Image.new('RGBA', (canvas_size, canvas_size), (240, 240, 240, 255))
        
        # Load and composite tiles
        for y in range(tiles_per_side):
            for x in range(tiles_per_side):
                # Get tile from our tile endpoint
                tile_response = get_tile(None, x, y)
                if tile_response.status_code == 200:
                    try:
                        tile_data = io.BytesIO(tile_response.content)
                        tile_img = Image.open(tile_data)
                        
                        # Paste tile onto canvas
                        canvas.paste(tile_img, (x * tile_size, y * tile_size), tile_img)
                    except Exception:
                        continue
        
        # Save composite image
        buffer = io.BytesIO()
        canvas.save(buffer, format='PNG', optimize=True)
        return HttpResponse(buffer.getvalue(), content_type='image/png')
        
    except Exception as e:
        # Fallback - return a simple test pattern
        img = Image.new('RGBA', (1000, 1000), (200, 200, 200, 255))
        from PIL import ImageDraw
        draw = ImageDraw.Draw(img)
        
        # Draw a grid pattern
        for i in range(0, 1000, 32):
            draw.line([(i, 0), (i, 1000)], fill=(150, 150, 150, 255), width=1)
            draw.line([(0, i), (1000, i)], fill=(150, 150, 150, 255), width=1)
        
        buffer = io.BytesIO()
        img.save(buffer, format='PNG')
        return HttpResponse(buffer.getvalue(), content_type='image/png')
