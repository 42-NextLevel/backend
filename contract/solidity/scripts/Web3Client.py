import sys
import os
import json
import time
from web3 import Web3
from pathlib import Path
from datetime import datetime
from eth_account import Account
from solcx import compile_standard, install_solc
from asgiref.sync import sync_to_async

class Web3Client:
	_instance = None

	def __new__(cls):
		if cls._instance is None:
			cls._instance = super(Web3Client, cls).__new__(cls)
			cls._instance._initialize()
		return cls._instance
	
	def _initialize(self):
		self.alchemy_url = os.environ.get('WEB3_PROVIDER_URL')
		self.w3 = Web3(Web3.HTTPProvider(self.alchemy_url))
		self._load_contract()

	def _load_contract(self):
		self._load_contract_artifacts()
		self._setup_account()
		self.contract_address = os.environ.get("CONTRACT_ADDRESS")
		if not self.contract_address:
			self.contract_address = self._deploy_contract()
			os.environ["CONTRACT_ADDRESS"] = self.contract_address

	def _load_contract_artifacts(self):
		"""컨트랙트 ABI와 바이트코드 로딩"""
		contract_path = Path(__file__).parent.parent / 'builds' / 'PongHistory.json'
		with open(contract_path, 'r') as file:
			compiled_contract = json.load(file)
		self.contract_abi = compiled_contract['abi']
		self.contract_bytecode = compiled_contract['bytecode']
		
	def _setup_account(self):
		private_key = os.environ.get('ETHEREUM_PRIVATE_KEY')
		self.account = Account.from_key(private_key)		
		
	def _deploy_contract(self):
		"""컨트랙트 배포"""
		Contract = self.w3.eth.contract(
			abi=self.contract_abi, 
			bytecode=self.contract_bytecode
		)

		# 트랜잭션 생성
		nonce = self.w3.eth.get_transaction_count(self.account.address)
		transaction = Contract.constructor().build_transaction({
			'from': self.account.address,
			'nonce': nonce,
			'gas': 2000000,
			'gasPrice': self.w3.eth.gas_price,
			'chainId': 11155111  # Sepolia chainId
		})

		# 트랜잭션 서명 및 전송
		signed_txn = self.w3.eth.account.sign_transaction(
			transaction, 
			os.environ.get('ETHEREUM_PRIVATE_KEY')
		)
		tx_hash = self.w3.eth.send_raw_transaction(signed_txn.raw_transaction)

		# 트랜잭션 영수증 대기
		tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
		return tx_receipt.contractAddress

	def get_contract(self):
		if not hasattr(self, 'contract'):
			self.contract = self.w3.eth.contract(
				address=self.contract_address,
				abi=self.contract_abi
			)
		return self.contract

	@staticmethod
	def _convert_datetime_to_timestamp(date_string: str) -> int:
		"""날짜 문자열을 Unix timestamp로 변환"""
		dt = datetime.strptime(date_string, '%Y-%m-%d %H:%M:%S')
		return int(dt.timestamp())

	@staticmethod
	def _truncate_and_encode(s: str, size: int = 16) -> bytes:
		"""문자열을 지정된 크기의 bytes로 변환"""
		return s.encode('utf-8')[:size].ljust(size, b'\0')

	@staticmethod
	def _clean_bytes16(b: bytes) -> str:
		"""bytes16을 문자열로 변환하고 null 바이트 제거"""
		return b.rstrip(b'\x00').decode('utf-8')

	def make_match_struct(self, 
						 start_time: str,
						 match_type: int,
						 user1: str,
						 user2: str,
						 nick1: str,
						 nick2: str,
						 score1: int,
						 score2: int) -> tuple:
		"""게임 매치 정보를 컨트랙트 구조체 형태로 변환"""
		return (
			self._convert_datetime_to_timestamp(start_time),# uint256
			match_type,										# uint8
			self._truncate_and_encode(user1),				# bytes16
			self._truncate_and_encode(user2),				# bytes16
			self._truncate_and_encode(nick1),				# bytes16
			self._truncate_and_encode(nick2),				# bytes16
			score1,											# uint8
			score2										   	# uint8
		)

	def get_match_history(self, game_id: int) -> dict:
		"""게임 ID로 매치 히스토리 조회"""
		contract = self.get_contract()
		history = contract.functions.getHistory(game_id).call()
		
		return self.format_match_history(history)

	def format_match_history(self, history: tuple) -> dict:
		"""매치 히스토리 데이터를 읽기 쉬운 형태로 변환"""
		print(history, sys.stderr)
		# readable_time = datetime.fromtimestamp(history[0]).strftime('%Y-%m-%d %H:%M:%S')
		# print(f"log2: {readable_time}", sys.stderr)
		return {
			'startTime': history[0],
			'matchType': history[1],
			'user1': self._clean_bytes16(history[2]),
			'user2': self._clean_bytes16(history[3]),
			'nick1': self._clean_bytes16(history[4]),
			'nick2': self._clean_bytes16(history[5]),
			'score1': history[6],
			'score2': history[7]
		}

	async def add_match_history(self, game_id: int, match_info: tuple) -> str:
		"""새로운 매치 히스토리 추가"""
		contract = self.get_contract()
		
		# 트랜잭션 생성을 비동기로 처리
		get_nonce = sync_to_async(self.w3.eth.get_transaction_count)
		get_gas_price = sync_to_async(lambda: self.w3.eth.gas_price * 2)
		
		nonce = await get_nonce(self.account.address)
		gas_price = await get_gas_price()
		
		# build_transaction을 비동기로 처리
		build_tx = sync_to_async(contract.functions.addHistory(game_id, match_info).build_transaction)
		txn = await build_tx({
			'from': self.account.address,
			'nonce': nonce,
			'gas': 2000000,
			'gasPrice': gas_price,
			'chainId': 11155111
		})

		# 트랜잭션 서명
		sign_tx = sync_to_async(self.w3.eth.account.sign_transaction)
		signed_txn = await sign_tx(txn, os.environ.get('ETHEREUM_PRIVATE_KEY'))
		
		# 트랜잭션 전송
		send_raw_tx = sync_to_async(self.w3.eth.send_raw_transaction)
		tx_hash = await send_raw_tx(signed_txn.raw_transaction)
		
		# 트랜잭션 영수증 대기를 비동기로 처리
		wait_for_tx = sync_to_async(self.w3.eth.wait_for_transaction_receipt)
		tx_receipt = await wait_for_tx(tx_hash)
		
		print(f"Transaction successful! Hash: {tx_hash.hex()}")
		return tx_hash.hex()