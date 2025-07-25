import asyncio
from typing import Dict, Any, List, Optional, Tuple
from dataclasses import dataclass
from decimal import Decimal
from web3 import Web3
import logging

logger = logging.getLogger(__name__)


@dataclass
class DexPool:
    address: str
    protocol: str
    token0: str
    token1: str
    reserve0: int
    reserve1: int
    fee: float
    liquidity: int
    

@dataclass
class SwapRoute:
    path: List[str]
    pools: List[DexPool]
    amount_in: int
    amount_out: int
    price_impact: float
    gas_estimate: int
    

class DexLiquidityChecker:
    """Check liquidity and find optimal swap paths across multiple DEXs"""
    
    # DEX Factory addresses
    FACTORIES = {
        "uniswap_v2": "0x5C69bEe701ef814a2B6a3EDD4B1652CB9cc5aA6f",
        "sushiswap": "0xC0AEe478e3658e2610c5F7A4A2E1777cE9e4f2Ac",
        "uniswap_v3": "0x1F98431c8aD98523631AE4a59f267346ea31F984"
    }
    
    # Router addresses
    ROUTERS = {
        "uniswap_v2": "0x7a250d5630B4cF539739dF2C5dAcb4c659F2488D",
        "sushiswap": "0xd9e1cE17f2641f24aE83637ab66a2cca9C378B9F",
        "uniswap_v3": "0xE592427A0AEce92De3Edee1F18E0157C05861564",
        "curve": "0x8301AE4fc9c624d1D396cbDAa1ed877821D7C511",
        "balancer": "0xBA12222222228d8Ba445958a75a0704d566BF2C8"
    }
    
    def __init__(self, eth_client):
        self.eth_client = eth_client
        self.pool_cache = {}
        
    async def find_pools_for_token(
        self,
        token_address: str,
        quote_tokens: List[str] = None
    ) -> List[DexPool]:
        """Find all pools containing a specific token"""
        
        if quote_tokens is None:
            # Default quote tokens
            quote_tokens = [
                "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
                "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
                "0xdAC17F958D2ee523a2206206994597C13D831ec7",  # USDT
                "0x6B175474E89094C44Da98b954EedeAC495271d0F"   # DAI
            ]
            
        pools = []
        
        # Check Uniswap V2 style pools
        for dex in ["uniswap_v2", "sushiswap"]:
            for quote_token in quote_tokens:
                pool = await self._get_v2_pool(
                    token_address,
                    quote_token,
                    self.FACTORIES[dex]
                )
                if pool:
                    pool.protocol = dex
                    pools.append(pool)
                    
        # Check Uniswap V3 pools
        v3_pools = await self._get_v3_pools(token_address, quote_tokens)
        pools.extend(v3_pools)
        
        return pools
        
    async def _get_v2_pool(
        self,
        token0: str,
        token1: str,
        factory: str
    ) -> Optional[DexPool]:
        """Get Uniswap V2 style pool information"""
        
        # Order tokens
        token0_addr = Web3.to_checksum_address(token0)
        token1_addr = Web3.to_checksum_address(token1)
        
        if int(token0_addr, 16) > int(token1_addr, 16):
            token0_addr, token1_addr = token1_addr, token0_addr
            
        # Calculate pair address
        factory_abi = [
            {
                "constant": True,
                "inputs": [
                    {"name": "", "type": "address"},
                    {"name": "", "type": "address"}
                ],
                "name": "getPair",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }
        ]
        
        factory_contract = await self.eth_client.get_contract(factory, factory_abi)
        pair_address = await factory_contract.functions.getPair(
            token0_addr,
            token1_addr
        ).call()
        
        if pair_address == "0x0000000000000000000000000000000000000000":
            return None
            
        # Get reserves
        pair_abi = [
            {
                "constant": True,
                "inputs": [],
                "name": "getReserves",
                "outputs": [
                    {"name": "_reserve0", "type": "uint112"},
                    {"name": "_reserve1", "type": "uint112"},
                    {"name": "_blockTimestampLast", "type": "uint32"}
                ],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token0",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            },
            {
                "constant": True,
                "inputs": [],
                "name": "token1",
                "outputs": [{"name": "", "type": "address"}],
                "type": "function"
            }
        ]
        
        pair_contract = await self.eth_client.get_contract(pair_address, pair_abi)
        
        try:
            reserves = await pair_contract.functions.getReserves().call()
            actual_token0 = await pair_contract.functions.token0().call()
            actual_token1 = await pair_contract.functions.token1().call()
            
            return DexPool(
                address=pair_address,
                protocol="",  # Set by caller
                token0=actual_token0,
                token1=actual_token1,
                reserve0=reserves[0],
                reserve1=reserves[1],
                fee=0.003,  # 0.3% for V2
                liquidity=reserves[0] * reserves[1]
            )
        except Exception as e:
            logger.error(f"Error getting pool data: {e}")
            return None
            
    async def _get_v3_pools(
        self,
        token: str,
        quote_tokens: List[str]
    ) -> List[DexPool]:
        """Get Uniswap V3 pools"""
        
        pools = []
        fee_tiers = [500, 3000, 10000]  # 0.05%, 0.3%, 1%
        
        factory_abi = [
            {
                "inputs": [
                    {"name": "tokenA", "type": "address"},
                    {"name": "tokenB", "type": "address"},
                    {"name": "fee", "type": "uint24"}
                ],
                "name": "getPool",
                "outputs": [{"name": "pool", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        factory = await self.eth_client.get_contract(
            self.FACTORIES["uniswap_v3"],
            factory_abi
        )
        
        for quote_token in quote_tokens:
            for fee in fee_tiers:
                try:
                    pool_address = await factory.functions.getPool(
                        Web3.to_checksum_address(token),
                        Web3.to_checksum_address(quote_token),
                        fee
                    ).call()
                    
                    if pool_address != "0x0000000000000000000000000000000000000000":
                        # Get pool data
                        pool_data = await self._get_v3_pool_data(pool_address)
                        if pool_data:
                            pool_data.protocol = "uniswap_v3"
                            pools.append(pool_data)
                            
                except Exception as e:
                    logger.debug(f"V3 pool not found: {e}")
                    
        return pools
        
    async def _get_v3_pool_data(self, pool_address: str) -> Optional[DexPool]:
        """Get Uniswap V3 pool data"""
        
        pool_abi = [
            {
                "inputs": [],
                "name": "liquidity",
                "outputs": [{"name": "", "type": "uint128"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "slot0",
                "outputs": [
                    {"name": "sqrtPriceX96", "type": "uint160"},
                    {"name": "tick", "type": "int24"},
                    {"name": "observationIndex", "type": "uint16"},
                    {"name": "observationCardinality", "type": "uint16"},
                    {"name": "observationCardinalityNext", "type": "uint16"},
                    {"name": "feeProtocol", "type": "uint8"},
                    {"name": "unlocked", "type": "bool"}
                ],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "fee",
                "outputs": [{"name": "", "type": "uint24"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token0",
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            },
            {
                "inputs": [],
                "name": "token1",
                "outputs": [{"name": "", "type": "address"}],
                "stateMutability": "view",
                "type": "function"
            }
        ]
        
        try:
            pool = await self.eth_client.get_contract(pool_address, pool_abi)
            
            liquidity = await pool.functions.liquidity().call()
            slot0 = await pool.functions.slot0().call()
            fee = await pool.functions.fee().call()
            token0 = await pool.functions.token0().call()
            token1 = await pool.functions.token1().call()
            
            # Calculate approximate reserves from sqrtPriceX96
            sqrt_price = slot0[0]
            price = (sqrt_price / (2**96)) ** 2
            
            # This is simplified - actual calculation would need tick data
            reserve0 = int(liquidity / (price ** 0.5))
            reserve1 = int(liquidity * (price ** 0.5))
            
            return DexPool(
                address=pool_address,
                protocol="",
                token0=token0,
                token1=token1,
                reserve0=reserve0,
                reserve1=reserve1,
                fee=fee / 1000000,  # Convert to decimal
                liquidity=liquidity
            )
            
        except Exception as e:
            logger.error(f"Error getting V3 pool data: {e}")
            return None
            
    async def calculate_price_impact(
        self,
        pool: DexPool,
        amount_in: int,
        token_in: str
    ) -> float:
        """Calculate price impact of a swap"""
        
        if pool.protocol in ["uniswap_v2", "sushiswap"]:
            # Uniswap V2 formula
            is_token0 = pool.token0.lower() == token_in.lower()
            
            if is_token0:
                reserve_in = pool.reserve0
                reserve_out = pool.reserve1
            else:
                reserve_in = pool.reserve1
                reserve_out = pool.reserve0
                
            amount_in_with_fee = amount_in * (1000 - pool.fee * 1000)
            amount_out = (amount_in_with_fee * reserve_out) / (
                reserve_in * 1000 + amount_in_with_fee
            )
            
            # Price before
            price_before = reserve_out / reserve_in
            
            # Price after
            new_reserve_in = reserve_in + amount_in
            new_reserve_out = reserve_out - amount_out
            price_after = new_reserve_out / new_reserve_in
            
            # Price impact
            price_impact = abs(price_after - price_before) / price_before
            
            return price_impact
            
        elif pool.protocol == "uniswap_v3":
            # Simplified V3 calculation
            # Real calculation would need tick math
            total_liquidity = pool.reserve0 + pool.reserve1
            impact = amount_in / total_liquidity
            return impact * 2  # Rough approximation
            
        return 0.0
        
    async def find_best_swap_route(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        max_hops: int = 3,
        max_price_impact: float = 0.05
    ) -> Optional[SwapRoute]:
        """Find the best swap route across multiple DEXs"""
        
        # Direct paths
        direct_pools = await self._find_direct_pools(token_in, token_out)
        
        best_route = None
        best_output = 0
        
        for pool in direct_pools:
            output = await self._calculate_output(pool, token_in, amount_in)
            impact = await self.calculate_price_impact(pool, amount_in, token_in)
            
            if impact <= max_price_impact and output > best_output:
                best_output = output
                best_route = SwapRoute(
                    path=[token_in, token_out],
                    pools=[pool],
                    amount_in=amount_in,
                    amount_out=output,
                    price_impact=impact,
                    gas_estimate=150000
                )
                
        # Multi-hop paths
        if max_hops > 1:
            multi_hop_route = await self._find_multi_hop_route(
                token_in,
                token_out,
                amount_in,
                max_hops,
                max_price_impact
            )
            
            if multi_hop_route and multi_hop_route.amount_out > best_output:
                best_route = multi_hop_route
                
        return best_route
        
    async def _find_direct_pools(
        self,
        token0: str,
        token1: str
    ) -> List[DexPool]:
        """Find all direct pools between two tokens"""
        
        pools = []
        
        # Check all DEXs
        for dex in ["uniswap_v2", "sushiswap"]:
            pool = await self._get_v2_pool(
                token0,
                token1,
                self.FACTORIES[dex]
            )
            if pool:
                pool.protocol = dex
                pools.append(pool)
                
        # Check V3
        v3_pools = await self._get_v3_pools(token0, [token1])
        pools.extend(v3_pools)
        
        return pools
        
    async def _calculate_output(
        self,
        pool: DexPool,
        token_in: str,
        amount_in: int
    ) -> int:
        """Calculate output amount for a swap"""
        
        if pool.protocol in ["uniswap_v2", "sushiswap"]:
            is_token0 = pool.token0.lower() == token_in.lower()
            
            if is_token0:
                reserve_in = pool.reserve0
                reserve_out = pool.reserve1
            else:
                reserve_in = pool.reserve1
                reserve_out = pool.reserve0
                
            amount_in_with_fee = amount_in * (1000 - int(pool.fee * 1000))
            amount_out = (amount_in_with_fee * reserve_out) // (
                reserve_in * 1000 + amount_in_with_fee
            )
            
            return amount_out
            
        return 0
        
    async def _find_multi_hop_route(
        self,
        token_in: str,
        token_out: str,
        amount_in: int,
        max_hops: int,
        max_price_impact: float
    ) -> Optional[SwapRoute]:
        """Find multi-hop routes through intermediate tokens"""
        
        # Common intermediate tokens
        intermediates = [
            "0xC02aaA39b223FE8D0A0e5C4F27eAD9083C756Cc2",  # WETH
            "0xA0b86991c6218b36c1d19D4a2e9Eb0cE3606eB48",  # USDC
            "0xdAC17F958D2ee523a2206206994597C13D831ec7"   # USDT
        ]
        
        best_route = None
        best_output = 0
        
        for intermediate in intermediates:
            if intermediate == token_in or intermediate == token_out:
                continue
                
            # First hop
            pools1 = await self._find_direct_pools(token_in, intermediate)
            if not pools1:
                continue
                
            # Second hop
            pools2 = await self._find_direct_pools(intermediate, token_out)
            if not pools2:
                continue
                
            # Calculate best path through this intermediate
            for pool1 in pools1:
                intermediate_amount = await self._calculate_output(
                    pool1,
                    token_in,
                    amount_in
                )
                
                if intermediate_amount == 0:
                    continue
                    
                impact1 = await self.calculate_price_impact(
                    pool1,
                    amount_in,
                    token_in
                )
                
                if impact1 > max_price_impact:
                    continue
                    
                for pool2 in pools2:
                    final_amount = await self._calculate_output(
                        pool2,
                        intermediate,
                        intermediate_amount
                    )
                    
                    if final_amount == 0:
                        continue
                        
                    impact2 = await self.calculate_price_impact(
                        pool2,
                        intermediate_amount,
                        intermediate
                    )
                    
                    total_impact = impact1 + impact2
                    
                    if total_impact <= max_price_impact and final_amount > best_output:
                        best_output = final_amount
                        best_route = SwapRoute(
                            path=[token_in, intermediate, token_out],
                            pools=[pool1, pool2],
                            amount_in=amount_in,
                            amount_out=final_amount,
                            price_impact=total_impact,
                            gas_estimate=250000
                        )
                        
        return best_route