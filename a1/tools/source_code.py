import aiohttp
import asyncio
import json
from typing import Dict, Any, Optional, List
from web3 import Web3
import logging

logger = logging.getLogger(__name__)


class SourceCodeRetriever:
    """Multi-source smart contract code retrieval"""
    
    def __init__(self, etherscan_api_key: Optional[str] = None):
        self.etherscan_api_key = etherscan_api_key
        self.session = None
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    async def get_from_etherscan(self, address: str) -> Optional[Dict[str, Any]]:
        if not self.etherscan_api_key:
            return None
            
        url = "https://api.etherscan.io/api"
        params = {
            "module": "contract",
            "action": "getsourcecode",
            "address": address,
            "apikey": self.etherscan_api_key
        }
        
        try:
            async with self.session.get(url, params=params) as response:
                data = await response.json()
                
                if data["status"] == "1" and data["result"]:
                    result = data["result"][0]
                    if result["SourceCode"]:
                        return {
                            "source_code": result["SourceCode"],
                            "abi": json.loads(result["ABI"]) if result["ABI"] != "Contract source code not verified" else None,
                            "contract_name": result["ContractName"],
                            "compiler_version": result["CompilerVersion"],
                            "optimization_used": result["OptimizationUsed"] == "1",
                            "runs": int(result["Runs"]) if result["Runs"] else 200,
                            "evm_version": result.get("EVMVersion", ""),
                            "library": result.get("Library", ""),
                            "proxy": result.get("Proxy", "0") == "1",
                            "implementation": result.get("Implementation", "")
                        }
        except Exception as e:
            logger.error(f"Etherscan error: {e}")
            
        return None
        
    async def get_from_sourcify(self, address: str, chain_id: int = 1) -> Optional[Dict[str, Any]]:
        checksum_address = Web3.to_checksum_address(address)
        
        # Try full match first
        base_url = f"https://repo.sourcify.dev/contracts/full_match/{chain_id}/{checksum_address}"
        
        try:
            async with self.session.get(f"{base_url}/metadata.json") as response:
                if response.status == 200:
                    metadata = await response.json()
                    
                    # Get source files
                    sources = {}
                    for source_path in metadata.get("sources", {}).keys():
                        source_url = f"{base_url}/sources/{source_path}"
                        async with self.session.get(source_url) as source_response:
                            if source_response.status == 200:
                                sources[source_path] = await source_response.text()
                                
                    return {
                        "source_code": sources,
                        "metadata": metadata,
                        "abi": metadata.get("output", {}).get("abi", []),
                        "compiler_version": metadata.get("compiler", {}).get("version", ""),
                        "optimization": metadata.get("settings", {}).get("optimizer", {})
                    }
        except Exception as e:
            logger.debug(f"Sourcify full match failed: {e}")
            
        # Try partial match
        base_url = f"https://repo.sourcify.dev/contracts/partial_match/{chain_id}/{checksum_address}"
        
        try:
            async with self.session.get(f"{base_url}/metadata.json") as response:
                if response.status == 200:
                    # Similar process for partial match
                    pass
        except Exception as e:
            logger.debug(f"Sourcify partial match failed: {e}")
            
        return None
        
    async def get_from_blockscout(self, address: str, base_url: str = "https://eth.blockscout.com") -> Optional[Dict[str, Any]]:
        url = f"{base_url}/api/v2/smart-contracts/{address}"
        
        try:
            async with self.session.get(url) as response:
                if response.status == 200:
                    data = await response.json()
                    
                    if data.get("is_verified"):
                        return {
                            "source_code": data.get("source_code", ""),
                            "abi": data.get("abi", []),
                            "contract_name": data.get("name", ""),
                            "compiler_version": data.get("compiler_version", ""),
                            "optimization_enabled": data.get("optimization_enabled", False),
                            "optimization_runs": data.get("optimization_runs", 200),
                            "evm_version": data.get("evm_version", ""),
                            "verified_at": data.get("verified_at", "")
                        }
        except Exception as e:
            logger.debug(f"BlockScout error: {e}")
            
        return None
        
    async def get_contract_creation_code(self, address: str, eth_client) -> Optional[bytes]:
        """Get contract creation code from deployment transaction"""
        
        # This would require finding the contract creation transaction
        # and extracting the init code
        
        return None
        
    async def decompile_bytecode(self, bytecode: bytes) -> Optional[str]:
        """Attempt to decompile bytecode using external services"""
        
        # This could integrate with services like:
        # - Dedaub
        # - eveem.org
        # - ethervm.io
        
        return None
        
    async def get_source_code(
        self,
        address: str,
        chain_id: int = 1,
        etherscan_api_key: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get source code from multiple sources with fallback"""
        
        checksum_address = Web3.to_checksum_address(address)
        result = {
            "address": checksum_address,
            "verified": False,
            "source_code": None,
            "abi": None,
            "metadata": {}
        }
        
        # Try Etherscan first
        if etherscan_api_key or self.etherscan_api_key:
            etherscan_result = await self.get_from_etherscan(checksum_address)
            if etherscan_result:
                result.update({
                    "verified": True,
                    "source": "etherscan",
                    **etherscan_result
                })
                return result
                
        # Try Sourcify
        sourcify_result = await self.get_from_sourcify(checksum_address, chain_id)
        if sourcify_result:
            result.update({
                "verified": True,
                "source": "sourcify",
                **sourcify_result
            })
            return result
            
        # Try BlockScout
        blockscout_result = await self.get_from_blockscout(checksum_address)
        if blockscout_result:
            result.update({
                "verified": True,
                "source": "blockscout",
                **blockscout_result
            })
            return result
            
        # If no verified source found, return unverified
        logger.warning(f"No verified source code found for {checksum_address}")
        return result
        
    async def get_multiple_contracts(
        self,
        addresses: List[str],
        chain_id: int = 1
    ) -> Dict[str, Dict[str, Any]]:
        """Batch retrieve source code for multiple contracts"""
        
        tasks = [
            self.get_source_code(address, chain_id)
            for address in addresses
        ]
        
        results = await asyncio.gather(*tasks, return_exceptions=True)
        
        return {
            address: result if not isinstance(result, Exception) else {
                "address": address,
                "error": str(result),
                "verified": False
            }
            for address, result in zip(addresses, results)
        }