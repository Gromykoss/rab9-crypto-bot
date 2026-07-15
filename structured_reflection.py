"""Structured Reflection for RAB9 MoA signal verification.

Neil XBT structured handoffs pattern:
- Builder (Grok) → structured SignalAnalysis object (not free text)
- Judge (DeepSeek) → granular JudgeVerdict with per-check PASS/FAIL
- Manager → stop conditions (max 2 retries, overall PASS iff ALL checks PASS)
Key insight: "natural language handoffs drift by week 3, structured handoffs don't"

Maker: Grok (xAI) produces SignalAnalysis
Reviewer: DeepSeek produces JudgeVerdict
Max 2 retries on FAIL.
Autonomous module — called externally, no changes to rab9_bot.py.
Backward compatible: verify_signal() signature and ReflectionResult unchanged.
"""

import os
import json
import asyncio
from typing import Literal, Optional
from dataclasses import dataclass, field
from pydantic import BaseModel, Field, ValidationError
import httpx
from dotenv import load_dotenv

load_dotenv(os.path.join(os.path.dirname(__file__), ".env"))

XAI_API_KEY = os.getenv("XAI_API_KEY", "")
DEEPSEEK_API_KEY = os.getenv("DEEPSEEK_API_KEY", "") or os.getenv("OPENROUTER_API_KEY", "")


class ReflectionVerdict(BaseModel):
    status: Literal["pass", "fail"]
    issues: list[str] = Field(default_factory=list)
    next_action: str
    confidence: float = Field(ge=0.0, le=1.0)


# Neil XBT structured handoff models
class SignalAnalysis(BaseModel):
    """Builder (Grok) output: structured analysis instead of free text."""
    verdict: str
    risk_factors: list[str] = Field(default_factory=list)
    key_numbers: dict = Field(default_factory=dict)
    cabal_flags: list[str] = Field(default_factory=list)
    confidence: float = Field(ge=0.0, le=1.0)


class JudgeVerdict(BaseModel):
    """Judge (DeepSeek) output: granular per-check verdicts. Overall PASS only if ALL PASS."""
    number_accuracy: Literal["PASS", "FAIL"]
    verdict_consistency: Literal["PASS", "FAIL"]
    cabal_correctness: Literal["PASS", "FAIL"]
    synthesis_quality: Literal["PASS", "FAIL"]


@dataclass
class ReflectionResult:
    verdict: str  # "pass" | "fail"
    confidence: float
    attempts: int
    total_cost: float
    issues: list[str] = field(default_factory=list)
    routing_receipt: Optional[dict] = None


async def _call_grok(prompt: str, signal_data: dict) -> SignalAnalysis:
    """Builder: Grok via xAI API producing structured SignalAnalysis."""
    if not XAI_API_KEY:
        return SignalAnalysis(verdict="pass", risk_factors=[], key_numbers={}, cabal_flags=[], confidence=0.8)

    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "grok-4-latest",
        "messages": [
            {"role": "system", "content": "You are a crypto signal builder. Return ONLY valid JSON matching SignalAnalysis schema."},
            {"role": "user", "content": f"Signal: {json.dumps(signal_data)}\n\n{prompt}"},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        data = json.loads(content)
        return SignalAnalysis(**data)


async def _call_deepseek(analysis: SignalAnalysis, signal_data: dict) -> JudgeVerdict:
    """Judge: DeepSeek with Pydantic schema for granular JudgeVerdict."""
    if not DEEPSEEK_API_KEY:
        # Mock for tests / no-key env: all PASS
        return JudgeVerdict(number_accuracy="PASS", verdict_consistency="PASS", cabal_correctness="PASS", synthesis_quality="PASS")

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    system_prompt = (
        "You are a strict crypto signal judge. "
        "Return ONLY valid JSON matching JudgeVerdict schema with PASS/FAIL for each check. "
        "Overall PASS only if ALL four checks are PASS."
    )
    user_content = f"Signal: {json.dumps(signal_data)}\n\nAnalysis: {analysis.model_dump_json()}"

    payload = {
        "model": "deepseek-chat",
        "messages": [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_content},
        ],
        "temperature": 0.1,
        "max_tokens": 400,
        "response_format": {"type": "json_object"},
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"].strip()
        data = json.loads(content)
        return JudgeVerdict(**data)


async def verify_signal(signal_data: dict) -> ReflectionResult:
    """Main entrypoint. Builder (Grok structured) → Judge (DeepSeek granular) → Retry (max 2)."""
    attempts = 0
    max_retries = 2
    total_cost = 0.0
    issues: list[str] = []

    maker_prompt = "Provide structured analysis of this meme coin signal."

    while attempts <= max_retries:
        attempts += 1
        # Builder: Grok -> SignalAnalysis
        signal_analysis = await _call_grok(maker_prompt, signal_data)

        # Judge: DeepSeek -> JudgeVerdict (granular)
        judge_verdict = await _call_deepseek(signal_analysis, signal_data)

        all_pass = (
            judge_verdict.number_accuracy == "PASS" and
            judge_verdict.verdict_consistency == "PASS" and
            judge_verdict.cabal_correctness == "PASS" and
            judge_verdict.synthesis_quality == "PASS"
        )

        if all_pass:
            return ReflectionResult(
                verdict="pass",
                confidence=signal_analysis.confidence,
                attempts=attempts,
                total_cost=total_cost,
                issues=[],
                routing_receipt={"maker": "grok", "reviewer": "deepseek", "attempts": attempts, "pattern": "neil_xbt_structured"},
            )
        else:
            issues = [f"{k}:{v}" for k, v in judge_verdict.model_dump().items() if v == "FAIL"]
            if attempts > max_retries:
                break
            # Retry: feed structured issues back
            maker_prompt = f"Re-analyze fixing these failed checks: {issues}. Original signal: {json.dumps(signal_data)}"

    # Final fail after retries
    return ReflectionResult(
        verdict="fail",
        confidence=0.3,
        attempts=attempts,
        total_cost=total_cost,
        issues=issues,
        routing_receipt={"maker": "grok", "reviewer": "deepseek", "attempts": attempts, "final": "rejected", "pattern": "neil_xbt_structured"},
    )
