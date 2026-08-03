"""Unit-тесты T-134 multi-LLM fallback: primary → fallback → template.

Мок отказа обоих LLM → template на live-данных (не пустая строка, не сырой error).
"""
from __future__ import annotations

import os
import sys
import unittest
from unittest.mock import patch

# rab9 root on path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from token_intel import (  # noqa: E402
    _is_llm_error,
    _resolve_llm_order,
    ask_llm,
    ask_llm_with_template,
)
from msf_template import build_template_card  # noqa: E402
from meme_score import anti_rug_penalty  # noqa: E402


class TestIsLlmError(unittest.TestCase):
    def test_empty(self):
        self.assertTrue(_is_llm_error("", "grok"))
        self.assertTrue(_is_llm_error("   ", "deepseek"))

    def test_openrouter_key_hole(self):
        """Дыра: раньше msf_analysis принимал это за success."""
        self.assertTrue(_is_llm_error("OpenRouter API key не найден", "deepseek"))

    def test_grok_errors(self):
        self.assertTrue(_is_llm_error("Grok API key не найден в .env", "grok"))
        self.assertTrue(_is_llm_error("Grok API error: 429 | rate limit", "grok"))
        self.assertTrue(_is_llm_error("Grok request failed: timeout", "grok"))

    def test_deepseek_errors(self):
        self.assertTrue(_is_llm_error("DeepSeek API error: 500", "deepseek"))
        self.assertTrue(_is_llm_error("DeepSeek request failed: conn", "deepseek"))

    def test_real_analysis_ok(self):
        self.assertFalse(
            _is_llm_error(
                "Verdict: WATCH. Liq/MC 8%, buy pressure ok.",
                "grok",
            )
        )
        self.assertFalse(
            _is_llm_error(
                "Токен выглядит спекулятивно. B/S 1.2x.",
                "deepseek",
            )
        )


class TestResolveOrder(unittest.TestCase):
    def test_default_deepseek_first(self):
        with patch.dict(os.environ, {"RAB9_LLM": "deepseek"}, clear=False):
            self.assertEqual(_resolve_llm_order(None), ["deepseek", "grok"])

    def test_grok_primary(self):
        self.assertEqual(_resolve_llm_order("grok"), ["grok", "deepseek"])

    def test_hy3_maps_to_deepseek(self):
        self.assertEqual(_resolve_llm_order("hy3"), ["deepseek", "grok"])


class TestAskLlmChain(unittest.TestCase):
    @patch("token_intel.ask_deepseek", return_value="OpenRouter API key не найден")
    @patch("token_intel.ask_grok", return_value="Grok API key не найден в .env")
    def test_both_fail_returns_empty(self, _g, _d):
        with patch.dict(os.environ, {"RAB9_LLM": "deepseek"}, clear=False):
            self.assertEqual(ask_llm("test prompt"), "")

    @patch("token_intel.ask_deepseek", return_value="OpenRouter API key не найден")
    @patch("token_intel.ask_grok", return_value="Хороший mid-cap, WATCH.")
    def test_fallback_to_grok(self, _g, _d):
        with patch.dict(os.environ, {"RAB9_LLM": "deepseek"}, clear=False):
            out = ask_llm("test prompt")
            self.assertEqual(out, "Хороший mid-cap, WATCH.")

    @patch("token_intel.ask_deepseek", return_value="DeepSeek: solid setup.")
    @patch("token_intel.ask_grok", return_value="should not call if primary ok")
    def test_primary_deepseek_success(self, mock_g, _d):
        with patch.dict(os.environ, {"RAB9_LLM": "deepseek"}, clear=False):
            out = ask_llm("test")
            self.assertEqual(out, "DeepSeek: solid setup.")
            mock_g.assert_not_called()


class TestAskLlmWithTemplate(unittest.TestCase):
    @patch("token_intel.ask_deepseek", return_value="DeepSeek request failed: x")
    @patch("token_intel.ask_grok", return_value="Grok request failed: y")
    def test_both_fail_uses_template(self, _g, _d):
        with patch.dict(os.environ, {"RAB9_LLM": "grok"}, clear=False):
            text, src = ask_llm_with_template(
                "analyze",
                template_kwargs={
                    "token_name": "BURNIE",
                    "address": "CGEDT9QZDvvH5GmVkWJH2BXiMJqMJySC9ihWyr7Spump",
                    "score": {"score": 82, "max": 115, "tier": "SOLID"},
                    "liq": 120_000,
                    "vol": 500_000,
                    "mc": 5_000_000,
                    "rugcheck": {"level": "low"},
                    "buy_ratio": 1.4,
                },
            )
        self.assertEqual(src, "template")
        self.assertIn("BURNIE", text)
        self.assertIn("82", text)
        self.assertIn("template fallback", text.lower())
        # не «пустая строка» и не сырой API error
        self.assertFalse(text.startswith("Grok"))
        self.assertFalse(text.startswith("DeepSeek"))
        self.assertFalse(text.startswith("OpenRouter"))

    @patch("token_intel.ask_deepseek", return_value="")
    @patch("token_intel.ask_grok", return_value="")
    def test_both_fail_live_fallback_text(self, _g, _d):
        text, src = ask_llm_with_template(
            "p",
            live_fallback_text="🧭 Decision Layer\nMC: $5M\nLiq: $100K",
        )
        self.assertEqual(src, "live")
        self.assertIn("Decision Layer", text)
        self.assertIn("$5M", text)


class TestTemplateCardLiveOnly(unittest.TestCase):
    def test_build_template_no_invent(self):
        card = build_template_card(
            token_name="TEST",
            address="So11111111111111111111111111111111111111112",
            score={"score": 72, "max": 100, "tier": "SOLID"},
            liq=50_000,
            vol=200_000,
            mc=5_000_000,
            rugcheck={"level": "low"},
        )
        self.assertIn("TEST", card)
        self.assertIn("72", card)
        self.assertIn("dexscreener.com", card)


class TestAntiRugPenalty(unittest.TestCase):
    def test_unavailable_skip(self):
        """Нет данных → 0 penalty, не штрафует."""
        pen, notes = anti_rug_penalty({}, {})
        self.assertEqual(pen, 0)

    def test_low_buy_ratio_penalizes(self):
        market = {
            "txns": {"h1": {"buys": 30, "sells": 70}},  # 30% buys
            "liquidity": {"usd": 50_000},
            "marketCap": 1_000_000,
        }
        pen, notes = anti_rug_penalty({}, market)
        self.assertGreaterEqual(pen, 3)
        self.assertTrue(any("buy_ratio" in n for n in notes))

    def test_thin_liq_penalizes(self):
        market = {"liquidity": {"usd": 100}}  # << 5 SOL
        pen, notes = anti_rug_penalty({}, market)
        self.assertGreaterEqual(pen, 5)
        self.assertTrue(any("liq" in n for n in notes))

    def test_established_high_mcap_no_sniper_penalty(self):
        """BURNIE-like: high mcap + age >> 6h → max_mcap не штрафует."""
        market = {
            "marketCap": 5_000_000,
            "liquidity": {"usd": 200_000},
            "txns": {"h1": {"buys": 100, "sells": 80}},
            "pairCreatedAt": 1_700_000_000_000,  # old ms timestamp
        }
        # age from pairCreatedAt will be large
        pen, notes = anti_rug_penalty({}, market)
        self.assertFalse(any("sniper mcap" in n for n in notes))


if __name__ == "__main__":
    unittest.main()
