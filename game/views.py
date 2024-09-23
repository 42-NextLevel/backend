from rest_framework import viewsets, status
from rest_framework.decorators import action
from rest_framework.response import Response
from django.shortcuts import get_object_or_404
from channels.layers import get_channel_layer
from asgiref.sync import async_to_sync
import uuid
import redis
import time


game_rooms = redis.StrictRedis(host='localhost', port=6379, db=0)

class GameRoomViewSet(viewsets.ViewSet):
	def list(self, request):
		"""모든 게임 방 목록을 반환합니다."""
		game_room_datas = []
		game_rooms_keys = game_rooms.keys()
		for room_id in game_rooms_keys:
			room = game_rooms.get(room_id)
			game_room_datas.append(
				{
					'id': room_id,
					'name': room['name'],
					'roomType': room['roomType'],
					'people': len(room['players']),
				}
			)
		return Response(game_room_datas, status=status.HTTP_200_OK)

	def create(self, request):
		"""새로운 게임 방을 생성합니다."""
		room_id = str(uuid.uuid4())
		room_data = {
			'id': room_id,
			'name': request.data.get('name'),
			'roomType': request.data.get('roomType'),
			'players': [{'username': request.data.get('nickname')}],
			'created_at': time.time(),
			'expire_at': time.time() + 3600  # 1 hour from creation
		}
		game_rooms.set(room_id, room_data)
		return Response(room_data, status=status.HTTP_201_CREATED)

	@action(detail=True, methods=['post'])
	def join(self, request):
		"""게임 방에 참가합니다."""
		room_id = request.data.get('room_id')
		nickname = request.data.get('nickname')
		room = game_rooms.get(room_id)

		if room.get('roomType') == 0 and len(room['players']) >= 2:
			return Response({'error': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)

		if room.get('roomType') == 1 and len(room['players']) >= 4:
			return Response({'error': 'Room is full'}, status=status.HTTP_400_BAD_REQUEST)

		if any(player['username'] == nickname for player in room['players']):
			return Response({'error': 'Nickname already taken'}, status=status.HTTP_400_BAD_REQUEST)

		room['players'].append({'username': nickname, 'ready': False})
		game_rooms.set(room_id, room)

		return Response()

	@action(detail=True, methods=['post'])
	def leave(self, request, pk=None):
		"""게임 방에서 나갑니다."""
		room = get_object_or_404(game_rooms, pk=pk)

		room['players'] = [p for p in room['players'] if p['username'] != request.user.username]

		if not room['players']:
			del game_rooms[pk]
			event = "room_closed"
		else:
			if room['host'] == request.user.username:
				room['host'] = room['players'][0]['username']
			event = "player_left"

		# WebSocket 그룹에 플레이어 퇴장 또는 방 폐쇄 알림
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f"room_{pk}",
			{
				"type": "room_update",
				"event": event,
				"room": room
			}
		)

		return Response({'message': 'Successfully left the room'})

	@action(detail=True, methods=['post'])
	def ready(self, request, pk=None):
		"""플레이어의 준비 상태를 변경합니다."""
		room = get_object_or_404(game_rooms, pk=pk)

		for player in room['players']:
			if player['username'] == request.user.username:
				player['ready'] = request.data.get('ready', not player['ready'])
				break
		else:
			return Response({'error': 'Player not in room'}, status=status.HTTP_400_BAD_REQUEST)

		# WebSocket 그룹에 준비 상태 변경 알림
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f"room_{pk}",
			{
				"type": "player_ready",
				"username": request.user.username,
				"ready": player['ready']
			}
		)

		return Response(room)

	@action(detail=True, methods=['post'])
	def start_game(self, request, pk=None):
		"""게임을 시작합니다."""
		room = get_object_or_404(game_rooms, pk=pk)

		if request.user.username != room['host']:
			return Response({'error': 'Only host can start the game'}, status=status.HTTP_403_FORBIDDEN)

		if not all(player['ready'] for player in room['players']):
			return Response({'error': 'Not all players are ready'}, status=status.HTTP_400_BAD_REQUEST)

		room['game_started'] = True

		# WebSocket 그룹에 게임 시작 알림
		channel_layer = get_channel_layer()
		async_to_sync(channel_layer.group_send)(
			f"room_{pk}",
			{
				"type": "game_start",
				"room": room
			}
		)

		return Response(room)