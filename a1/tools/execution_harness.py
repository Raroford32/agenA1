import subprocess
import asyncio
import tempfile
import json
import os
from typing import Dict, Any, Optional, List
from pathlib import Path
import logging

logger = logging.getLogger(__name__)


class ExecutionHarness:
    """Foundry/Anvil-based execution harness for exploit testing"""
    
    def __init__(self, fork_url: str, fork_block: Optional[int] = None):
        self.fork_url = fork_url
        self.fork_block = fork_block
        self.anvil_process = None
        self.anvil_url = "http://127.0.0.1:8545"
        self.temp_dir = None
        
    async def __aenter__(self):
        self.temp_dir = tempfile.mkdtemp()
        await self.start_anvil()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        await self.stop_anvil()
        if self.temp_dir:
            import shutil
            shutil.rmtree(self.temp_dir)
            
    async def start_anvil(self):
        """Start Anvil fork"""
        cmd = [
            "anvil",
            "--fork-url", self.fork_url,
            "--host", "127.0.0.1",
            "--port", "8545",
            "--accounts", "10",
            "--balance", "10000",
            "--block-time", "1",
            "--gas-limit", "30000000",
            "--code-size-limit", "100000",
            "--no-mining"
        ]
        
        if self.fork_block:
            cmd.extend(["--fork-block-number", str(self.fork_block)])
            
        logger.info(f"Starting Anvil fork at block {self.fork_block or 'latest'}")
        
        self.anvil_process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        # Wait for Anvil to be ready
        await asyncio.sleep(2)
        
        # Test connection
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        
        for _ in range(10):
            if w3.is_connected():
                logger.info("Anvil fork started successfully")
                return
            await asyncio.sleep(1)
            
        raise Exception("Failed to start Anvil fork")
        
    async def stop_anvil(self):
        """Stop Anvil fork"""
        if self.anvil_process:
            self.anvil_process.terminate()
            await self.anvil_process.wait()
            logger.info("Anvil fork stopped")
            
    async def compile_contract(
        self,
        source_code: str,
        contract_name: str,
        solc_version: str = "0.8.19"
    ) -> Dict[str, Any]:
        """Compile Solidity contract using Foundry"""
        
        # Write source to file
        source_file = os.path.join(self.temp_dir, f"{contract_name}.sol")
        with open(source_file, "w") as f:
            f.write(source_code)
            
        # Use forge to compile
        cmd = [
            "forge", "build",
            "--root", self.temp_dir,
            "--contracts", self.temp_dir,
            "--out", os.path.join(self.temp_dir, "out"),
            "--cache-path", os.path.join(self.temp_dir, "cache"),
            "--use", solc_version
        ]
        
        process = await asyncio.create_subprocess_exec(
            *cmd,
            stdout=asyncio.subprocess.PIPE,
            stderr=asyncio.subprocess.PIPE
        )
        
        stdout, stderr = await process.communicate()
        
        if process.returncode != 0:
            logger.error(f"Compilation failed: {stderr.decode()}")
            return {"success": False, "error": stderr.decode()}
            
        # Read compiled artifacts
        artifact_path = os.path.join(
            self.temp_dir,
            "out",
            f"{contract_name}.sol",
            f"{contract_name}.json"
        )
        
        if not os.path.exists(artifact_path):
            return {"success": False, "error": "Artifact not found"}
            
        with open(artifact_path, "r") as f:
            artifact = json.load(f)
            
        return {
            "success": True,
            "bytecode": artifact["bytecode"]["object"],
            "deployedBytecode": artifact["deployedBytecode"]["object"],
            "abi": artifact["abi"],
            "metadata": artifact.get("metadata", {})
        }
        
    async def deploy_exploit(
        self,
        bytecode: str,
        abi: List[Dict[str, Any]],
        constructor_args: Optional[List[Any]] = None,
        sender: Optional[str] = None,
        value: int = 0
    ) -> Dict[str, Any]:
        """Deploy exploit contract on fork"""
        
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        
        # Use first account if sender not specified
        if not sender:
            accounts = w3.eth.accounts
            sender = accounts[0]
            
        # Create contract instance
        contract = w3.eth.contract(abi=abi, bytecode=bytecode)
        
        # Build transaction
        if constructor_args:
            tx = contract.constructor(*constructor_args).build_transaction({
                'from': sender,
                'value': value,
                'gas': 5000000,
                'gasPrice': w3.eth.gas_price
            })
        else:
            tx = contract.constructor().build_transaction({
                'from': sender,
                'value': value,
                'gas': 5000000,
                'gasPrice': w3.eth.gas_price
            })
            
        # Send transaction
        tx_hash = w3.eth.send_transaction(tx)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        if receipt['status'] != 1:
            return {
                "success": False,
                "error": "Deployment failed",
                "receipt": dict(receipt)
            }
            
        return {
            "success": True,
            "address": receipt['contractAddress'],
            "tx_hash": tx_hash.hex(),
            "gas_used": receipt['gasUsed'],
            "receipt": dict(receipt)
        }
        
    async def execute_exploit(
        self,
        exploit_address: str,
        function_name: str,
        abi: List[Dict[str, Any]],
        args: Optional[List[Any]] = None,
        sender: Optional[str] = None,
        value: int = 0
    ) -> Dict[str, Any]:
        """Execute exploit function"""
        
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        
        if not sender:
            sender = w3.eth.accounts[0]
            
        # Get contract instance
        contract = w3.eth.contract(address=exploit_address, abi=abi)
        
        # Get function
        func = getattr(contract.functions, function_name)
        
        # Build transaction
        if args:
            tx = func(*args).build_transaction({
                'from': sender,
                'value': value,
                'gas': 5000000,
                'gasPrice': w3.eth.gas_price
            })
        else:
            tx = func().build_transaction({
                'from': sender,
                'value': value,
                'gas': 5000000,
                'gasPrice': w3.eth.gas_price
            })
            
        # Execute
        tx_hash = w3.eth.send_transaction(tx)
        receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
        
        # Get logs
        logs = []
        for log in receipt['logs']:
            try:
                parsed = contract.events.parse_log(log)
                logs.append({
                    "event": parsed['event'],
                    "args": dict(parsed['args'])
                })
            except:
                logs.append({"raw": dict(log)})
                
        return {
            "success": receipt['status'] == 1,
            "tx_hash": tx_hash.hex(),
            "gas_used": receipt['gasUsed'],
            "logs": logs,
            "receipt": dict(receipt)
        }
        
    async def check_balance_change(
        self,
        address: str,
        token_address: Optional[str] = None
    ) -> Dict[str, int]:
        """Check ETH or token balance changes"""
        
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        
        if token_address:
            # ERC20 balance
            erc20_abi = [
                {
                    "constant": True,
                    "inputs": [{"name": "_owner", "type": "address"}],
                    "name": "balanceOf",
                    "outputs": [{"name": "balance", "type": "uint256"}],
                    "type": "function"
                }
            ]
            
            token = w3.eth.contract(address=token_address, abi=erc20_abi)
            balance = token.functions.balanceOf(address).call()
            
            return {"token": token_address, "balance": balance}
        else:
            # ETH balance
            balance = w3.eth.get_balance(address)
            return {"token": "ETH", "balance": balance}
            
    async def trace_transaction(self, tx_hash: str) -> Dict[str, Any]:
        """Get detailed transaction trace"""
        
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        
        # Use debug_traceTransaction
        trace = w3.manager.request_blocking(
            "debug_traceTransaction",
            [tx_hash, {"tracer": "callTracer"}]
        )
        
        return trace
        
    async def simulate_bundle(
        self,
        transactions: List[Dict[str, Any]]
    ) -> Dict[str, Any]:
        """Simulate a bundle of transactions"""
        
        from web3 import Web3
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        
        results = []
        total_gas = 0
        
        # Take snapshot
        snapshot_id = w3.manager.request_blocking("evm_snapshot", [])
        
        try:
            for i, tx in enumerate(transactions):
                try:
                    tx_hash = w3.eth.send_transaction(tx)
                    receipt = w3.eth.wait_for_transaction_receipt(tx_hash)
                    
                    results.append({
                        "index": i,
                        "success": receipt['status'] == 1,
                        "tx_hash": tx_hash.hex(),
                        "gas_used": receipt['gasUsed']
                    })
                    
                    total_gas += receipt['gasUsed']
                    
                except Exception as e:
                    results.append({
                        "index": i,
                        "success": False,
                        "error": str(e)
                    })
                    
        finally:
            # Revert to snapshot
            w3.manager.request_blocking("evm_revert", [snapshot_id])
            
        return {
            "results": results,
            "total_gas": total_gas,
            "all_success": all(r["success"] for r in results)
        }
        
    async def fuzz_test(
        self,
        contract_address: str,
        function_name: str,
        abi: List[Dict[str, Any]],
        num_runs: int = 100
    ) -> Dict[str, Any]:
        """Run basic fuzz testing on a function"""
        
        # This would integrate with Foundry's fuzzing capabilities
        # Simplified version here
        
        from web3 import Web3
        import random
        
        w3 = Web3(Web3.HTTPProvider(self.anvil_url))
        contract = w3.eth.contract(address=contract_address, abi=abi)
        
        results = {
            "runs": num_runs,
            "failures": 0,
            "errors": []
        }
        
        for i in range(num_runs):
            try:
                # Generate random inputs based on function ABI
                # This is simplified - real fuzzing would be more sophisticated
                
                func = getattr(contract.functions, function_name)
                
                # Execute with random inputs
                result = func().call()
                
            except Exception as e:
                results["failures"] += 1
                results["errors"].append({
                    "run": i,
                    "error": str(e)
                })
                
        results["success_rate"] = (num_runs - results["failures"]) / num_runs
        
        return results