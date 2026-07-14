"""Structured Reflection for RAB9 MoA signal verification.

Pattern: UniGrok Execute-Review-Retry loop.
Maker: Grok (xAI)
Reviewer: DeepSeek (via api.deepseek.com or OpenRouter)
Max 2 retries on fail.
Autonomous module — called externally, no changes to rab9_bot.py.
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


@dataclass
class ReflectionResult:
    verdict: str  # "pass" | "fail"
    confidence: float
    attempts: int
    total_cost: float
    issues: list[str] = field(default_factory=list)
    routing_receipt: Optional[dict] = None


async def _call_grok(prompt: str, signal_data: dict) -> str:
    """Maker: Grok via xAI API."""
    if not XAI_API_KEY:
        return json.dumps({"analysis": "MOCK: Grok analysis placeholder", "verdict": "pass"})

    url = "https://api.x.ai/v1/chat/completions"
    headers = {"Authorization": f"Bearer {XAI_API_KEY}", "Content-Type": "application/json"}
    payload = {
        "model": "grok-4-latest",
        "messages": [
            {"role": "system", "content": "You are a crypto signal maker. Analyze the signal and propose verdict."},
            {"role": "user", "content": f"Signal: {json.dumps(signal_data)}\n\n{prompt}"},
        ],
        "temperature": 0.2,
        "max_tokens": 800,
    }
    async with httpx.AsyncClient(timeout=30.0) as client:
        r = await client.post(url, headers=headers, json=payload)
        r.raise_for_status()
        content = r.json()["choices"][0]["message"]["content"]
        return content


async def _call_deepseek(prompt: str, previous_issues: list[str] = None) -> ReflectionVerdict:
    """Reviewer: DeepSeek with Pydantic schema."""
    if not DEEPSEEK_API_KEY:
        # Mock for tests / no-key env
        return ReflectionVerdict(status="pass", issues=[], next_action="accept", confidence=0.85)

    url = "https://api.deepseek.com/chat/completions"
    headers = {"Authorization": f"Bearer {DEEPSEEK_API_KEY}", "Content-Type": "application/json"}
    system_prompt = (
        "You are a strict crypto signal reviewer. "
        "Return ONLY valid JSON matching the schema: "
        '{"status": "pass|fail", "issues": [...], "next_action": "...", "confidence": 0.0-1.0}'
    )
    user_content = prompt
    if previous_issues:
        user_content += f"\n\nPrevious issues to address: {previous_issues}"

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
        return ReflectionVerdict(**data)


async def verify_signal(signal_data: dict) -> ReflectionResult:
    """Main entrypoint. Execute (Grok) → Review (DeepSeek) → Retry (max 2)."""
    attempts = 0
    max_retries = 2
    total_cost = 0.0  # placeholder; real tracking would use token counts
    issues: list[str] = []

    maker_prompt = "Provide detailed analysis of this meme coin signal. Suggest pass/fail."

    while attempts <= max_retries:
        attempts += 1
        # Execute: Grok maker
        grok_output = await _call_grok(maker_prompt, signal_data)

        # Review: DeepSeek reviewer
        review_prompt = f"Review this Grok analysis for the signal {json.dumps(signal_data)}:\n{grok_output}"
        prev_issues = issues if attempts > 1 else []
        verdict = await _call_deepseek(review_prompt, prev_issues)

        if verdict.status == "pass":
            return ReflectionResult(
                verdict="pass",
                confidence=verdict.confidence,
                attempts=attempts,
                total_cost=total_cost,
                issues=[],
                routing_receipt={"maker": "grok", "reviewer": "deepseek", "attempts": attempts},
            )
        else:
            issues = verdict.issues
            if attempts > max_retries:
                break
            # Retry: feed issues back to Grok
            maker_prompt = f"Re-analyze fixing these issues: {issues}. Original signal: {json.dumps(signal_data)}"

    # Final fail after retries
    return ReflectionResult(
        verdict="fail",
        confidence=verdict.confidence if 'verdict' in locals() else 0.3,
        attempts=attempts,
        total_cost=total_cost,
        issues=issues,
        routing_receipt={"maker": "grok", "reviewer": "deepseek", "attempts": attempts, "final": "rejected"},
    )
