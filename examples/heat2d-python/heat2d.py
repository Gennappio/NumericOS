"""Explicit finite differences for the 2D heat equation, instrumented for NumericOS.

Problem: u_t = alpha (u_xx + u_yy) on the unit square, u = 0 on the boundary,
u(x, y, 0) = sin(pi x) sin(pi y). Exact solution: exp(-2 pi^2 alpha t) sin(pi x) sin(pi y).

Scheme: forward Euler in time, 5-point central differences in space (FTCS), on a uniform grid
with N intervals per side, h = 1/N, r = alpha dt / h^2:

    u[i][j] <- u[i][j] + r (u[i+1][j] + u[i-1][j] + u[i][j+1] + u[i][j-1] - 4 u[i][j])

README.md derives when this scheme is stable. In short: r <= 1/4 is sufficient on every grid.

Standard library only. Usage:
    python3 heat2d.py --dt 0.0002 --grid 32 --steps 600
"""

from __future__ import annotations

import argparse
import json
import math
import os


def emit_metric(name: str, value: float, step: int, time: float) -> None:
    """Print one numericos.metric.v1 record. Copy this function into your own solver.

    JSON has no NaN and no infinity, so a non-finite value is written as a word. The record is
    flushed at once: the supervisor then sees a value when it is produced, not when the
    program ends.
    """
    if math.isnan(value):
        shown: float | str = "nan"
    elif math.isinf(value):
        shown = "inf" if value > 0 else "-inf"
    else:
        shown = value
    record = {
        "schema": "numericos.metric.v1",
        "name": name,
        "value": shown,
        "step": step,
        "time": time,
    }
    print(json.dumps(record), flush=True)


def max_abs(field: list[list[float]]) -> float:
    """Largest absolute value. A NaN anywhere makes the result NaN: `max` would hide it."""
    worst = 0.0
    for row in field:
        for value in row:
            magnitude = abs(value)
            if magnitude != magnitude:
                return magnitude
            if magnitude > worst:
                worst = magnitude
    return worst


def l2_norm(field: list[list[float]], h: float, minus: list[list[float]] | None = None) -> float:
    """Discrete L2 norm, sqrt(h^2 sum f^2), of a grid function or of its difference to another."""
    total = 0.0
    for i, row in enumerate(field):
        other = minus[i] if minus is not None else None
        for j, value in enumerate(row):
            difference = value - other[j] if other is not None else value
            total += difference * difference
    return math.sqrt(total) * h


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument("--dt", type=float, required=True, help="time step")
    parser.add_argument("--grid", type=int, default=32, help="intervals per side (N)")
    parser.add_argument("--steps", type=int, default=600)
    parser.add_argument("--alpha", type=float, default=1.0, help="diffusivity")
    parser.add_argument("--report-every", type=int, default=10, help="steps between reports")
    arguments = parser.parse_args()

    n, dt, alpha = arguments.grid, arguments.dt, arguments.alpha
    h = 1.0 / n
    r = alpha * dt / (h * h)
    # The initial condition is one discrete sine mode, so the exact solution at the grid
    # points is this shape times exp(-2 pi^2 alpha t).
    shape = [
        [math.sin(math.pi * i * h) * math.sin(math.pi * j * h) for j in range(n + 1)]
        for i in range(n + 1)
    ]
    u = [row[:] for row in shape]
    print(f"heat2d: grid {n}x{n}, h={h:.6e}, dt={dt:.6e}, alpha={alpha}, r={r:.6f}", flush=True)

    def report(step: int) -> None:
        time = step * dt
        decay = math.exp(-2.0 * math.pi**2 * alpha * time)
        exact = [[decay * value for value in row] for row in shape]
        norm = l2_norm(u, h)
        emit_metric("max_abs_u", max_abs(u), step, time)
        emit_metric("l2_error", l2_norm(u, h, minus=exact), step, time)
        # A progress line for people. The contract's parser reads the norm from it.
        print(f"step {step:6d}  t={time:.6e}  norm={norm:.10e}", flush=True)

    report(0)
    for step in range(1, arguments.steps + 1):
        updated = [row[:] for row in u]  # boundary values stay zero
        for i in range(1, n):
            above, here, below, target = u[i - 1], u[i], u[i + 1], updated[i]
            for j in range(1, n):
                target[j] = here[j] + r * (
                    above[j] + below[j] + here[j - 1] + here[j + 1] - 4.0 * here[j]
                )
        u = updated
        if step % arguments.report_every == 0 or step == arguments.steps:
            report(step)

    directory = os.environ.get("NUMERICOS_OUTPUT_DIR", ".")
    with open(os.path.join(directory, "u_final.csv"), "w") as handle:
        for row in u:
            handle.write(",".join(f"{value:.17g}" for value in row) + "\n")
    print(f"wrote u_final.csv after {arguments.steps} steps", flush=True)


if __name__ == "__main__":
    main()
