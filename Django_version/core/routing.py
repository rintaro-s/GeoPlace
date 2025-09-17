"""
WebSocket routing for real-time updates
"""
from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/canvas/$', consumers.CanvasConsumer.as_asgi()),
    re_path(r'ws/generation/$', consumers.GenerationConsumer.as_asgi()),
    re_path(r'ws/world/$', consumers.WorldConsumer.as_asgi()),
]
