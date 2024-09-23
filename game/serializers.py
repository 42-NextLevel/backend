from rest_framework import serializers
from .models import GameLog, UserGameLog
from api.serializers import UserSerializer
from api.models import User

class GameLogSerializer(serializers.ModelSerializer):
    players = serializers.SerializerMethodField()

    class Meta:
        model = GameLog
        fields = ['id', 'start_time', 'match_type', 'address', 'players']
        read_only_fields = ['id', 'players']

    def get_players(self, obj):
        user_game_logs = UserGameLog.objects.filter(game_log=obj)
        return UserGameLogSerializer(user_game_logs, many=True).data

    def create(self, validated_data):
        players_data = self.context['request'].data.get('players', [])
        game_log = GameLog.objects.create(**validated_data)

        for player_data in players_data:
            UserGameLog.objects.create(
                user_id=player_data['user_id'],
                game_log=game_log,
                nickname=player_data['nickname']
            )

        return game_log

    def update(self, instance, validated_data):
        instance.start_time = validated_data.get('start_time', instance.start_time)
        instance.match_type = validated_data.get('match_type', instance.match_type)
        instance.address = validated_data.get('address', instance.address)
        instance.save()
        return instance

class UserGameLogSerializer(serializers.ModelSerializer):
    user = UserSerializer(read_only=True)

    class Meta:
        model = UserGameLog
        fields = ['id', 'user', 'nickname', 'score']
        read_only_fields = ['id', 'user']

    def create(self, validated_data):
        user_id = self.context['request'].data.get('user_id')
        user = User.objects.get(id=user_id)
        validated_data['user'] = user
        return super().create(validated_data)