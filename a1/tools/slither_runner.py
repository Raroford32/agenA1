import subprocess
import json
import tempfile
import os
from typing import Dict, Any, List, Optional
from pathlib import Path
import asyncio
import logging

logger = logging.getLogger(__name__)


class SlitherRunner:
    """Slither static analysis integration"""
    
    def __init__(self, slither_path: str = "slither"):
        self.slither_path = slither_path
        self.temp_dir = None
        
    async def __aenter__(self):
        self.temp_dir = tempfile.mkdtemp()
        return self
        
    async def __aexit__(self, exc_type, exc_val, exc_tb):
        if self.temp_dir and os.path.exists(self.temp_dir):
            import shutil
            shutil.rmtree(self.temp_dir)
            
    async def analyze_source_code(
        self,
        source_code: str,
        contract_name: str,
        solc_version: str = "0.8.19",
        optimization: bool = True,
        runs: int = 200
    ) -> Dict[str, Any]:
        """Run Slither analysis on source code"""
        
        # Write source code to temporary file
        source_file = os.path.join(self.temp_dir, f"{contract_name}.sol")
        with open(source_file, "w") as f:
            f.write(source_code)
            
        # Prepare Slither command
        cmd = [
            self.slither_path,
            source_file,
            "--json", "-",
            "--solc-solcs-select", solc_version,
            "--checklist",
            "--print", "human-summary,inheritance-graph,call-graph",
            "--exclude-informational",
            "--exclude-low"
        ]
        
        if optimization:
            cmd.extend(["--solc-args", f"--optimize --optimize-runs {runs}"])
            
        try:
            # Run Slither asynchronously
            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            
            stdout, stderr = await process.communicate()
            
            if process.returncode != 0:
                logger.error(f"Slither error: {stderr.decode()}")
                return {
                    "success": False,
                    "error": stderr.decode(),
                    "detectors": []
                }
                
            # Parse JSON output
            result = json.loads(stdout.decode())
            
            return {
                "success": True,
                "detectors": self._parse_detectors(result),
                "summary": self._generate_summary(result),
                "raw_output": result
            }
            
        except Exception as e:
            logger.error(f"Slither execution failed: {e}")
            return {
                "success": False,
                "error": str(e),
                "detectors": []
            }
            
    def _parse_detectors(self, slither_output: Dict[str, Any]) -> List[Dict[str, Any]]:
        """Parse Slither detector results"""
        
        detectors = []
        
        for detector in slither_output.get("results", {}).get("detectors", []):
            parsed = {
                "check": detector.get("check", ""),
                "impact": detector.get("impact", ""),
                "confidence": detector.get("confidence", ""),
                "description": detector.get("description", ""),
                "elements": []
            }
            
            # Parse affected elements
            for element in detector.get("elements", []):
                parsed["elements"].append({
                    "type": element.get("type", ""),
                    "name": element.get("name", ""),
                    "source_mapping": element.get("source_mapping", {}),
                    "additional_fields": element.get("additional_fields", {})
                })
                
            # Categorize by exploitability
            parsed["exploitable"] = self._is_exploitable(parsed)
            parsed["profit_potential"] = self._estimate_profit_potential(parsed)
            
            detectors.append(parsed)
            
        return detectors
        
    def _is_exploitable(self, detector: Dict[str, Any]) -> bool:
        """Determine if vulnerability is exploitable"""
        
        exploitable_checks = [
            "reentrancy-eth",
            "reentrancy-no-eth",
            "unchecked-transfer",
            "arbitrary-send",
            "uninitialized-state",
            "uninitialized-storage",
            "controlled-delegatecall",
            "delegatecall-loop",
            "arbitrary-send-eth",
            "suicidal",
            "unprotected-upgrade",
            "weak-prng",
            "incorrect-shift",
            "storage-array",
            "unchecked-lowlevel",
            "unchecked-send"
        ]
        
        return (
            detector["check"] in exploitable_checks and
            detector["impact"] in ["HIGH", "MEDIUM"] and
            detector["confidence"] in ["HIGH", "MEDIUM"]
        )
        
    def _estimate_profit_potential(self, detector: Dict[str, Any]) -> str:
        """Estimate profit potential of vulnerability"""
        
        high_profit_checks = [
            "reentrancy-eth",
            "arbitrary-send-eth",
            "suicidal",
            "unprotected-upgrade"
        ]
        
        medium_profit_checks = [
            "reentrancy-no-eth",
            "unchecked-transfer",
            "controlled-delegatecall"
        ]
        
        if detector["check"] in high_profit_checks:
            return "HIGH"
        elif detector["check"] in medium_profit_checks:
            return "MEDIUM"
        else:
            return "LOW"
            
    def _generate_summary(self, slither_output: Dict[str, Any]) -> Dict[str, Any]:
        """Generate analysis summary"""
        
        detectors = slither_output.get("results", {}).get("detectors", [])
        
        summary = {
            "total_issues": len(detectors),
            "high_impact": sum(1 for d in detectors if d.get("impact") == "HIGH"),
            "medium_impact": sum(1 for d in detectors if d.get("impact") == "MEDIUM"),
            "low_impact": sum(1 for d in detectors if d.get("impact") == "LOW"),
            "informational": sum(1 for d in detectors if d.get("impact") == "INFORMATIONAL"),
            "optimization_issues": sum(1 for d in detectors if "optimization" in d.get("check", "").lower()),
            "security_issues": sum(1 for d in detectors if d.get("impact") in ["HIGH", "MEDIUM"])
        }
        
        return summary
        
    async def analyze_bytecode(
        self,
        bytecode: str,
        contract_address: Optional[str] = None
    ) -> Dict[str, Any]:
        """Analyze deployed bytecode (limited functionality)"""
        
        # Slither has limited bytecode-only analysis
        # This would primarily identify:
        # - Compiler version
        # - Basic contract structure
        # - Some simple patterns
        
        return {
            "success": False,
            "error": "Bytecode-only analysis not fully implemented",
            "detectors": []
        }
        
    async def compare_contracts(
        self,
        source_code1: str,
        source_code2: str,
        contract_name: str = "Contract"
    ) -> Dict[str, Any]:
        """Compare two versions of a contract"""
        
        # Analyze both contracts
        result1 = await self.analyze_source_code(source_code1, f"{contract_name}_v1")
        result2 = await self.analyze_source_code(source_code2, f"{contract_name}_v2")
        
        if not result1["success"] or not result2["success"]:
            return {
                "success": False,
                "error": "Analysis failed for one or both contracts"
            }
            
        # Compare detectors
        detectors1 = {d["check"]: d for d in result1["detectors"]}
        detectors2 = {d["check"]: d for d in result2["detectors"]}
        
        added = [d for check, d in detectors2.items() if check not in detectors1]
        removed = [d for check, d in detectors1.items() if check not in detectors2]
        
        return {
            "success": True,
            "added_vulnerabilities": added,
            "removed_vulnerabilities": removed,
            "version1_summary": result1["summary"],
            "version2_summary": result2["summary"]
        }