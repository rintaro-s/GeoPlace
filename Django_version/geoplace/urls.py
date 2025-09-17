"""
URL configuration for GeoPlace project.
"""
from django.contrib import admin
from django.urls import path, include
from django.conf import settings
from django.conf.urls.static import static
from django.views.static import serve
from core import views
import os

urlpatterns = [
    path('admin/', admin.site.urls),
    
    # API endpoints that match original backend expectations
    path('api/tile/<int:tile_x>/<int:tile_y>/', views.get_tile, name='get_tile'),
    path('api/tile/<int:tile_x>/<int:tile_y>', views.get_tile, name='get_tile_no_slash'),
    path('api/paint_tile/', views.paint_tile, name='paint_tile'),
    path('api/paint_tile', views.paint_tile, name='paint_tile_no_slash'),
    path('api/generate_3d/', views.generate_3d, name='generate_3d'),
    path('api/generate_3d', views.generate_3d, name='generate_3d_no_slash'),
    path('api/objects/', views.get_objects_json, name='get_objects'),
    path('api/objects', views.get_objects_json, name='get_objects_no_slash'),
    path('api/canvas.png', views.get_canvas_image, name='get_canvas_image'),
    
    # Serve original HTML files directly
    path('', views.serve_static_file, {'file_path': 'paint.html'}, name='index'),
    path('paint.html', views.serve_static_file, {'file_path': 'paint.html'}, name='paint'),
    path('world.html', views.serve_static_file, {'file_path': 'world.html'}, name='world'),
    path('admin.html', views.serve_static_file, {'file_path': 'admin.html'}, name='admin'),
]

# Serve media files in development
if settings.DEBUG:
    urlpatterns += static(settings.MEDIA_URL, document_root=settings.MEDIA_ROOT)
    urlpatterns += static(settings.STATIC_URL, document_root=settings.STATIC_ROOT)
