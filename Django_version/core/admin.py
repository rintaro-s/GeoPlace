"""
Django admin configuration for GeoPlace
"""
from django.contrib import admin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    Tile, GenerationJob, ThreeDObject, VLMAnalysis, 
    SystemStatus, UserSession
)


@admin.register(Tile)
class TileAdmin(admin.ModelAdmin):
    list_display = ['x', 'y', 'exists_on_disk', 'updated_at', 'modified_by']
    list_filter = ['updated_at', 'modified_by']
    search_fields = ['x', 'y']
    ordering = ['-updated_at']
    readonly_fields = ['created_at', 'updated_at', 'file_path']
    
    def exists_on_disk(self, obj):
        if obj.exists_on_disk():
            return format_html('<span style="color: green;">✓ Exists</span>')
        else:
            return format_html('<span style="color: red;">✗ Missing</span>')
    exists_on_disk.short_description = 'File Status'


@admin.register(GenerationJob)
class GenerationJobAdmin(admin.ModelAdmin):
    list_display = ['job_id', 'status', 'progress_display', 'total_tiles', 'created_at', 'created_by']
    list_filter = ['status', 'created_at']
    search_fields = ['job_id', 'current_tile']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'completed_at']
    filter_horizontal = ['tiles']
    
    def progress_display(self, obj):
        if obj.total_tiles > 0:
            percentage = (obj.progress / obj.total_tiles) * 100
            return format_html(
                '<div style="width: 100px; background: #f0f0f0; border-radius: 3px;">'
                '<div style="width: {}%; background: #4CAF50; height: 20px; border-radius: 3px; text-align: center; color: white; font-size: 12px; line-height: 20px;">'
                '{}%</div></div>',
                percentage, int(percentage)
            )
        return "0%"
    progress_display.short_description = 'Progress'


@admin.register(ThreeDObject)
class ThreeDObjectAdmin(admin.ModelAdmin):
    list_display = ['object_id', 'tile', 'position_display', 'scale', 'quality', 'created_at']
    list_filter = ['quality', 'created_at']
    search_fields = ['object_id', 'tile__x', 'tile__y']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at', 'metadata_display']
    
    def position_display(self, obj):
        return f"({obj.x:.1f}, {obj.y:.1f}, {obj.z:.1f})"
    position_display.short_description = 'Position'
    
    def metadata_display(self, obj):
        import json
        try:
            metadata = json.loads(obj.metadata_json)
            formatted = json.dumps(metadata, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted)
        except:
            return obj.metadata_json
    metadata_display.short_description = 'Metadata'


@admin.register(VLMAnalysis)
class VLMAnalysisAdmin(admin.ModelAdmin):
    list_display = ['tile', 'category', 'size', 'colors_display', 'confidence_score', 'created_at']
    list_filter = ['category', 'size', 'created_at']
    search_fields = ['tile__x', 'tile__y', 'category']
    ordering = ['-created_at']
    readonly_fields = ['created_at', 'updated_at']
    
    def colors_display(self, obj):
        colors = obj.colors if isinstance(obj.colors, list) else []
        return ', '.join(colors[:3])  # Show first 3 colors
    colors_display.short_description = 'Colors'


@admin.register(SystemStatus)
class SystemStatusAdmin(admin.ModelAdmin):
    list_display = ['component', 'status_display', 'last_check', 'error_message_short']
    list_filter = ['status', 'last_check']
    search_fields = ['component', 'error_message']
    ordering = ['component']
    readonly_fields = ['last_check', 'metadata_display']
    
    def status_display(self, obj):
        color_map = {
            'ready': 'green',
            'loading': 'orange',
            'error': 'red'
        }
        color = color_map.get(obj.status, 'gray')
        return format_html('<span style="color: {};">{}</span>', color, obj.status.upper())
    status_display.short_description = 'Status'
    
    def error_message_short(self, obj):
        if obj.error_message:
            return obj.error_message[:50] + ('...' if len(obj.error_message) > 50 else '')
        return '-'
    error_message_short.short_description = 'Error'
    
    def metadata_display(self, obj):
        import json
        try:
            metadata = json.loads(obj.metadata_json)
            formatted = json.dumps(metadata, indent=2, ensure_ascii=False)
            return format_html('<pre>{}</pre>', formatted)
        except:
            return obj.metadata_json
    metadata_display.short_description = 'Metadata'


@admin.register(UserSession)
class UserSessionAdmin(admin.ModelAdmin):
    list_display = ['session_key', 'user', 'current_view', 'is_active_display', 'last_activity']
    list_filter = ['current_view', 'last_activity']
    search_fields = ['session_key', 'user__username']
    ordering = ['-last_activity']
    readonly_fields = ['last_activity']
    
    def is_active_display(self, obj):
        if obj.is_active():
            return format_html('<span style="color: green;">✓ Active</span>')
        else:
            return format_html('<span style="color: gray;">Inactive</span>')
    is_active_display.short_description = 'Status'


# Customize admin site
admin.site.site_header = 'GeoPlace Administration'
admin.site.site_title = 'GeoPlace Admin'
admin.site.index_title = 'Welcome to GeoPlace Administration'
