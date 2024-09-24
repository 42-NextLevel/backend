from django.urls import path
from .views import GameRoomViewSet
from game.views import game_room_test

urlpatterns = [
    path('list', GameRoomViewSet.as_view({'get': 'list'}), name='room-list'),
    path('new', GameRoomViewSet.as_view({'post': 'create'}), name='room-create'),
    path('join', GameRoomViewSet.as_view({'post': 'join'}), name='room-join'),
    path('info', GameRoomViewSet.as_view({'get': 'retrieve'}), name='room-info'),
    path('start', GameRoomViewSet.as_view({'post': 'start_game'}), name='room-start'),
	path('game-room-test/', game_room_test, name='game_room_test'),
]