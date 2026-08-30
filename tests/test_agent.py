"""
Tests for the deterministic parts of agent.py - the label mapping and
JSON parsing - which don't require calling the actual API.
"""

import os
import sys
import unittest
from unittest.mock import patch
import json as _json

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import _ground_truth_label, VALID_LABELS, CONFIDENCE_THRESHOLD, classify_pair


class TestGroundTruthMapping(unittest.TestCase):

    def test_matched_maps_to_match(self):
        self.assertEqual(_ground_truth_label("anything", has_matched=True), "MATCH")

    def test_amount_mismatch_maps_correctly(self):
        self.assertEqual(_ground_truth_label("AMOUNT_MISMATCH", has_matched=False), "AMOUNT_MISMATCH")

    def test_partial_refund_maps_correctly(self):
        self.assertEqual(_ground_truth_label("LIKELY_PARTIAL_REFUND", has_matched=False), "LIKELY_PARTIAL_REFUND")

    def test_unknown_type_falls_back_to_unresolved(self):
        self.assertEqual(_ground_truth_label("SOMETHING_NEW", has_matched=False), "UNRESOLVED")

    def test_all_mapped_labels_are_valid(self):
        for deterministic_type in ["AMOUNT_MISMATCH", "LIKELY_PARTIAL_REFUND",
                                    "MERCHANT_NAME_MISMATCH", "MISSING_IN_BANK",
                                    "MISSING_IN_INTERNAL", "DUPLICATE_IN_BANK"]:
            label = _ground_truth_label(deterministic_type, has_matched=False)
            self.assertIn(label, VALID_LABELS)


class TestConfidenceDeferral(unittest.TestCase):
    """
    Tests the human-review deferral logic directly, without calling the
    live API - classify_pair's post-processing is deterministic once you
    have a (raw_label, confidence) pair, so we test that logic in isolation
    by re-implementing the same threshold check the real function applies.
    """

    def test_needs_human_review_is_a_valid_label(self):
        self.assertIn("NEEDS_HUMAN_REVIEW", VALID_LABELS)

    def test_low_confidence_defers(self):
        confidence = CONFIDENCE_THRESHOLD - 0.01
        deferred = confidence < CONFIDENCE_THRESHOLD
        self.assertTrue(deferred)

    def test_high_confidence_does_not_defer(self):
        confidence = CONFIDENCE_THRESHOLD + 0.01
        deferred = confidence < CONFIDENCE_THRESHOLD
        self.assertFalse(deferred)

    def test_threshold_is_reasonable(self):
        # Sanity check the threshold is in a sensible range - not 0 (which
        # would defer nothing) and not 1 (which would defer everything).
        self.assertGreater(CONFIDENCE_THRESHOLD, 0.0)
        self.assertLess(CONFIDENCE_THRESHOLD, 1.0)


class TestClassifyPairDeferralEndToEnd(unittest.TestCase):
    """
    Exercises the actual classify_pair() production code path with
    call_llm mocked, rather than re-testing the threshold comparison
    in isolation. This is the real regression guard for the deferral
    behavior described in the README.
    """

    SAMPLE_INTERNAL = {"transaction_id": "T1", "date": "2026-08-01", "amount": "100.00", "merchant": "Test"}
    SAMPLE_BANK = {"transaction_id": "T1", "date": "2026-08-01", "amount": "95.00", "merchant": "Test"}

    @patch("agent.call_llm")
    def test_low_confidence_response_is_overridden_to_needs_human_review(self, mock_call_llm):
        mock_call_llm.return_value = _json.dumps({
            "label": "AMOUNT_MISMATCH",
            "confidence": max(CONFIDENCE_THRESHOLD - 0.1, 0.0),
            "reasoning": "test reasoning",
        })

        decision = classify_pair(self.SAMPLE_INTERNAL, self.SAMPLE_BANK)

        self.assertEqual(decision["label"], "NEEDS_HUMAN_REVIEW")
        self.assertTrue(decision["deferred"])
        # The model's original lean must still be exposed for a human
        # reviewer, even though it wasn't acted on automatically.
        self.assertEqual(decision["raw_label"], "AMOUNT_MISMATCH")

    @patch("agent.call_llm")
    def test_high_confidence_response_is_not_deferred(self, mock_call_llm):
        mock_call_llm.return_value = _json.dumps({
            "label": "MATCH",
            "confidence": min(CONFIDENCE_THRESHOLD + 0.2, 1.0),
            "reasoning": "test reasoning",
        })

        decision = classify_pair(self.SAMPLE_INTERNAL, self.SAMPLE_BANK)

        self.assertEqual(decision["label"], "MATCH")
        self.assertFalse(decision["deferred"])
        self.assertEqual(decision["raw_label"], "MATCH")

    @patch("agent.call_llm")
    def test_prompt_never_contains_ground_truth_fields(self, mock_call_llm):
        """
        classify_pair must reason from raw record data only. If a
        deterministic ground-truth label ever leaked into the prompt,
        the agent's "independent judgment" claim would be false.
        """
        mock_call_llm.return_value = _json.dumps({
            "label": "MATCH", "confidence": 0.9, "reasoning": "test",
        })

        classify_pair(self.SAMPLE_INTERNAL, self.SAMPLE_BANK)

        sent_prompt = mock_call_llm.call_args[0][0]
        self.assertNotIn("_ground_truth", sent_prompt)
        self.assertNotIn("ground_truth", sent_prompt.lower())
        self.assertNotIn("true_label", sent_prompt)


if __name__ == "__main__":
    unittest.main()
