---
name: research-code-style
description: Use when writing or refactoring numerical, computational or exploratory scientific code; prefer a direct lean implementation, scientifically necessary checks and reproducible behavior over enterprise defensive boilerplate.
---

# Research Code Style

## Objective

Write **simple computational code** that makes the mathematical algorithm and data flow legible without sacrificing correctness, numerical safeguards or data protection.

## Rules

- Prefer small explicit functions, clear math variable names and readable loops/kernels to speculative abstractions.
- Do not insert catch-all exception handlers, silent fallback values, automatic data coercion, redundant retries or huge configuration frameworks merely “to be safe”.
- Fail quickly when an *actual* critical assumption is invalid (dimensions, numerical domain, required input availability, hard memory limits). For numerical routines preserve relevant checks for NaN/Inf, non-convergence, ill-conditioning or violated invariants when they are meaningful.
- Do not silently densify a sparse matrix, change precision, modify a boundary condition, random seed, metric or tolerance to make a run pass.
- Distinguish research prototype from public/production interfaces; enforce safe boundaries on files, shell execution, secrets, approval and untrusted inputs.
- Optimize only after a measured baseline. Maintain correctness/accuracy gates on optimized candidates.
- Make the **smallest reviewable code change** for each concrete hypothesis. Avoid incidental rewrites that introduce confounders.
- Record the exact source version, runtime inputs and environment required to reproduce the computation.
- Comments should explain *why* a numerical choice was made, not narrate obvious syntax.

## Before presenting the change

Briefly state the equation/algorithmic assumption affected, the minimal diff, the expected numerical or performance effect, the tests actually executed and any remaining uncertainty. Don't pretend unexecuted tests passed.
