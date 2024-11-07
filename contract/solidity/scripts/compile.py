import json
import os
from solcx import compile_standard, install_solc
from pathlib import Path

def compile_contracts():
	# solc 버전 설치 (프로젝트에 맞는 버전 사용)
	install_solc("0.8.26")
		
	# 소스 디렉토리와 빌드 디렉토리 경로
	current_dir = Path(__file__).parent.parent
	sources_dir = current_dir / "sources"
	builds_dir = current_dir / "builds"
		
	# 빌드 디렉토리가 없으면 생성
	builds_dir.mkdir(exist_ok=True)
	
	compiler_settings = {
		"optimizer": {
			"enabled": True,
			"runs": 200
		},
		"outputSelection": {
			"*": {
				"": ["ast"],
				"*": [
					"abi",
					"metadata",
					"devdoc",
					"userdoc",
					"storageLayout",
					"evm.legacyAssembly",
					"evm.bytecode",
					"evm.deployedBytecode",
					"evm.methodIdentifiers",
					"evm.gasEstimates",
					"evm.assembly"
				]
			}
		}
	}

	# 각 .sol 파일에 대해 컴파일 수행
	for sol_file in sources_dir.glob("*.sol"):
		with open(sol_file, "r") as file:
			source = file.read()
			
		# 컴파일 설정
	compiled_sol = compile_standard(
		{
			"language": "Solidity",
			"sources": {
				sol_file.name: {
					"content": source
				}
			},
			"settings": compiler_settings
		},
		solc_version="0.8.26"
	)

	# 컴파일 결과 저장
	contract_name = sol_file.stem
	build_file = builds_dir / f"{contract_name}.json"
	
	# 필요한 정보만 추출하여 저장
	contract_data = compiled_sol['contracts'][sol_file.name][contract_name]
	output = {
		'abi': contract_data['abi'],
		'bytecode': contract_data['evm']['bytecode']['object']
	}
	
	with open(build_file, 'w') as f:
		json.dump(output, f, indent=2)
		
	print(f"Compiled {contract_name} -> {build_file}")

if __name__ == "__main__":
	compile_contracts()