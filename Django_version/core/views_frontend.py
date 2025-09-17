"""
Frontend views for Django GeoPlace
"""
from django.shortcuts import render
from django.http import HttpResponse
from django.conf import settings
from django.urls import path


def index(request):
    """Main index page - redirect to paint"""
    return paint_view(request)


def paint_view(request):
    """Paint canvas view"""
    context = {
        'title': 'GeoPlace - ペイント',
        'canvas_config': settings.GEOPLACE_CONFIG,
        'websocket_url': 'ws://localhost:8000/ws/canvas/',
        'api_base_url': '/api/'
    }
    return render(request, 'paint.html', context)


def world_view(request):
    """3D world view"""
    context = {
        'title': 'GeoPlace - 3D世界',
        'canvas_config': settings.GEOPLACE_CONFIG,
        'websocket_url': 'ws://localhost:8000/ws/world/',
        'api_base_url': '/api/'
    }
    return render(request, 'world.html', context)


def admin_view(request):
    """Admin dashboard view"""
    context = {
        'title': 'GeoPlace - 管理画面',
        'canvas_config': settings.GEOPLACE_CONFIG,
        'websocket_url': 'ws://localhost:8000/ws/generation/',
        'api_base_url': '/api/'
    }
    return render(request, 'admin_dashboard.html', context)


# URL patterns for frontend views
urlpatterns = [
    path('', index, name='index'),
    path('paint/', paint_view, name='paint'),
    path('world/', world_view, name='world'),
    path('admin-dashboard/', admin_view, name='admin_dashboard'),
]
