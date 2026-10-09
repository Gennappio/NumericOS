---
name: numerical-validation
description: Use when testing a numerical solver, scientific algorithm or simulation, including stability, convergence, discretization error, conservation, baseline comparisons or stochastic uncertainty.
---

# Numerical Validation

## Intent

Plan appropriate **problem-specific** validation before drawing conclusions about a numerical result. This M1 skill provides guidance. **Executable validators and scientific validity gates are introduced in NumericOS M3.** Never mark a run validated merely because this skill was loaded.

## Procedure

1. Identify governing equations/model, discretization, time integrator, initial/boundary conditions and chosen precision.
2. Select the right reference: analytic solution, manufactured solution, published benchmark, independent implementation, mesh/time refinement or invariant. Record reference limitations.
3. Specify what will be measured: residual *and* solution error (not interchangeable), conservation/positivity/physical invariants, constraint violation, stability, repeatability, runtime, RAM where applicable.
4. Write objective pass/fail/inconclusive rules and experimental parameter ranges. Derive stability criteria for the actual scheme; do not paste a universal CFL condition onto unrelated methods.
5. Control mesh, numerical parameters, inputs, seeds, hardware and solver configuration; when a required control changes, record a distinct experiment cohort.
6. For deterministic methods, evaluate refinement and numerical sensitivity where justified. For stochastic models, repeat independent seeds and report uncertainty; avoid single-run claims.
7. Diagnose failures separately: code errors, numerical instability, ill-conditioning, model inconsistency, data problems and infrastructure faults.
8. Provide an evidence report with actual measurements, test/validator identifiers and limitations. If runs were not executed, report a *validation plan*, not a pass.

## Output schema suggestion

```yaml
problem_class: "..."
reference: "..."
controlled_variables: ["..."]
validation_tests:
  - metric: "..."
    criterion: "..."
    source: "planned/not-run"
verdict: "NOT_EVALUATED"
```

## Constraints

- Numerical validity and executable correctness are different.
- A residual decreasing does not by itself guarantee solution accuracy.
- Runtime performance gains may not justify increased numerical error; use explicit multi-objective constraints.
- Use no invented precision, stability or significance thresholds.
