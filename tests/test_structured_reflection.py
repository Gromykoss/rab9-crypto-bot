"""Tests for structured_reflection with mock providers."""

import pytest
import asyncio
from unittest.mock import AsyncMock, patch
from structured_reflection import verify_signal, ReflectionResult, ReflectionVerdict, SignalAnalysis, JudgeVerdict


def PASS_JUDGE():
    return JudgeVerdict(number_accuracy="PASS", verdict_consistency="PASS", cabal_correctness="PASS", synthesis_quality="PASS")


def FAIL_JUDGE():
    return JudgeVerdict(number_accuracy="FAIL", verdict_consistency="FAIL", cabal_correctness="FAIL", synthesis_quality="FAIL")


@pytest.mark.asyncio
async def test_pass_on_first_try():
    mock_verdict = PASS_JUDGE()

    with patch("structured_reflection._call_grok", new_callable=AsyncMock) as mock_grok, \
         patch("structured_reflection._call_deepseek", new_callable=AsyncMock) as mock_ds:
        mock_grok.return_value = SignalAnalysis(verdict="pass", risk_factors=[], key_numbers={}, cabal_flags=[], confidence=0.9)
        mock_ds.return_value = mock_verdict

        result = await verify_signal({"address": "0x123", "mc": 1000000})
        assert result.verdict == "pass"
        assert result.attempts == 1
        assert result.confidence == 0.9


@pytest.mark.asyncio
async def test_retry_then_pass():
    fail_verdict = FAIL_JUDGE()
    pass_verdict = PASS_JUDGE()

    with patch("structured_reflection._call_grok", new_callable=AsyncMock) as mock_grok, \
         patch("structured_reflection._call_deepseek", new_callable=AsyncMock) as mock_ds:
        mock_grok.return_value = SignalAnalysis(verdict="retry", risk_factors=[], key_numbers={}, cabal_flags=[], confidence=0.85)
        mock_ds.side_effect = [fail_verdict, pass_verdict]

        result = await verify_signal({"address": "0xabc"})
        assert result.verdict == "pass"
        assert result.attempts == 2


@pytest.mark.asyncio
async def test_fail_after_max_retries():
    fail_verdict = FAIL_JUDGE()

    with patch("structured_reflection._call_grok", new_callable=AsyncMock) as mock_grok, \
         patch("structured_reflection._call_deepseek", new_callable=AsyncMock) as mock_ds:
        mock_grok.return_value = SignalAnalysis(verdict="reject", risk_factors=[], key_numbers={}, cabal_flags=[], confidence=0.2)
        mock_ds.return_value = fail_verdict

        result = await verify_signal({"address": "0xdef"})
        assert result.verdict == "fail"
        assert result.attempts == 3  # initial + 2 retries
        assert any("FAIL" in i for i in result.issues)
