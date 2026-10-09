---
name: scientific-method
description: Use when proposing, evaluating or iterating computational experiments, especially when a result must be supported by explicit hypotheses, predictions, controls and falsification criteria.
---

# Scientific Method for Computational Research

## Purpose

Make an experiment falsifiable and interpretable. This skill is **procedure guidance**, not a validated-run certificate. Use NumericOS Runtime to record/execute actual tests once available.

## Procedure

1. **Question:** state the scientific or computational question and define the baseline. Separate exploration from confirmatory evaluation.
2. **Hypothesis:** state the *specific* proposed causal or numerical explanation; for optimization, describe the expected mechanism (not just “faster”).
3. **Independent changes and controls:** identify what varies and what must remain identical (code revision, environment, solver settings, mesh/dataset, boundary/initial conditions, seed, hardware). Changes to controls create a new comparison cohort.
4. **Prediction:** write which observable metric(s) should move, direction and bounds/uncertainty where warranted.
5. **Falsification:** explicitly specify which outcome would contradict the hypothesis or prevent a conclusive verdict.
6. **Protocol:** define commands or procedures, metric source, reference/baseline, resource limits, repetitions and acceptance gates. Never invent thresholds without labeling them as proposed assumptions.
7. **Execution:** ask the NumericOS supervisor to execute, or transparently state that an experiment has not actually run.
8. **Evaluation:** separate measurement from interpretation. Report supported / contradicted / inconclusive outcomes with evidence refs and unresolved confounders.
9. **Next step:** choose a minimal discriminating follow-up, or stop if no evidence justifies more compute.

## Expected structured output

```yaml
hypothesis: "..."
independent_variable: "..."
controls: ["..."]
prediction: "..."
falsification_conditions: ["..."]
metrics: ["..."]
validation_plan: ["..."]
interpretation: "pending experiment"
```

## Rules

- A successful process exit or a plausible plot does **not** establish scientific correctness.
- Do not claim causality from a single benchmark or unreplicated stochastic result.
- Preserve negative/inconclusive evidence; never silently change thresholds after seeing results.
- Keep explanations concise and let users request targeted elaboration on a selected span.
