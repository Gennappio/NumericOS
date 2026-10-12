# Sparse conjugate gradient in C++

A fixed sparse benchmark with a known solution: conjugate gradient (CG) on the 5-point Poisson
matrix of an `n x n` grid, stored in CSR. The matrix is symmetric positive definite. The
right-hand side is `b = A x*` for a known `x*`, so the **error** of the computed solution can
be measured, not only its residual.

## What it shows

A decreasing residual does not by itself say that the solution is accurate.

- The residual that CG maintains by recurrence (`residual_rel`) keeps decreasing even after the
  residual of the actual iterate, `||b - A x|| / ||b||`, has stalled at the level the working
  precision allows.
- Even the true residual is not the error: for an ill-conditioned matrix the error can be
  larger by up to the condition number.

`--precision single` runs the same algorithm in `float`. Both precisions stop when their
recurrence residual is below the tolerance and exit with code 0. What they achieved is then
measured in double precision and reported as `true_residual_rel` and `error_rel`. On the
development machine, `n = 128`, tolerance 1e-10:

| precision | iterations | residual it reports | true residual | error |
| --- | --- | --- | --- | --- |
| double | 262 | below 1e-10 | 9.3e-11 | 2.8e-9 |
| single | 339 | below 1e-10 | 1.8e-6 | 7.2e-6 |

The single-precision run says it converged, and it did not reach what it says. Its process
ended normally all the same: only a check of the measured error against an explicit criterion
can tell the two runs apart.

Timings depend on the machine and are measured, not assumed: `solve_seconds` is the solve
alone, timed by the program; `wall_time` is the whole process, measured by the supervisor. The
two differ by far more than the matrix assembly: on macOS the first start of a freshly built
binary alone took about 0.3 s on the development machine, ten times the solve. A comparison of
kernels uses the time the program measures around the kernel.

## Files

- `cg.cpp`: matrix assembly, CG, and the measurement of what was achieved.
- `numericos_metrics.hpp`: one-header instrumentation, `numericos::metric(name, value, step)`.
  Copy it next to your own solver.
- `experiment.yaml`: the experiment contract. It builds the program with
  `c++ -O2 -std=c++17` as part of the run and records `c++ --version` with it.

## Running it

Alone:

```bash
c++ -O2 -std=c++17 -o cg cg.cpp
./cg --n 128 --tol 1e-10 --max-iter 2000 --precision double
```

Under NumericOS, from the top of this repository, with `make api` and `make worker` running:

```bash
numericos experiment run examples/sparse-cg-cpp/experiment.yaml -p PROJECT_ID -P precision=double
numericos experiment run examples/sparse-cg-cpp/experiment.yaml -p PROJECT_ID -P precision=single
numericos run metrics RUN_ID
```

The run record identifies the binary that ran by its SHA-256 and keeps the compiler's version.
