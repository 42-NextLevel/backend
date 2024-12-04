import sys
import json
import traceback
from datetime import datetime, timezone
from Web3Client import Web3Client
import asyncio
import os

async def main():
	if len(sys.argv) < 4:
		print("Usage: save_blockchain_worker.py <game_id> <players_json> <room_copy_json>", file=sys.stderr)
		sys.exit(1)

	try:
		# 입력 데이터 파싱
		game_id = int(sys.argv[1]) 
		players = json.loads(sys.argv[2])  # 플레이어 정보
		room_copy = json.loads(sys.argv[3])  # 방 정보
		game_state = json.loads(sys.argv[4])  # 게임 상태
		match = sys.argv[5]  # 매치 타입
		

		score1 = int(game_state.get('score', {}).get('player1', 0))
		score2 = int(game_state.get('score', {}).get('player2', 0))


		# 환경 변수 검증
		if not os.environ.get('ETHEREUM_PRIVATE_KEY') or not os.environ.get('WEB3_PROVIDER_URL'):
			print("Missing required environment variables", file=sys.stderr)
			sys.exit(1)

		# Web3Client 초기화
		web3_client = Web3Client()

		# 시작 시간 변환
		start_time = datetime.fromtimestamp(room_copy['started_at'], tz=timezone.utc).strftime('%Y-%m-%d %H:%M:%S')

		# Solidity 구조체에 맞는 데이터 생성
		match_info = web3_client.make_match_struct(
			start_time=start_time,
			match_type=int(match),
			user1=str(players[0]['intraId']),
			user2=str(players[1]['intraId']), 
			nick1=str(players[0]['nickname']),
			nick2=str(players[1]['nickname']),
			score1=score1,
			score2=score2
		)

		# 블록체인 트랜잭션 실행
		tx_hash = await web3_client.add_match_history(game_id, match_info)

		if tx_hash:
			print(f"Transaction successful! Hash: {tx_hash}")
		else:
			print("Transaction failed", file=sys.stderr)
	except json.JSONDecodeError as e:
		print(f"JSON decode error: {e}", file=sys.stderr)
	except KeyError as e:
		print(f"Missing key: {e}", file=sys.stderr)
	except Exception as e:
		print(f"Error in save_blockchain_worker: {e}", file=sys.stderr)
		traceback.print_exc(file=sys.stderr)
		sys.exit(1)

if __name__ == "__main__":
	asyncio.run(main())
