from django.urls import re_path
from . import consumers

websocket_urlpatterns = [
    re_path(r'ws/room/(?P<room_id>[\w-]+)/?$', consumers.GameConsumer.as_asgi()),
    re_path(r'ws/game/(?P<game_id>[\w-]+)/?$', consumers.GamePingPongConsumer.as_asgi()),
]