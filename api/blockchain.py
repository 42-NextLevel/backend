from web3 import Web3
from eth_account import Account
import json
import os
from django.conf import settings

class ContractDeployer:
    def __init__(self):
        self.w3 = Web3(Web3.HTTPProvider(settings.WEB3_PROVIDER_URL))
        self.account = Account.from_key(settings.ETHEREUM_PRIVATE_KEY)
        
    def load_contract(self):
        with open(os.path.join(settings.BASE_DIR, 'contracts/MyContract.json')) as f:
            contract_json = json.load(f)
        return contract_json

    def deploy_contract(self):
        contract_json = self.load_contract()
        Contract = self.w3.eth.contract(
            abi=contract_json['abi'],
            bytecode=contract_json['bytecode']
        )
        
        nonce = self.w3.eth.get_transaction_count(self.account.address)
        
        # 컨트랙트 배포 트랜잭션 생성
        transaction = Contract.constructor().build_transaction({
            'from': self.account.address,
            'nonce': nonce,
            'gas': 2000000,
            'gasPrice': self.w3.eth.gas_price
        })
        
        # 트랜잭션 서명
        signed_txn = self.w3.eth.account.sign_transaction(
            transaction, settings.ETHEREUM_PRIVATE_KEY
        )
        
        # 트랜잭션 전송
        tx_hash = self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        # 트랜잭션 완료 대기
        tx_receipt = self.w3.eth.wait_for_transaction_receipt(tx_hash)
        
        return tx_receipt.contractAddress
