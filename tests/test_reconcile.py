"""
Unit tests for the reconciliation engine. These use small, hand-crafted
in-memory datasets (not the random synthetic generator) so every test
case is exact and reproducible.
"""

import csv
import os
import tempfile
import unittest

import sys
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from reconcile import reconcile, merchant_names_related, normalize_merchant


FIELDNAMES = ["transaction_id", "date", "amount", "merchant"]


def _write_csv(rows):
    fd, path = tempfile.mkstemp(suffix=".csv")
    with os.fdopen(fd, "w", newline="") as f:
        writer = csv.DictWriter(f, fieldnames=FIELDNAMES)
        writer.writeheader()
        writer.writerows(rows)
    return path


class TestReconcile(unittest.TestCase):

    def test_exact_match(self):
        row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Zomato"}
        internal_path = _write_csv([row])
        bank_path = _write_csv([row])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(len(result["mismatched"]), 0)
        self.assertEqual(len(result["exceptions"]), 0)
        self.assertEqual(result["match_rate"], 100.0)

    def test_amount_mismatch(self):
        internal_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Zomato"}
        bank_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "105.00", "merchant": "Zomato"}
        internal_path = _write_csv([internal_row])
        bank_path = _write_csv([bank_row])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["matched"]), 0)
        self.assertEqual(len(result["mismatched"]), 1)
        self.assertEqual(result["mismatched"][0]["type"], "AMOUNT_MISMATCH")

    def test_partial_refund_detected(self):
        internal_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "1000.00", "merchant": "Amazon"}
        bank_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "700.00", "merchant": "Amazon"}
        internal_path = _write_csv([internal_row])
        bank_path = _write_csv([bank_row])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["mismatched"]), 1)
        self.assertEqual(result["mismatched"][0]["type"], "LIKELY_PARTIAL_REFUND")

    def test_settlement_delay_still_counts_as_matched(self):
        internal_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Swiggy"}
        bank_row = {"transaction_id": "TXN1", "date": "2026-08-08", "amount": "100.00", "merchant": "Swiggy"}
        internal_path = _write_csv([internal_row])
        bank_path = _write_csv([bank_row])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["matched"]), 1)
        self.assertIn("note", result["matched"][0])
        self.assertEqual(len(result["mismatched"]), 0)

    def test_merchant_name_variant_still_matches(self):
        internal_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Zomato"}
        bank_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "ZOMATO*ORDER"}
        internal_path = _write_csv([internal_row])
        bank_path = _write_csv([bank_row])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["matched"]), 1)
        self.assertEqual(len(result["mismatched"]), 0)

    def test_missing_in_bank(self):
        internal_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Ola"}
        internal_path = _write_csv([internal_row])
        bank_path = _write_csv([])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["exceptions"]), 1)
        self.assertEqual(result["exceptions"][0]["type"], "MISSING_IN_BANK")

    def test_missing_in_internal(self):
        bank_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Uber"}
        internal_path = _write_csv([])
        bank_path = _write_csv([bank_row])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["exceptions"]), 1)
        self.assertEqual(result["exceptions"][0]["type"], "MISSING_IN_INTERNAL")

    def test_duplicate_in_bank(self):
        internal_row = {"transaction_id": "TXN1", "date": "2026-08-01", "amount": "100.00", "merchant": "Ola"}
        bank_path_rows = [internal_row, internal_row]
        internal_path = _write_csv([internal_row])
        bank_path = _write_csv(bank_path_rows)

        result = reconcile(internal_path, bank_path)

        self.assertEqual(len(result["exceptions"]), 1)
        self.assertEqual(result["exceptions"][0]["type"], "DUPLICATE_IN_BANK")

    def test_empty_inputs_give_zero_percent_not_a_crash(self):
        internal_path = _write_csv([])
        bank_path = _write_csv([])

        result = reconcile(internal_path, bank_path)

        self.assertEqual(result["total_considered"], 0)
        self.assertEqual(result["match_rate"], 0.0)


class TestMerchantNormalization(unittest.TestCase):

    def test_normalize_strips_punctuation_and_case(self):
        self.assertEqual(normalize_merchant("Zomato*Order"), "ZOMATOORDER")

    def test_related_names_detected(self):
        self.assertTrue(merchant_names_related("Zomato", "ZOMATO*ORDER"))
        self.assertTrue(merchant_names_related("Uber", "UBER INDIA"))

    def test_unrelated_names_rejected(self):
        self.assertFalse(merchant_names_related("Zomato", "Swiggy"))


if __name__ == "__main__":
    unittest.main()
