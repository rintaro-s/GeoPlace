"""
Django REST Framework serializers for GeoPlace
"""
from rest_framework import serializers
from .models import Tile, GenerationJob, ThreeDObject, VLMAnalysis, SystemStatus, UserSession


class TileSerializer(serializers.ModelSerializer):
    """Serializer for Tile model"""
    exists_on_disk = serializers.ReadOnlyField()
    world_position = serializers.ReadOnlyField(source='get_world_position')
    
    class Meta:
        model = Tile
        fields = ['x', 'y', 'created_at', 'updated_at', 'modified_by', 
                 'exists_on_disk', 'world_position']
        read_only_fields = ['created_at', 'updated_at']


class GenerationJobSerializer(serializers.ModelSerializer):
    """Serializer for GenerationJob model"""
    tiles_count = serializers.SerializerMethodField()
    progress_percentage = serializers.SerializerMethodField()
    
    class Meta:
        model = GenerationJob
        fields = ['job_id', 'status', 'progress', 'total_tiles', 'current_tile',
                 'error_message', 'created_at', 'updated_at', 'completed_at',
                 'created_by', 'tiles_count', 'progress_percentage']
        read_only_fields = ['created_at', 'updated_at', 'completed_at']
    
    def get_tiles_count(self, obj):
        return obj.tiles.count()
    
    def get_progress_percentage(self, obj):
        if obj.total_tiles > 0:
            return round((obj.progress / obj.total_tiles) * 100, 1)
        return 0.0


class ThreeDObjectSerializer(serializers.ModelSerializer):
    """Serializer for ThreeDObject model"""
    tile_coords = serializers.SerializerMethodField()
    position = serializers.SerializerMethodField()
    rotation = serializers.SerializerMethodField()
    aframe_data = serializers.SerializerMethodField()
    
    class Meta:
        model = ThreeDObject
        fields = ['object_id', 'tile', 'x', 'y', 'z', 'rotation_x', 'rotation_y', 
                 'rotation_z', 'scale', 'glb_url', 'glb_file_path', 'quality',
                 'metadata_json', 'created_at', 'updated_at', 'created_by',
                 'tile_coords', 'position', 'rotation', 'aframe_data']
        read_only_fields = ['created_at', 'updated_at']
    
    def get_tile_coords(self, obj):
        return {'x': obj.tile.x, 'y': obj.tile.y}
    
    def get_position(self, obj):
        return obj.get_position_dict()
    
    def get_rotation(self, obj):
        return obj.get_rotation_dict()
    
    def get_aframe_data(self, obj):
        return obj.to_aframe_dict()


class VLMAnalysisSerializer(serializers.ModelSerializer):
    """Serializer for VLMAnalysis model"""
    tile_coords = serializers.SerializerMethodField()
    size_multiplier = serializers.ReadOnlyField(source='get_size_multiplier')
    
    class Meta:
        model = VLMAnalysis
        fields = ['tile', 'category', 'colors', 'size', 'orientation', 'details',
                 'sd_prompt', 'confidence_score', 'processing_time', 'model_used',
                 'created_at', 'updated_at', 'tile_coords', 'size_multiplier']
        read_only_fields = ['created_at', 'updated_at']
    
    def get_tile_coords(self, obj):
        return {'x': obj.tile.x, 'y': obj.tile.y}


class SystemStatusSerializer(serializers.ModelSerializer):
    """Serializer for SystemStatus model"""
    
    class Meta:
        model = SystemStatus
        fields = ['component', 'status', 'error_message', 'last_check', 'metadata_json']
        read_only_fields = ['last_check']


class UserSessionSerializer(serializers.ModelSerializer):
    """Serializer for UserSession model"""
    is_active = serializers.ReadOnlyField()
    
    class Meta:
        model = UserSession
        fields = ['session_key', 'user', 'last_activity', 'current_view',
                 'viewport_x', 'viewport_y', 'zoom_level', 'is_active']
        read_only_fields = ['last_activity']
