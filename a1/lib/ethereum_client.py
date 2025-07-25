import os
import json
import asyncio
from web3 import Web3, AsyncWeb3
from web3.providers import AsyncHTTPProvider
from eth_account import Account
from eth_typing import Address, HexStr
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
import logging
from decimal import Decimal
from hexbytes import HexBytes

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class EthereumConfig:
    rpc_url: str
    chain_id: int = 1
    gas_price_multiplier: float = 1.1
    max_gas_price_gwei: int = 300
    default_gas_limit: int = 3000000
    confirmation_blocks: int = 2
    archive_node: bool = True
    

class EthereumClient:
    def __init__(self, config: EthereumConfig):
        self.config = config
        self.w3 = AsyncWeb3(AsyncHTTPProvider(config.rpc_url))
        self._chain_id = None
        
    async def initialize(self):
        self._chain_id = await self.w3.eth.chain_id
        if self._chain_id != self.config.chain_id:
            logger.warning(f"Chain ID mismatch: expected {self.config.chain_id}, got {self._chain_id}")
            
        is_connected = await self.w3.is_connected()
        if not is_connected:
            raise ConnectionError(f"Failed to connect to Ethereum node at {self.config.rpc_url}")
            
        logger.info(f"Connected to Ethereum network, chain ID: {self._chain_id}")
        
    async def get_block_number(self) -> int:
        return await self.w3.eth.block_number
        
    async def get_block(self, block_identifier: Union[int, str]) -> Dict[str, Any]:
        block = await self.w3.eth.get_block(block_identifier, full_transactions=True)
        return dict(block)
        
    async def get_balance(self, address: str) -> int:
        checksum_address = Web3.to_checksum_address(address)
        return await self.w3.eth.get_balance(checksum_address)
        
    async def get_code(self, address: str, block_identifier: Union[int, str] = 'latest') -> HexBytes:
        checksum_address = Web3.to_checksum_address(address)
        return await self.w3.eth.get_code(checksum_address, block_identifier)
        
    async def get_storage_at(
        self,
        address: str,
        position: int,
        block_identifier: Union[int, str] = 'latest'
    ) -> HexBytes:
        checksum_address = Web3.to_checksum_address(address)
        return await self.w3.eth.get_storage_at(checksum_address, position, block_identifier)
        
    async def call(
        self,
        transaction: Dict[str, Any],
        block_identifier: Union[int, str] = 'latest'
    ) -> HexBytes:
        if 'to' in transaction:
            transaction['to'] = Web3.to_checksum_address(transaction['to'])
        if 'from' in transaction:
            transaction['from'] = Web3.to_checksum_address(transaction['from'])
            
        return await self.w3.eth.call(transaction, block_identifier)
        
    async def estimate_gas(self, transaction: Dict[str, Any]) -> int:
        if 'to' in transaction:
            transaction['to'] = Web3.to_checksum_address(transaction['to'])
        if 'from' in transaction:
            transaction['from'] = Web3.to_checksum_address(transaction['from'])
            
        return await self.w3.eth.estimate_gas(transaction)
        
    async def get_gas_price(self) -> int:
        base_price = await self.w3.eth.gas_price
        adjusted_price = int(base_price * self.config.gas_price_multiplier)
        max_price = Web3.to_wei(self.config.max_gas_price_gwei, 'gwei')
        return min(adjusted_price, max_price)
        
    async def send_transaction(
        self,
        transaction: Dict[str, Any],
        private_key: str
    ) -> HexStr:
        account = Account.from_key(private_key)
        
        if 'nonce' not in transaction:
            transaction['nonce'] = await self.w3.eth.get_transaction_count(account.address)
            
        if 'gasPrice' not in transaction:
            transaction['gasPrice'] = await self.get_gas_price()
            
        if 'gas' not in transaction:
            transaction['gas'] = await self.estimate_gas(transaction)
            
        if 'chainId' not in transaction:
            transaction['chainId'] = self._chain_id
            
        signed_txn = self.w3.eth.account.sign_transaction(transaction, private_key)
        tx_hash = await self.w3.eth.send_raw_transaction(signed_txn.rawTransaction)
        
        logger.info(f"Transaction sent: {tx_hash.hex()}")
        return tx_hash
        
    async def wait_for_transaction_receipt(
        self,
        tx_hash: HexStr,
        timeout: int = 120
    ) -> Dict[str, Any]:
        receipt = await self.w3.eth.wait_for_transaction_receipt(tx_hash, timeout=timeout)
        
        if self.config.confirmation_blocks > 0:
            target_block = receipt['blockNumber'] + self.config.confirmation_blocks
            while await self.get_block_number() < target_block:
                await asyncio.sleep(1)
                
        return dict(receipt)
        
    async def deploy_contract(
        self,
        bytecode: str,
        abi: List[Dict[str, Any]],
        private_key: str,
        constructor_args: Optional[List[Any]] = None,
        **kwargs
    ) -> Dict[str, Any]:
        account = Account.from_key(private_key)
        
        contract = self.w3.eth.contract(abi=abi, bytecode=bytecode)
        
        if constructor_args:
            transaction = contract.constructor(*constructor_args).build_transaction({
                'from': account.address,
                'nonce': await self.w3.eth.get_transaction_count(account.address),
                'gasPrice': await self.get_gas_price(),
                **kwargs
            })
        else:
            transaction = contract.constructor().build_transaction({
                'from': account.address,
                'nonce': await self.w3.eth.get_transaction_count(account.address),
                'gasPrice': await self.get_gas_price(),
                **kwargs
            })
            
        tx_hash = await self.send_transaction(transaction, private_key)
        receipt = await self.wait_for_transaction_receipt(tx_hash)
        
        if receipt['status'] != 1:
            raise Exception(f"Contract deployment failed: {receipt}")
            
        contract_address = receipt['contractAddress']
        logger.info(f"Contract deployed at: {contract_address}")
        
        return {
            'address': contract_address,
            'tx_hash': tx_hash.hex(),
            'receipt': receipt,
            'abi': abi
        }
        
    async def get_contract(
        self,
        address: str,
        abi: List[Dict[str, Any]]
    ):
        checksum_address = Web3.to_checksum_address(address)
        return self.w3.eth.contract(address=checksum_address, abi=abi)
        
    async def multicall(
        self,
        calls: List[Dict[str, Any]],
        block_identifier: Union[int, str] = 'latest'
    ) -> List[Any]:
        multicall_address = "0xeefBa1e63905eF1D7ACbA5a8513c70307C1cE441"
        
        multicall_abi = [
            {
                "constant": False,
                "inputs": [
                    {
                        "components": [
                            {"name": "target", "type": "address"},
                            {"name": "callData", "type": "bytes"}
                        ],
                        "name": "calls",
                        "type": "tuple[]"
                    }
                ],
                "name": "aggregate",
                "outputs": [
                    {"name": "blockNumber", "type": "uint256"},
                    {"name": "returnData", "type": "bytes[]"}
                ],
                "payable": False,
                "stateMutability": "nonpayable",
                "type": "function"
            }
        ]
        
        multicall = await self.get_contract(multicall_address, multicall_abi)
        
        formatted_calls = [
            (Web3.to_checksum_address(call['target']), call['callData'])
            for call in calls
        ]
        
        result = await multicall.functions.aggregate(formatted_calls).call(
            block_identifier=block_identifier
        )
        
        return result[1]
        
    async def trace_transaction(self, tx_hash: HexStr) -> Dict[str, Any]:
        if not self.config.archive_node:
            raise Exception("Transaction tracing requires an archive node")
            
        return await self.w3.manager.request_blocking(
            "debug_traceTransaction",
            [tx_hash, {"tracer": "callTracer"}]
        )
        
    async def get_logs(
        self,
        from_block: Union[int, str],
        to_block: Union[int, str],
        address: Optional[Union[str, List[str]]] = None,
        topics: Optional[List[Optional[Union[str, List[str]]]]] = None
    ) -> List[Dict[str, Any]]:
        filter_params = {
            'fromBlock': from_block,
            'toBlock': to_block
        }
        
        if address:
            if isinstance(address, list):
                filter_params['address'] = [Web3.to_checksum_address(a) for a in address]
            else:
                filter_params['address'] = Web3.to_checksum_address(address)
                
        if topics:
            filter_params['topics'] = topics
            
        logs = await self.w3.eth.get_logs(filter_params)
        return [dict(log) for log in logs]
        

class ForkSimulator:
    def __init__(self, ethereum_client: EthereumClient, fork_block: int):
        self.client = ethereum_client
        self.fork_block = fork_block
        
    async def create_fork(self) -> Dict[str, Any]:
        params = {
            "jsonrpc": "2.0",
            "method": "anvil_reset",
            "params": [{
                "forking": {
                    "jsonRpcUrl": self.client.config.rpc_url,
                    "blockNumber": self.fork_block
                }
            }],
            "id": 1
        }
        
        return params
        
    async def impersonate_account(self, address: str):
        checksum_address = Web3.to_checksum_address(address)
        await self.client.w3.manager.request_blocking(
            "anvil_impersonateAccount",
            [checksum_address]
        )
        
    async def set_balance(self, address: str, balance: int):
        checksum_address = Web3.to_checksum_address(address)
        balance_hex = hex(balance)
        await self.client.w3.manager.request_blocking(
            "anvil_setBalance",
            [checksum_address, balance_hex]
        )
        
    async def mine_block(self, timestamp: Optional[int] = None):
        if timestamp:
            await self.client.w3.manager.request_blocking(
                "evm_mine",
                [timestamp]
            )
        else:
            await self.client.w3.manager.request_blocking(
                "evm_mine",
                []
            )
            
    async def snapshot(self) -> str:
        return await self.client.w3.manager.request_blocking(
            "evm_snapshot",
            []
        )
        
    async def revert(self, snapshot_id: str):
        await self.client.w3.manager.request_blocking(
            "evm_revert",
            [snapshot_id]
        )


def create_ethereum_client(
    rpc_url: Optional[str] = None,
    chain_id: int = 1
) -> EthereumClient:
    if not rpc_url:
        rpc_url = os.getenv("ETH_RPC_URL", "http://localhost:8545")
        
    config = EthereumConfig(
        rpc_url=rpc_url,
        chain_id=chain_id
    )
    
    return EthereumClient(config)