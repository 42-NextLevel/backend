import json
from channels.generic.websocket import AsyncWebsocketConsumer
from django.core.cache import cache
from channels.db import database_sync_to_async
from asgiref.sync import sync_to_async
import sys

class GameConsumer(AsyncWebsocketConsumer):
    async def connect(self):
        print("connect", sys.stderr)
        self.room_id = self.scope['url_route']['kwargs']['room_id']
        self.room_group_name = f'game_{self.room_id}'
        self.user = self.scope['user']

        # Join room group
        print("test", sys.stderr)
        await self.channel_layer.group_add(
            self.room_group_name,
            self.channel_name
        )

        await self.accept()

        # Send current room info to the new connection
        room = await self.get_room()
        if room:
            await self.send(text_data=json.dumps({
                'type': 'room_update',
                'room': room
            }))

    async def disconnect(self, close_code):
        # Leave room group
        await self.channel_layer.group_discard(
            self.room_group_name,
            self.channel_name
        )

    async def receive(self, text_data):
        text_data_json = json.loads(text_data)
        message_type = text_data_json.get('type')
        
        if message_type == 'chat_message':
            await self.handle_chat_message(text_data_json)
        elif message_type == 'game_action':
            await self.handle_game_action(text_data_json)
        else:
            # Handle other message types as needed
            pass

    @database_sync_to_async
    def get_room(self):
        return cache.get(f'game_room_{self.room_id}')

    async def room_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'room_update',
            'room': event['room']
        }))

    async def game_start(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_start',
            'room': event['room']
        }))

    async def handle_chat_message(self, data):
        message = data['message']
        await self.channel_layer.group_send(
            self.room_group_name,
            {
                'type': 'chat_message',
                'message': message,
                'sender': self.user.username
            }
        )

    async def chat_message(self, event):
        await self.send(text_data=json.dumps({
            'type': 'chat_message',
            'message': event['message'],
            'sender': event['sender']
        }))

    async def handle_game_action(self, data):
        action = data['action']
        # Process game action here
        # Update game state in cache if necessary
        room = await self.get_room()
        if room:
            # Update room state based on the action
            # This is where you'd implement game logic
            await sync_to_async(cache.set)(f'game_room_{self.room_id}', room, timeout=3600)
            
            # Broadcast the updated game state to all players
            await self.channel_layer.group_send(
                self.room_group_name,
                {
                    'type': 'game_update',
                    'room': room,
                    'action': action
                }
            )

    async def game_update(self, event):
        await self.send(text_data=json.dumps({
            'type': 'game_update',
            'room': event['room'],
            'action': event['action']
        }))