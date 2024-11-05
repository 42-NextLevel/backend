from django.urls import path
from .views import GameRoomViewSet
# from game.views import game_test
from game.views import get_client_info


urlpatterns = [
    path('list', GameRoomViewSet.as_view({'get': 'list'}), name='room-list'),
    path('new', GameRoomViewSet.as_view({'post': 'create'}), name='room-create'),
    path('join', GameRoomViewSet.as_view({'post': 'join'}), name='room-join'),
    path('start', GameRoomViewSet.as_view({'post': 'start_game'}), name='room-start'),
	path('players', GameRoomViewSet.as_view({'post': 'players_info'}), name='room-players'),
	path('user-info/', get_client_info, name='get_client_info'),
	path('history', GameRoomViewSet.as_view({'get': 'game_history'}), name='game-history')
	# path('test/', game_test, name='game_test'),
]