"""
Core services for tile management and image processing
"""
from pathlib import Path
from PIL import Image, ImageDraw
import io
import base64
import json
import time
import logging
from django.conf import settings
from django.core.files.base import ContentFile
from django.http import HttpResponse
from .models import Tile, VLMAnalysis, ThreeDObject

logger = logging.getLogger('geoplace')


class TileService:
    """Service for managing tile operations with E:\files\GeoPLace-tmp\images"""
    
    def __init__(self):
        self.config = settings.GEOPLACE_CONFIG
        self.tile_size = self.config['TILE_SIZE']
        self.tiles_dir = self.config['TILES_DIR']
        
        # Ensure tiles directory exists
        self.tiles_dir.mkdir(parents=True, exist_ok=True)
    
    def get_tile_path(self, tile_x, tile_y):
        """Get file path for a tile"""
        return self.tiles_dir / f"tile_{tile_x}_{tile_y}.png"
    
    def load_tile_image(self, tile_x, tile_y):
        """Load tile image from E:\files\GeoPLace-tmp\images"""
        tile_path = self.get_tile_path(tile_x, tile_y)
        
        try:
            if tile_path.exists():
                logger.info(f"Loading tile from {tile_path}")
                image = Image.open(tile_path).convert('RGBA')
                return image
            else:
                logger.info(f"Creating transparent tile for {tile_x},{tile_y}")
                # Create transparent tile
                return Image.new('RGBA', (self.tile_size, self.tile_size), (0, 0, 0, 0))
        except Exception as e:
            logger.error(f"Error loading tile {tile_x},{tile_y}: {e}")
            # Return transparent tile on error
            return Image.new('RGBA', (self.tile_size, self.tile_size), (0, 0, 0, 0))
    
    def save_tile_image(self, tile_x, tile_y, image_data):
        """Save tile image to E:\files\GeoPLace-tmp\images"""
        tile_path = self.get_tile_path(tile_x, tile_y)
        
        try:
            if isinstance(image_data, bytes):
                # Convert bytes to PIL Image
                image = Image.open(io.BytesIO(image_data)).convert('RGBA')
            elif isinstance(image_data, Image.Image):
                image = image_data.convert('RGBA')
            elif isinstance(image_data, list):
                # Convert pixel array to PIL Image
                image = Image.new('RGBA', (self.tile_size, self.tile_size))
                image.putdata([tuple(p) for p in image_data])
            else:
                raise ValueError(f"Unsupported image data type: {type(image_data)}")
            
            # Ensure correct size
            if image.size != (self.tile_size, self.tile_size):
                image = image.resize((self.tile_size, self.tile_size), Image.LANCZOS)
            
            # Save to disk
            image.save(tile_path, 'PNG')
            logger.info(f"Saved tile to {tile_path}")
            
            # Update or create tile record
            tile, created = Tile.objects.get_or_create(x=tile_x, y=tile_y)
            if created:
                logger.info(f"Created new tile record for {tile_x},{tile_y}")
            
            return tile_path
            
        except Exception as e:
            logger.error(f"Error saving tile {tile_x},{tile_y}: {e}")
            raise
    
    def get_tile_as_response(self, tile_x, tile_y):
        """Get tile as HTTP response"""
        try:
            image = self.load_tile_image(tile_x, tile_y)
            
            # Convert to bytes
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)
            
            response = HttpResponse(buffer.getvalue(), content_type='image/png')
            response['Cache-Control'] = 'max-age=3600'  # Cache for 1 hour
            return response
            
        except Exception as e:
            logger.error(f"Error serving tile {tile_x},{tile_y}: {e}")
            # Return transparent tile
            transparent = Image.new('RGBA', (self.tile_size, self.tile_size), (0, 0, 0, 0))
            buffer = io.BytesIO()
            transparent.save(buffer, format='PNG')
            buffer.seek(0)
            return HttpResponse(buffer.getvalue(), content_type='image/png')
    
    def get_tile_as_base64(self, tile_x, tile_y):
        """Get tile as base64 string"""
        try:
            image = self.load_tile_image(tile_x, tile_y)
            buffer = io.BytesIO()
            image.save(buffer, format='PNG')
            buffer.seek(0)
            return base64.b64encode(buffer.getvalue()).decode('utf-8')
        except Exception as e:
            logger.error(f"Error converting tile {tile_x},{tile_y} to base64: {e}")
            return None
    
    def get_modified_tiles(self, since_minutes=60):
        """Get tiles modified within the last N minutes"""
        from django.utils import timezone
        from datetime import timedelta
        
        since_time = timezone.now() - timedelta(minutes=since_minutes)
        return Tile.objects.filter(updated_at__gte=since_time)
    
    def create_canvas_region(self, start_x, start_y, width, height):
        """Create a larger canvas region from multiple tiles"""
        try:
            # Calculate tile range
            tile_start_x = start_x // self.tile_size
            tile_start_y = start_y // self.tile_size
            tile_end_x = (start_x + width) // self.tile_size + 1
            tile_end_y = (start_y + height) // self.tile_size + 1
            
            # Create canvas
            canvas = Image.new('RGBA', (width, height), (255, 255, 255, 0))
            
            # Composite tiles
            for tile_y in range(tile_start_y, tile_end_y):
                for tile_x in range(tile_start_x, tile_end_x):
                    tile_image = self.load_tile_image(tile_x, tile_y)
                    
                    # Calculate position on canvas
                    canvas_x = tile_x * self.tile_size - start_x
                    canvas_y = tile_y * self.tile_size - start_y
                    
                    # Paste tile onto canvas
                    canvas.paste(tile_image, (canvas_x, canvas_y), tile_image)
            
            return canvas
            
        except Exception as e:
            logger.error(f"Error creating canvas region: {e}")
            return Image.new('RGBA', (width, height), (255, 255, 255, 0))


class ImageProcessingService:
    """Service for image processing operations"""
    
    @staticmethod
    def resize_image(image, target_size, maintain_aspect=True):
        """Resize image to target size"""
        if maintain_aspect:
            image.thumbnail(target_size, Image.LANCZOS)
            # Create new image with target size and paste resized image centered
            new_image = Image.new('RGBA', target_size, (0, 0, 0, 0))
            paste_x = (target_size[0] - image.size[0]) // 2
            paste_y = (target_size[1] - image.size[1]) // 2
            new_image.paste(image, (paste_x, paste_y), image)
            return new_image
        else:
            return image.resize(target_size, Image.LANCZOS)
    
    @staticmethod
    def create_thumbnail(image, size=(128, 128)):
        """Create thumbnail of image"""
        thumbnail = image.copy()
        thumbnail.thumbnail(size, Image.LANCZOS)
        return thumbnail
    
    @staticmethod
    def apply_drawing_operation(image, operation_data):
        """Apply drawing operation to image"""
        try:
            draw = ImageDraw.Draw(image)
            
            op_type = operation_data.get('type')
            color = tuple(operation_data.get('color', [255, 0, 0, 255]))
            
            if op_type == 'brush':
                points = operation_data.get('points', [])
                width = operation_data.get('width', 2)
                
                if len(points) > 1:
                    for i in range(len(points) - 1):
                        x1, y1 = points[i]
                        x2, y2 = points[i + 1]
                        draw.line([(x1, y1), (x2, y2)], fill=color, width=width)
                elif len(points) == 1:
                    x, y = points[0]
                    r = width // 2
                    draw.ellipse([x-r, y-r, x+r, y+r], fill=color)
            
            elif op_type == 'circle':
                center = operation_data.get('center', [16, 16])
                radius = operation_data.get('radius', 5)
                x, y = center
                draw.ellipse([x-radius, y-radius, x+radius, y+radius], fill=color)
            
            elif op_type == 'rectangle':
                start = operation_data.get('start', [0, 0])
                end = operation_data.get('end', [32, 32])
                draw.rectangle([start[0], start[1], end[0], end[1]], fill=color)
            
            return image
            
        except Exception as e:
            logger.error(f"Error applying drawing operation: {e}")
            return image


class CoordinateService:
    """Service for coordinate transformations"""
    
    def __init__(self):
        self.config = settings.GEOPLACE_CONFIG
        self.tile_size = self.config['TILE_SIZE']
    
    def canvas_to_tile(self, canvas_x, canvas_y):
        """Convert canvas coordinates to tile coordinates"""
        tile_x = int(canvas_x // self.tile_size)
        tile_y = int(canvas_y // self.tile_size)
        return tile_x, tile_y
    
    def tile_to_canvas(self, tile_x, tile_y):
        """Convert tile coordinates to canvas coordinates"""
        canvas_x = tile_x * self.tile_size
        canvas_y = tile_y * self.tile_size
        return canvas_x, canvas_y
    
    def tile_to_world_3d(self, tile_x, tile_y):
        """Convert tile coordinates to 3D world coordinates"""
        # 1 tile = 1 meter in 3D world
        world_x = float(tile_x)
        world_y = 0.0  # Ground level
        world_z = float(tile_y)
        return world_x, world_y, world_z
    
    def world_3d_to_tile(self, world_x, world_z):
        """Convert 3D world coordinates to tile coordinates"""
        tile_x = int(round(world_x))
        tile_y = int(round(world_z))
        return tile_x, tile_y
    
    def get_viewport_tiles(self, viewport_x, viewport_y, viewport_width, viewport_height, zoom=1.0):
        """Get tiles visible in viewport"""
        # Calculate actual viewport size considering zoom
        actual_width = viewport_width / zoom
        actual_height = viewport_height / zoom
        
        # Calculate tile range
        start_tile_x = int(viewport_x // self.tile_size)
        start_tile_y = int(viewport_y // self.tile_size)
        end_tile_x = int((viewport_x + actual_width) // self.tile_size) + 1
        end_tile_y = int((viewport_y + actual_height) // self.tile_size) + 1
        
        tiles = []
        for tile_y in range(start_tile_y, end_tile_y):
            for tile_x in range(start_tile_x, end_tile_x):
                tiles.append((tile_x, tile_y))
        
        return tiles


class ObjectService:
    """Service for managing 3D objects"""
    
    def __init__(self):
        self.config = settings.GEOPLACE_CONFIG
        self.coordinate_service = CoordinateService()
    
    def register_3d_object(self, tile_x, tile_y, glb_path, metadata=None):
        """Register a 3D object for a tile"""
        try:
            # Get or create tile
            tile, _ = Tile.objects.get_or_create(x=tile_x, y=tile_y)
            
            # Generate object ID
            object_id = f"tile_{tile_x}_{tile_y}_{int(time.time())}"
            
            # Calculate 3D position
            world_x, world_y, world_z = self.coordinate_service.tile_to_world_3d(tile_x, tile_y)
            
            # Get scale from VLM analysis if available
            scale = 1.0
            try:
                vlm_analysis = VLMAnalysis.objects.get(tile=tile)
                scale = vlm_analysis.get_size_multiplier()
            except VLMAnalysis.DoesNotExist:
                pass
            
            # Create GLB URL
            glb_url = f"/media/glb/{glb_path.name}"
            
            # Create 3D object
            obj = ThreeDObject.objects.create(
                object_id=object_id,
                tile=tile,
                x=world_x,
                y=world_y,
                z=world_z,
                scale=scale,
                glb_url=glb_url,
                glb_file_path=str(glb_path),
                metadata=metadata or {}
            )
            
            logger.info(f"Registered 3D object {object_id} at ({world_x}, {world_y}, {world_z})")
            return obj
            
        except Exception as e:
            logger.error(f"Error registering 3D object for tile {tile_x},{tile_y}: {e}")
            raise
    
    def get_objects_in_region(self, min_x, min_z, max_x, max_z):
        """Get 3D objects in a region"""
        return ThreeDObject.objects.filter(
            x__gte=min_x, x__lte=max_x,
            z__gte=min_z, z__lte=max_z
        )
    
    def get_objects_for_aframe(self, limit=None):
        """Get objects formatted for A-Frame"""
        queryset = ThreeDObject.objects.all().order_by('-created_at')
        if limit:
            queryset = queryset[:limit]
        
        return [obj.to_aframe_dict() for obj in queryset]
    
    def update_object_position(self, object_id, x=None, y=None, z=None):
        """Update object position"""
        try:
            obj = ThreeDObject.objects.get(object_id=object_id)
            if x is not None:
                obj.x = x
            if y is not None:
                obj.y = y
            if z is not None:
                obj.z = z
            obj.save()
            return obj
        except ThreeDObject.DoesNotExist:
            logger.error(f"3D object {object_id} not found")
            return None
