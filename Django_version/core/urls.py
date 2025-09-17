"""
URL configuration for core app - simplified for original frontend compatibility
"""
from django.urls import path
from . import views

urlpatterns = [
    # Basic API endpoints that match original backend expectations
    path('tile/<int:tile_x>/<int:tile_y>/', views.get_tile, name='get_tile'),
    path('paint_tile/', views.paint_tile, name='paint_tile'),
    path('generate_3d/', views.generate_3d, name='generate_3d'),
    path('objects/', views.get_objects_json, name='get_objects'),
    path('canvas.png', views.get_canvas_image, name='get_canvas_image'),
]
