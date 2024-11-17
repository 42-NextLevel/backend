from django.urls import path
# render 함수를 사용하기 위해 import
from django.shortcuts import render
from .views import get_contract_info


# 예상되는 url 패턴
# /contract/game/1
# /contract/game/2
# /contract/game/3
urlpatterns = [
    path('game/<int:game_id>', get_contract_info, name='get_contract_info'),
]