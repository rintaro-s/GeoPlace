"""
Django models for GeoPlace application
"""
from django.db import models
from django.contrib.auth.models import User
from django.utils import timezone
import json
from pathlib import Path


class Tile(models.Model):
    """Represents a single tile in the canvas"""
    x = models.IntegerField()
    y = models.IntegerField()
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    modified_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        unique_together = ('x', 'y')
        indexes = [
            models.Index(fields=['x', 'y']),
            models.Index(fields=['updated_at']),
        ]
    
    def __str__(self):
        return f"Tile({self.x}, {self.y})"
    
    @property
    def file_path(self):
        """Get the file path for this tile"""
        from django.conf import settings
        tiles_dir = settings.GEOPLACE_CONFIG['TILES_DIR']
        return tiles_dir / f"tile_{self.x}_{self.y}.png"
    
    def exists_on_disk(self):
        """Check if tile file exists on disk"""
        return self.file_path.exists()
    
    def get_world_position(self):
        """Get 3D world position for this tile"""
        tile_size_meters = 1.0  # 1 tile = 1 meter
        return {
            'x': self.x * tile_size_meters,
            'y': 0,
            'z': self.y * tile_size_meters
        }


class GenerationJob(models.Model):
    """Represents a 3D generation job"""
    STATUS_CHOICES = [
        ('queued', 'Queued'),
        ('vlm_analyzing', 'VLM Analysis'),
        ('sd_generating', 'SD Generation'),
        ('triposr_generating', 'TripoSR Generation'),
        ('light_ready', 'Light Ready'),
        ('refining', 'Refining'),
        ('refined_ready', 'Refined Ready'),
        ('completed', 'Completed'),
        ('failed', 'Failed'),
    ]
    
    job_id = models.CharField(max_length=100, unique=True)
    status = models.CharField(max_length=20, choices=STATUS_CHOICES, default='queued')
    tiles = models.ManyToManyField(Tile, related_name='generation_jobs')
    progress = models.IntegerField(default=0)
    total_tiles = models.IntegerField(default=0)
    current_tile = models.CharField(max_length=50, blank=True)
    error_message = models.TextField(blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    completed_at = models.DateTimeField(null=True, blank=True)
    
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"Job {self.job_id} - {self.status}"
    
    def mark_completed(self):
        """Mark job as completed"""
        self.status = 'completed'
        self.completed_at = timezone.now()
        self.save()
    
    def mark_failed(self, error_message):
        """Mark job as failed"""
        self.status = 'failed'
        self.error_message = error_message
        self.completed_at = timezone.now()
        self.save()
    
    def update_progress(self, current_tile=None, progress=None):
        """Update job progress"""
        if current_tile:
            self.current_tile = current_tile
        if progress is not None:
            self.progress = progress
        self.updated_at = timezone.now()
        self.save()


class ThreeDObject(models.Model):
    """Represents a 3D object in the world"""
    object_id = models.CharField(max_length=100, unique=True)
    tile = models.ForeignKey(Tile, on_delete=models.CASCADE, related_name='objects')
    
    # 3D position and transformation
    x = models.FloatField()
    y = models.FloatField(default=0)
    z = models.FloatField()
    rotation_x = models.FloatField(default=0)
    rotation_y = models.FloatField(default=0)
    rotation_z = models.FloatField(default=0)
    scale = models.FloatField(default=1.0)
    
    # File references
    glb_url = models.CharField(max_length=500)
    glb_file_path = models.CharField(max_length=500, blank=True)
    
    # Metadata
    quality = models.CharField(max_length=20, default='light')  # light, refined, fallback
    metadata_json = models.TextField(default='{}')
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    created_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True)
    
    class Meta:
        ordering = ['-created_at']
    
    def __str__(self):
        return f"3D Object {self.object_id} at ({self.x}, {self.y}, {self.z})"
    
    @property
    def metadata(self):
        """Get metadata as dict"""
        try:
            return json.loads(self.metadata_json)
        except:
            return {}
    
    @metadata.setter
    def metadata(self, value):
        """Set metadata from dict"""
        self.metadata_json = json.dumps(value, ensure_ascii=False)
    
    def get_position_dict(self):
        """Get position as dict"""
        return {
            'x': self.x,
            'y': self.y,
            'z': self.z
        }
    
    def get_rotation_dict(self):
        """Get rotation as dict"""
        return {
            'x': self.rotation_x,
            'y': self.rotation_y,
            'z': self.rotation_z
        }
    
    def to_aframe_dict(self):
        """Convert to A-Frame compatible dict"""
        return {
            'id': self.object_id,
            'position': f"{self.x} {self.y} {self.z}",
            'rotation': f"{self.rotation_x} {self.rotation_y} {self.rotation_z}",
            'scale': f"{self.scale} {self.scale} {self.scale}",
            'src': self.glb_url,
            'metadata': self.metadata,
            'quality': self.quality,
            'created_at': self.created_at.isoformat(),
        }


class VLMAnalysis(models.Model):
    """Stores VLM analysis results for tiles"""
    tile = models.OneToOneField(Tile, on_delete=models.CASCADE, related_name='vlm_analysis')
    
    # VLM extracted attributes
    category = models.CharField(max_length=50, default='object')
    colors = models.JSONField(default=list)  # List of color names
    size = models.CharField(max_length=20, default='medium')  # small, medium, large
    orientation = models.CharField(max_length=20, default='front')
    details = models.JSONField(default=list)  # List of detail strings
    
    # Generated prompt
    sd_prompt = models.TextField(blank=True)
    
    # Analysis metadata
    confidence_score = models.FloatField(default=0.0)
    processing_time = models.FloatField(default=0.0)
    model_used = models.CharField(max_length=100, blank=True)
    
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)
    
    def __str__(self):
        return f"VLM Analysis for {self.tile} - {self.category}"
    
    def get_size_multiplier(self):
        """Get scale multiplier based on size"""
        size_map = {
            'small': 0.5,
            'medium': 1.0,
            'large': 1.5
        }
        return size_map.get(self.size, 1.0)


class SystemStatus(models.Model):
    """Stores system status and model loading states"""
    component = models.CharField(max_length=50, unique=True)  # sd, vlm, triposr
    status = models.CharField(max_length=20)  # loading, ready, error
    error_message = models.TextField(blank=True)
    last_check = models.DateTimeField(auto_now=True)
    metadata_json = models.TextField(default='{}')
    
    def __str__(self):
        return f"{self.component}: {self.status}"
    
    @property
    def metadata(self):
        try:
            return json.loads(self.metadata_json)
        except:
            return {}
    
    @metadata.setter
    def metadata(self, value):
        self.metadata_json = json.dumps(value, ensure_ascii=False)


class UserSession(models.Model):
    """Tracks user sessions for collaborative editing"""
    session_key = models.CharField(max_length=100, unique=True)
    user = models.ForeignKey(User, on_delete=models.CASCADE, null=True, blank=True)
    last_activity = models.DateTimeField(auto_now=True)
    current_view = models.CharField(max_length=20, default='paint')  # paint, world, admin
    viewport_x = models.FloatField(default=0)
    viewport_y = models.FloatField(default=0)
    zoom_level = models.FloatField(default=1.0)
    
    def __str__(self):
        return f"Session {self.session_key} - {self.user or 'Anonymous'}"
    
    def is_active(self):
        """Check if session is active (within last 5 minutes)"""
        from django.utils import timezone
        from datetime import timedelta
        return timezone.now() - self.last_activity < timedelta(minutes=5)
