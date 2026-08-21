"""
Tests for the deterministic parts of agent.py - the label mapping and
JSON parsing - which don't require calling the actual API.
"""

import os
import sys
import unittest

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import _ground_truth_label, VALID_LABELS


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


if __name__ == "__main__":
    unittest.main()
