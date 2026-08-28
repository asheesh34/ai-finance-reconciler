"""
Runs the reconciliation agent against tests/eval_set.py - a small,
hand-labeled set of transaction pairs where a human decided the
correct answer in advance, independent of reconcile.py's own rules.

This is a genuine held-out evaluation: the labels were not generated
by the system being tested, so a high score here is a real accuracy
claim, not the system grading itself.

Reports overall accuracy plus per-label precision and recall, and
prints every case the agent got wrong so the mistakes are visible,
not just the summary number.

Usage:
    export AI_API_KEY=your_key_here
    python3 tests/eval_agent.py
"""

import os
import sys
from collections import defaultdict

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import classify_pair, VALID_LABELS
from eval_set import EVAL_CASES


def run_evaluation():
    results = []

    for case in EVAL_CASES:
        decision = classify_pair(case["internal"], case["bank"])
        predicted = decision["label"]
        correct = predicted == case["true_label"]
        results.append({
            "id": case["id"],
            "true_label": case["true_label"],
            "predicted_label": predicted,
            "correct": correct,
            "confidence": decision["confidence"],
            "reasoning": decision["reasoning"],
            "human_note": case["human_note"],
        })

    return results


def compute_metrics(results):
    total = len(results)
    correct = sum(1 for r in results if r["correct"])
    accuracy = round(correct / total * 100, 1) if total else 0.0

    # Per-label precision/recall
    labels = sorted(set(r["true_label"] for r in results) | set(r["predicted_label"] for r in results))
    per_label = {}

    for label in labels:
        true_positives = sum(1 for r in results if r["true_label"] == label and r["predicted_label"] == label)
        predicted_positives = sum(1 for r in results if r["predicted_label"] == label)
        actual_positives = sum(1 for r in results if r["true_label"] == label)

        precision = round(true_positives / predicted_positives * 100, 1) if predicted_positives else None
        recall = round(true_positives / actual_positives * 100, 1) if actual_positives else None

        if actual_positives > 0 or predicted_positives > 0:
            per_label[label] = {
                "precision": precision,
                "recall": recall,
                "support": actual_positives,
            }

    return {
        "total": total,
        "correct": correct,
        "accuracy": accuracy,
        "per_label": per_label,
    }


def print_report(results, metrics):
    print("=" * 64)
    print("  AGENT EVALUATION — hand-labeled ground truth")
    print("=" * 64)
    print(f"Total cases: {metrics['total']}")
    print(f"Correct:     {metrics['correct']}")
    print(f"ACCURACY:    {metrics['accuracy']}%")
    print()
    print("Per-label precision / recall (support = how many true cases of that label)")
    print("-" * 64)
    for label, m in metrics["per_label"].items():
        p = f"{m['precision']}%" if m["precision"] is not None else "n/a"
        r = f"{m['recall']}%" if m["recall"] is not None else "n/a"
        print(f"  {label:<25} precision={p:<8} recall={r:<8} support={m['support']}")

    wrong = [r for r in results if not r["correct"]]
    if wrong:
        print()
        print(f"MISCLASSIFIED ({len(wrong)} of {metrics['total']})")
        print("-" * 64)
        for r in wrong:
            print(f"[{r['id']}] true={r['true_label']}  agent said={r['predicted_label']} (confidence {r['confidence']})")
            print(f"  human reasoning: {r['human_note']}")
            print(f"  agent reasoning: {r['reasoning']}\n")
    else:
        print("\nNo misclassifications - every case matched human judgment.")

    print("=" * 64)


if __name__ == "__main__":
    results = run_evaluation()
    metrics = compute_metrics(results)
    print_report(results, metrics)
