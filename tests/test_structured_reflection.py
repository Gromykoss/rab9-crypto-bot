"""Tests for structured_reflection with mock providers."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from structured_reflection import verify_signal, ReflectionResult, ReflectionVerdict


@pytest.mark.asyncio
async def test_pass_on_first_try():
    mock_verdict = ReflectionVerdict(status="pass", issues=[], next_action="accept", confidence=0.9)

    with patch("structured_reflection._call_grok", new_callable=AsyncMock) as mock_grok, \
         patch("structured_reflection._call_deepseek", new_callable=AsyncMock) as mock_ds:
        mock_grok.return_value = "Grok analysis"
        mock_ds.return_value = mock_verdict

        result = await verify_signal({"address": "0x123", "mc": 1000000})
        assert result.verdict == "pass"
        assert result.attempts == 1
        assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_retry_then_pass():
    fail_verdict = ReflectionVerdict(status="fail", issues=["low volume"], next_action="retry", confidence=0.4)
    pass_verdict = ReflectionVerdict(status="pass", issues=[], next_action="accept", confidence=0.85)

    with patch("structured_reflection._call_grok", new_callable=AsyncMock) as mock_grok, \
         patch("structured_reflection._call_deepseek", new_callable=AsyncMock) as mock_ds:
        mock_grok.return_value = "Grok analysis"
        mock_ds.side_effect = [fail_verdict, pass_verdict]

        result = await verify_signal({"address": "0xabc"})
        assert result.verdict == "pass"
        assert result.attempts == 2


@pytest.mark.asyncio
async def test_fail_after_max_retries():
    fail_verdict = ReflectionVerdict(status="fail", issues=["bad token"], next_action="reject", confidence=0.2)

    with patch("structured_reflection._call_grok", new_callable=AsyncMock) as mock_grok, \
         patch("structured_reflection._call_deepseek", new_callable=AsyncMock) as mock_ds:
        mock_grok.return_value = "Grok analysis"
        mock_ds.return_value = fail_verdict

        result = await verify_signal({"address": "0xdef"})
        assert result.verdict == "fail"
        assert result.attempts == 3  # initial + 2 retries
        assert "bad token" in result.issues
