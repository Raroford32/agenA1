#!/usr/bin/env python3
import asyncio
import argparse
import json
import os
import sys
from datetime import datetime
import logging
from typing import Optional, List
import yaml

# Add project root to path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from lib.grok_llm import create_grok_client
from lib.ethereum_client import create_ethereum_client
from lib.exploit_agent import create_exploit_agent
from tools.source_code import SourceCodeRetriever
from tools.slither_runner import SlitherRunner

# Setup logging
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s'
)
logger = logging.getLogger(__name__)


class ExploitScanner:
    """Main scanner orchestrating Grok-4-0709 exploit generation on Ethereum"""
    
    def __init__(self, config_path: str = "config/models.yaml"):
        self.config = self._load_config(config_path)
        self.grok_client = None
        self.eth_client = None
        self.exploit_agent = None
        
    def _load_config(self, config_path: str) -> dict:
        """Load configuration from YAML file"""
        with open(config_path, 'r') as f:
            return yaml.safe_load(f)
            
    async def initialize(self):
        """Initialize all components"""
        logger.info("Initializing Grok-4-0709 Exploit Scanner")
        
        # Initialize Grok client
        grok_api_key = os.getenv("GROK_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        if not grok_api_key:
            raise ValueError("GROK_API_KEY or OPENROUTER_API_KEY environment variable required")
            
        self.grok_client = create_grok_client(grok_api_key)
        
        # Initialize Ethereum client
        eth_rpc_url = os.getenv("ETH_RPC_URL", "http://localhost:8545")
        self.eth_client = create_ethereum_client(eth_rpc_url)
        await self.eth_client.initialize()
        
        # Get current block for forking
        current_block = await self.eth_client.get_block_number()
        logger.info(f"Connected to Ethereum at block {current_block}")
        
        # Create exploit agent
        self.exploit_agent = await create_exploit_agent(
            grok_api_key=grok_api_key,
            eth_rpc_url=eth_rpc_url,
            fork_block=current_block
        )
        
    async def scan_contract(
        self,
        contract_address: str,
        deep_analysis: bool = True,
        simulate: bool = True,
        execute: bool = False
    ) -> dict:
        """Scan a single contract for vulnerabilities and generate exploits"""
        
        logger.info(f"Scanning contract: {contract_address}")
        scan_result = {
            "contract_address": contract_address,
            "scan_timestamp": datetime.now().isoformat(),
            "grok_model": "grok-4-0709",
            "network": "ethereum-mainnet",
            "vulnerabilities": [],
            "exploits": [],
            "source_code_analysis": {},
            "static_analysis": {},
            "total_profit_potential_eth": 0
        }
        
        try:
            # Step 1: Retrieve source code
            logger.info("Retrieving source code...")
            async with SourceCodeRetriever() as retriever:
                source_result = await retriever.get_source_code(
                    contract_address,
                    etherscan_api_key=os.getenv("ETHERSCAN_API_KEY")
                )
                scan_result["source_code_analysis"] = {
                    "verified": source_result["verified"],
                    "source": source_result.get("source", "unknown"),
                    "contract_name": source_result.get("contract_name", "Unknown"),
                    "compiler_version": source_result.get("compiler_version", "")
                }
                
            # Step 2: Run static analysis if source code available
            if source_result["verified"] and source_result["source_code"] and deep_analysis:
                logger.info("Running Slither static analysis...")
                async with SlitherRunner() as slither:
                    if isinstance(source_result["source_code"], str):
                        slither_result = await slither.analyze_source_code(
                            source_result["source_code"],
                            source_result.get("contract_name", "Contract"),
                            source_result.get("compiler_version", "0.8.19")
                        )
                        scan_result["static_analysis"] = slither_result
                        
            # Step 3: Use Grok-4-0709 for vulnerability analysis
            logger.info("Analyzing with Grok-4-0709...")
            async with self.grok_client as grok:
                vulnerabilities = await self.exploit_agent.analyze_contract(contract_address)
                scan_result["vulnerabilities"] = [
                    {
                        "type": v.vulnerability_type,
                        "severity": v.severity,
                        "description": v.description,
                        "attack_vector": v.attack_vector,
                        "estimated_profit_eth": v.estimated_profit_eth,
                        "confidence_score": v.confidence_score
                    }
                    for v in vulnerabilities
                ]
                
                # Step 4: Generate and simulate exploits
                if simulate:
                    for vuln in vulnerabilities:
                        if vuln.confidence_score < 0.7:
                            continue
                            
                        logger.info(f"Planning exploit for {vuln.vulnerability_type}...")
                        plan = await self.exploit_agent.plan_exploit(vuln)
                        
                        logger.info("Simulating exploit on forked mainnet...")
                        simulation_results = await self.exploit_agent.simulate_exploit(plan)
                        
                        exploit_data = {
                            "vulnerability_type": vuln.vulnerability_type,
                            "exploit_code_generated": bool(plan.exploit_contract_code),
                            "required_funds_eth": plan.required_funds_eth,
                            "expected_profit_eth": plan.expected_profit_eth,
                            "simulation_success": simulation_results.get("success", False),
                            "simulated_profit_eth": simulation_results.get("profit_eth", 0)
                        }
                        
                        scan_result["exploits"].append(exploit_data)
                        
                        if simulation_results.get("success"):
                            scan_result["total_profit_potential_eth"] += simulation_results.get("profit_eth", 0)
                            
                # Step 5: Execute exploits if requested (DANGEROUS!)
                if execute and os.getenv("PRIVATE_KEY"):
                    logger.warning("LIVE EXECUTION ENABLED - This will execute real transactions!")
                    # Implementation would go here
                    pass
                    
        except Exception as e:
            logger.error(f"Scan failed: {e}")
            scan_result["error"] = str(e)
            
        return scan_result
        
    async def scan_multiple(
        self,
        contract_addresses: List[str],
        parallel: int = 3
    ) -> List[dict]:
        """Scan multiple contracts with controlled parallelism"""
        
        results = []
        
        # Process in batches
        for i in range(0, len(contract_addresses), parallel):
            batch = contract_addresses[i:i+parallel]
            
            tasks = [
                self.scan_contract(address)
                for address in batch
            ]
            
            batch_results = await asyncio.gather(*tasks, return_exceptions=True)
            
            for address, result in zip(batch, batch_results):
                if isinstance(result, Exception):
                    results.append({
                        "contract_address": address,
                        "error": str(result)
                    })
                else:
                    results.append(result)
                    
        return results
        
    async def close(self):
        """Cleanup resources"""
        if self.grok_client and hasattr(self.grok_client, 'session'):
            await self.grok_client.__aexit__(None, None, None)


async def main():
    parser = argparse.ArgumentParser(
        description="Grok-4-0709 Exploit Scanner for Ethereum - A1 Implementation"
    )
    
    parser.add_argument(
        "addresses",
        nargs="+",
        help="Contract addresses to scan"
    )
    
    parser.add_argument(
        "--deep-analysis",
        action="store_true",
        default=True,
        help="Enable deep static analysis with Slither"
    )
    
    parser.add_argument(
        "--simulate",
        action="store_true",
        default=True,
        help="Simulate exploits on forked mainnet"
    )
    
    parser.add_argument(
        "--execute",
        action="store_true",
        default=False,
        help="DANGER: Execute exploits on mainnet (requires PRIVATE_KEY env var)"
    )
    
    parser.add_argument(
        "--output",
        type=str,
        help="Output file for results (JSON format)"
    )
    
    parser.add_argument(
        "--parallel",
        type=int,
        default=3,
        help="Number of parallel scans"
    )
    
    parser.add_argument(
        "--config",
        type=str,
        default="config/models.yaml",
        help="Path to configuration file"
    )
    
    args = parser.parse_args()
    
    # Initialize scanner
    scanner = ExploitScanner(args.config)
    await scanner.initialize()
    
    try:
        # Scan contracts
        if len(args.addresses) == 1:
            result = await scanner.scan_contract(
                args.addresses[0],
                deep_analysis=args.deep_analysis,
                simulate=args.simulate,
                execute=args.execute
            )
            results = [result]
        else:
            results = await scanner.scan_multiple(
                args.addresses,
                parallel=args.parallel
            )
            
        # Output results
        if args.output:
            with open(args.output, 'w') as f:
                json.dump(results, f, indent=2)
            logger.info(f"Results saved to {args.output}")
        else:
            print(json.dumps(results, indent=2))
            
        # Summary
        total_vulns = sum(len(r.get("vulnerabilities", [])) for r in results)
        total_profit = sum(r.get("total_profit_potential_eth", 0) for r in results)
        
        logger.info(f"\n{'='*50}")
        logger.info(f"Scan Summary:")
        logger.info(f"Contracts scanned: {len(results)}")
        logger.info(f"Total vulnerabilities found: {total_vulns}")
        logger.info(f"Total profit potential: {total_profit:.4f} ETH")
        logger.info(f"Model: Grok-4-0709 via OpenRouter")
        logger.info(f"Network: Ethereum Mainnet")
        logger.info(f"{'='*50}")
        
    finally:
        await scanner.close()


if __name__ == "__main__":
    asyncio.run(main())