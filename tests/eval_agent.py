"""
Runs the reconciliation agent against tests/eval_set.py - a small,
hand-labeled set of transaction pairs where a human decided the
correct answer in advance, independent of reconcile.py's own rules.

This is a genuine held-out evaluation: the labels were not generated
by the system being tested, so a high score here is a real accuracy
claim, not the system grading itself.

A note on sample size: with 18 cases and several label categories
represented by only 1-3 examples, per-label precision/recall here
are indicative, not statistically robust - a single case flips a
category from 0% to 100%. Treat these as a diagnostic signal, not
a rigorous benchmark. Expanding eval_set.py with more cases per
category is the natural next step (see README).

Reports overall accuracy, a separate deferral rate (cases the agent
declined to auto-resolve due to low confidence - correct, safe
behavior, not a mistake), and per-label precision/recall. Every
misclassified AND every deferred case is printed, so both kinds of
non-answers are visible, not just the summary number.

Usage:
    export AI_API_KEY=your_key_here
    python3 tests/eval_agent.py
"""

import os
import sys

sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "src"))

from agent import classify_pair
from eval_set import EVAL_CASES


def run_evaluation():
    results = []
    skipped = []

    for i, case in enumerate(EVAL_CASES, 1):
        print(f"  Evaluating {case['id']} ({i}/{len(EVAL_CASES)})...", flush=True)
        try:
            decision = classify_pair(case["internal"], case["bank"])
        except Exception as e:
            print(f"  Skipping {case['id']} after repeated failures: {e}", flush=True)
            skipped.append(case["id"])
            continue

        predicted = decision["label"]
        deferred = decision["deferred"]
        correct = (predicted == case["true_label"]) if not deferred else None
        results.append({
            "id": case["id"],
            "true_label": case["true_label"],
            "predicted_label": predicted,
            "raw_label": decision["raw_label"],
            "deferred": deferred,
            "correct": correct,
            "confidence": decision["confidence"],
            "reasoning": decision["reasoning"],
            "human_note": case["human_note"],
        })

    if skipped:
        print(f"\nNote: {len(skipped)} case(s) skipped due to persistent errors: {skipped}")
        print("Metrics below are computed over the remaining cases only.\n")

    return results


def compute_metrics(results):
    total = len(results)
    deferred_results = [r for r in results if r["deferred"]]
    auto_resolved = [r for r in results if not r["deferred"]]

    correct = sum(1 for r in auto_resolved if r["correct"])
    accuracy = round(correct / len(auto_resolved) * 100, 1) if auto_resolved else 0.0
    deferral_rate = round(len(deferred_results) / total * 100, 1) if total else 0.0

    # Per-label precision/recall - computed only over auto-resolved cases,
    # since a deferred case has no predicted label to score.
    labels = sorted(
        set(r["true_label"] for r in results)
        | set(r["predicted_label"] for r in auto_resolved)
    )
    per_label = {}

    for label in labels:
        true_positives = sum(1 for r in auto_resolved if r["true_label"] == label and r["predicted_label"] == label)
        predicted_positives = sum(1 for r in auto_resolved if r["predicted_label"] == label)
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
        "auto_resolved": len(auto_resolved),
        "deferred": len(deferred_results),
        "deferral_rate": deferral_rate,
        "correct": correct,
        "accuracy": accuracy,
        "per_label": per_label,
    }


def print_report(results, metrics):
    print("=" * 64)
    print("  AGENT EVALUATION — hand-labeled ground truth")
    print("=" * 64)
    print(f"Total cases:         {metrics['total']}")
    print(f"Deferred to human:   {metrics['deferred']}  ({metrics['deferral_rate']}%)")
    print(f"Auto-resolved:       {metrics['auto_resolved']}")
    print(f"Correct (of auto-resolved): {metrics['correct']}")
    print(f"ACCURACY (auto-resolved only): {metrics['accuracy']}%")
    print()
    print("Note: sample size is small (n=20) with 1-3 examples per label -")
    print("treat per-label numbers below as indicative, not statistically robust.")
    print()
    print("Per-label precision / recall (support = how many true cases of that label)")
    print("-" * 64)
    for label, m in metrics["per_label"].items():
        p = f"{m['precision']}%" if m["precision"] is not None else "n/a"
        r = f"{m['recall']}%" if m["recall"] is not None else "n/a"
        print(f"  {label:<25} precision={p:<8} recall={r:<8} support={m['support']}")

    wrong = [r for r in results if r["correct"] is False]
    if wrong:
        print()
        print(f"MISCLASSIFIED ({len(wrong)} of {metrics['auto_resolved']} auto-resolved)")
        print("-" * 64)
        for r in wrong:
            print(f"[{r['id']}] true={r['true_label']}  agent said={r['predicted_label']} (confidence {r['confidence']})")
            print(f"  human reasoning: {r['human_note']}")
            print(f"  agent reasoning: {r['reasoning']}\n")

    deferred = [r for r in results if r["deferred"]]
    if deferred:
        print()
        print(f"DEFERRED TO HUMAN ({len(deferred)} of {metrics['total']}) — not counted as wrong")
        print("-" * 64)
        for r in deferred:
            print(f"[{r['id']}] true={r['true_label']}  agent leaned toward={r['raw_label']} (confidence {r['confidence']})")
            print(f"  human reasoning: {r['human_note']}")
            print(f"  agent reasoning: {r['reasoning']}\n")

    if not wrong and not deferred:
        print("\nNo misclassifications or deferrals - every case both matched human")
        print("judgment and was resolved with sufficient confidence.")

    print("=" * 64)


if __name__ == "__main__":
    results = run_evaluation()
    metrics = compute_metrics(results)
    print_report(results, metrics)
