import os
import json
import asyncio
import aiohttp
from typing import Dict, Any, Optional, List, Union
from dataclasses import dataclass
from datetime import datetime
import time
import logging
from tenacity import retry, stop_after_attempt, wait_exponential

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)


@dataclass
class GrokConfig:
    api_key: str
    model: str = "grok-4-0709"
    base_url: str = "https://openrouter.ai/api/v1"
    max_tokens: int = 4096
    temperature: float = 0.7
    top_p: float = 0.95
    frequency_penalty: float = 0.0
    presence_penalty: float = 0.0
    timeout: int = 300
    max_retries: int = 3
    

@dataclass
class GrokResponse:
    content: str
    model: str
    usage: Dict[str, int]
    created: int
    finish_reason: str
    raw_response: Dict[str, Any]


class GrokLLM:
    def __init__(self, config: GrokConfig):
        self.config = config
        self.session: Optional[aiohttp.ClientSession] = None
        self.headers = {
            "Authorization": f"Bearer {config.api_key}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/Raroford32/agenA1",
            "X-Title": "A1 Ethereum Exploit Generator"
        }
        
    async def __aenter__(self):
        self.session = aiohttp.ClientSession(
            timeout=aiohttp.ClientTimeout(total=self.config.timeout)
        )
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.session:
            await self.session.close()
            
    @retry(
        stop=stop_after_attempt(3),
        wait=wait_exponential(multiplier=1, min=4, max=60)
    )
    async def generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        max_tokens: Optional[int] = None,
        temperature: Optional[float] = None,
        response_format: Optional[Dict[str, Any]] = None,
        tools: Optional[List[Dict[str, Any]]] = None,
        tool_choice: Optional[Union[str, Dict[str, Any]]] = None
    ) -> GrokResponse:
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
            
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": f"x-ai/{self.config.model}",
            "messages": messages,
            "max_tokens": max_tokens or self.config.max_tokens,
            "temperature": temperature or self.config.temperature,
            "top_p": self.config.top_p,
            "frequency_penalty": self.config.frequency_penalty,
            "presence_penalty": self.config.presence_penalty,
            "stream": False
        }
        
        if response_format:
            payload["response_format"] = response_format
            
        if tools:
            payload["tools"] = tools
            if tool_choice:
                payload["tool_choice"] = tool_choice
                
        logger.info(f"Sending request to Grok-4-0709 with {len(prompt)} chars")
        start_time = time.time()
        
        try:
            async with self.session.post(
                f"{self.config.base_url}/chat/completions",
                headers=self.headers,
                json=payload
            ) as response:
                response.raise_for_status()
                data = await response.json()
                
                elapsed = time.time() - start_time
                logger.info(f"Grok response received in {elapsed:.2f}s")
                
                choice = data["choices"][0]
                message = choice["message"]
                
                return GrokResponse(
                    content=message.get("content", ""),
                    model=data["model"],
                    usage=data.get("usage", {}),
                    created=data["created"],
                    finish_reason=choice.get("finish_reason", ""),
                    raw_response=data
                )
                
        except aiohttp.ClientError as e:
            logger.error(f"Grok API error: {e}")
            raise
        except Exception as e:
            logger.error(f"Unexpected error: {e}")
            raise
            
    async def generate_with_tools(
        self,
        prompt: str,
        tools: List[Dict[str, Any]],
        system_prompt: Optional[str] = None,
        max_iterations: int = 10
    ) -> List[Dict[str, Any]]:
        results = []
        messages = []
        
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        for iteration in range(max_iterations):
            response = await self.generate(
                prompt=prompt,
                system_prompt=system_prompt,
                tools=tools,
                tool_choice="auto"
            )
            
            message = response.raw_response["choices"][0]["message"]
            messages.append(message)
            
            if not message.get("tool_calls"):
                break
                
            for tool_call in message["tool_calls"]:
                results.append({
                    "tool_call": tool_call,
                    "iteration": iteration
                })
                
                messages.append({
                    "role": "tool",
                    "tool_call_id": tool_call["id"],
                    "content": json.dumps({"status": "executed"})
                })
                
        return results
        
    async def analyze_contract(
        self,
        contract_address: str,
        contract_code: str,
        abi: Optional[List[Dict[str, Any]]] = None
    ) -> Dict[str, Any]:
        system_prompt = """You are Grok-4-0709, an advanced AI specialized in Ethereum smart contract analysis and exploit generation.
Your task is to analyze smart contracts for vulnerabilities and generate working exploits.
Focus on: reentrancy, integer overflow/underflow, access control, oracle manipulation, flash loan attacks, and MEV opportunities."""
        
        prompt = f"""Analyze this Ethereum smart contract at address {contract_address}:

Contract Code:
```solidity
{contract_code}
```

{"ABI: " + json.dumps(abi, indent=2) if abi else ""}

Provide a comprehensive vulnerability analysis including:
1. Identified vulnerabilities with severity ratings
2. Attack vectors and exploit strategies
3. Estimated potential profit
4. Implementation recommendations"""
        
        response = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.3,
            response_format={"type": "json_object"}
        )
        
        try:
            return json.loads(response.content)
        except json.JSONDecodeError:
            return {"error": "Failed to parse response", "raw": response.content}
            
    async def generate_exploit(
        self,
        vulnerability: Dict[str, Any],
        target_contract: str,
        fork_block: int
    ) -> str:
        system_prompt = """You are Grok-4-0709, generating production-ready Solidity exploit code.
Generate complete, working exploit contracts that can be deployed and executed on Ethereum mainnet forks."""
        
        prompt = f"""Generate a complete Solidity exploit contract for:

Target: {target_contract}
Fork Block: {fork_block}
Vulnerability: {json.dumps(vulnerability, indent=2)}

Requirements:
1. Complete, deployable Solidity code
2. Include all necessary imports and interfaces
3. Implement flashloan if needed
4. Handle all edge cases and reverts
5. Optimize for gas efficiency
6. Include profit extraction logic"""
        
        response = await self.generate(
            prompt=prompt,
            system_prompt=system_prompt,
            temperature=0.2,
            max_tokens=8192
        )
        
        return response.content
        
    async def stream_generate(
        self,
        prompt: str,
        system_prompt: Optional[str] = None,
        callback=None
    ):
        if not self.session:
            raise RuntimeError("Session not initialized. Use async context manager.")
            
        messages = []
        if system_prompt:
            messages.append({"role": "system", "content": system_prompt})
        messages.append({"role": "user", "content": prompt})
        
        payload = {
            "model": f"x-ai/{self.config.model}",
            "messages": messages,
            "max_tokens": self.config.max_tokens,
            "temperature": self.config.temperature,
            "stream": True
        }
        
        async with self.session.post(
            f"{self.config.base_url}/chat/completions",
            headers=self.headers,
            json=payload
        ) as response:
            response.raise_for_status()
            
            async for line in response.content:
                if line:
                    line = line.decode('utf-8').strip()
                    if line.startswith("data: "):
                        data = line[6:]
                        if data == "[DONE]":
                            break
                        try:
                            chunk = json.loads(data)
                            delta = chunk["choices"][0]["delta"]
                            if "content" in delta and callback:
                                await callback(delta["content"])
                        except json.JSONDecodeError:
                            continue


def create_grok_client(api_key: Optional[str] = None) -> GrokLLM:
    if not api_key:
        api_key = os.getenv("GROK_API_KEY") or os.getenv("OPENROUTER_API_KEY")
        
    if not api_key:
        raise ValueError("Grok API key not provided. Set GROK_API_KEY or OPENROUTER_API_KEY environment variable.")
        
    config = GrokConfig(api_key=api_key)
    return GrokLLM(config)