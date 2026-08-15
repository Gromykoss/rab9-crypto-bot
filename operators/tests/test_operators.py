"""Юнит-тесты чистых enforced-операторов RAB9."""

import unittest

from operators import (
    Verdict,
    check_destination,
    check_mutation,
    check_safety,
    check_verifier,
)


class DestinationOperatorTest(unittest.TestCase):
    def test_allows_cryptanalyst(self):
        self.assertEqual(check_destination("-1004425561477").verdict, Verdict.ALLOW)

    def test_allows_sandbox(self):
        self.assertEqual(check_destination("-1003979753733").verdict, Verdict.ALLOW)

    def test_blocks_unknown_destination(self):
        self.assertEqual(check_destination("-999").verdict, Verdict.BLOCK)

    def test_allows_cryptanalyst_int(self):
        self.assertEqual(check_destination(-1004425561477).verdict, Verdict.ALLOW)

    def test_blocks_unknown_destination_int(self):
        self.assertEqual(check_destination(-999).verdict, Verdict.BLOCK)

    def test_blocks_empty_destination(self):
        self.assertEqual(check_destination(None).verdict, Verdict.BLOCK)


class SafetyOperatorTest(unittest.TestCase):
    def test_drops_honeypot_fail(self):
        self.assertEqual(check_safety("fail", "", "BUY").verdict, Verdict.DROP)

    def test_drops_honeypot_fail_case_insensitive(self):
        self.assertEqual(check_safety("FAIL", "", "").verdict, Verdict.DROP)

    def test_drops_honeypot_true_bool(self):
        self.assertEqual(check_safety(True, "", "").verdict, Verdict.DROP)

    def test_inconclusive_unknown_values(self):
        self.assertEqual(check_safety("unknown", "unknown", "BUY").verdict, Verdict.INCONCLUSIVE)

    def test_inconclusive_high_rugcheck(self):
        self.assertEqual(check_safety("", "high", "BUY").verdict, Verdict.INCONCLUSIVE)

    def test_drops_rugged_rugcheck(self):
        self.assertEqual(check_safety("", "rugged", "").verdict, Verdict.DROP)

    def test_dead_phase_inconclusive(self):
        self.assertEqual(check_safety("pass", "low", "DEAD").verdict, Verdict.INCONCLUSIVE)
        self.assertEqual(check_safety("", "", "dead").verdict, Verdict.INCONCLUSIVE)

    def test_allows_clean_data(self):
        self.assertEqual(check_safety("pass", "low", "BUY").verdict, Verdict.ALLOW)

    def test_allows_clean_data_with_empty_phase(self):
        self.assertEqual(check_safety("pass", "medium", "").verdict, Verdict.ALLOW)

    def test_inconclusive_without_data(self):
        self.assertEqual(check_safety("", "", "").verdict, Verdict.INCONCLUSIVE)


class VerdictGateOperatorTest(unittest.TestCase):
    def test_rejects_unavailable_verifier(self):
        self.assertEqual(check_verifier("PASS", available=False).verdict, Verdict.REJECT)

    def test_rejects_fail(self):
        self.assertEqual(check_verifier("FAIL", available=True).verdict, Verdict.REJECT)

    def test_allows_pass(self):
        self.assertEqual(check_verifier("PASS", available=True).verdict, Verdict.ALLOW)

    def test_holds_flag_without_fixed_text(self):
        self.assertEqual(check_verifier("FLAG", available=True).verdict, Verdict.HOLD)

    def test_holds_flag_with_blank_fixed_text(self):
        self.assertEqual(check_verifier("FLAG", available=True, fixed_text="   ").verdict, Verdict.HOLD)

    def test_allows_flag_with_fixed_text(self):
        self.assertEqual(check_verifier("FLAG", available=True, fixed_text="переписанный текст").verdict, Verdict.ALLOW)

    def test_rejects_unknown_verdict(self):
        self.assertEqual(check_verifier("BOGUS", available=True).verdict, Verdict.REJECT)


class ConfigGuardOperatorTest(unittest.TestCase):
    def test_allows_non_mutating_action(self):
        self.assertEqual(check_mutation("read", None).verdict, Verdict.ALLOW)

    def test_holds_env_edit_without_token(self):
        self.assertEqual(check_mutation("env_edit", None).verdict, Verdict.HOLD)

    def test_allows_env_edit_with_token(self):
        self.assertEqual(check_mutation("env_edit", "tok123").verdict, Verdict.ALLOW)

    def test_holds_deploy_with_empty_token(self):
        self.assertEqual(check_mutation("deploy", "").verdict, Verdict.HOLD)

    def test_blocks_none_action(self):
        self.assertEqual(check_mutation(None, None).verdict, Verdict.BLOCK)

    def test_blocks_empty_action(self):
        self.assertEqual(check_mutation("", None).verdict, Verdict.BLOCK)

    def test_holds_env_edit_with_blank_token(self):
        self.assertEqual(check_mutation("env_edit", " ").verdict, Verdict.HOLD)


if __name__ == "__main__":
    unittest.main()
