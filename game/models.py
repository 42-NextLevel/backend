from django.db import models
from django.contrib.auth.models import User

class GameLog(models.Model):
    id = models.AutoField(primary_key=True)
    start_time = models.DateTimeField()
    match_type = models.IntegerField()
    address = models.CharField(max_length=255, null=True)

    class Meta:
        db_table = 'tb_gamelog'

class UserGameLog(models.Model):
    user = models.ForeignKey(User, on_delete=models.CASCADE, db_column='user_id')
    game_log = models.ForeignKey(GameLog, on_delete=models.CASCADE, db_column='game_log_id')
    nickname = models.CharField(max_length=15)
    score = models.IntegerField()

    class Meta:
        db_table = 'tb_user_gamelog'