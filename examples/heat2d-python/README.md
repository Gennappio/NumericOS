# 2D heat equation, explicit scheme

A small, fully characterised numerical experiment: the same program is stable or unstable
depending on one parameter, and the limit between the two can be derived exactly.

## Problem and scheme

`u_t = alpha (u_xx + u_yy)` on the unit square, `u = 0` on the boundary,
`u(x, y, 0) = sin(pi x) sin(pi y)`. The exact solution is
`u = exp(-2 pi^2 alpha t) sin(pi x) sin(pi y)`.

`heat2d.py` uses forward Euler in time and 5-point central differences in space (FTCS) on a
uniform grid with `N` intervals per side, `h = 1/N`, `r = alpha dt / h^2`:

```text
u[i][j] <- u[i][j] + r (u[i+1][j] + u[i-1][j] + u[i][j+1] + u[i][j-1] - 4 u[i][j])
```

## When this scheme is stable

This is the stability condition of this discretisation, not a general rule for other schemes.

With zero boundary values the discrete sine modes `sin(p pi i h) sin(q pi j h)`,
`p, q = 1 .. N-1`, are eigenvectors of the update. One step multiplies mode `(p, q)` by

```text
g(p, q) = 1 - 4 r (sin^2(p pi h / 2) + sin^2(q pi h / 2))
```

All modes stay bounded exactly when `|g| <= 1` for every mode. The most negative factor belongs
to `p = q = N-1`, which gives the exact limit for a grid with `N` intervals:

```text
r <= 1 / (4 cos^2(pi / (2 N)))
```

The right-hand side is slightly above 1/4 and tends to 1/4 as the grid is refined, so
**`r <= 1/4` is sufficient on every grid**. For `N = 32` the exact limit is `r <= 0.250603`,
that is `dt <= 2.4473e-4` with `alpha = 1`.

Above the limit the initial condition itself does not grow (it is the smooth mode `(1, 1)`).
What grows is round-off: an error of relative size 1e-17 in the highest mode is multiplied by
`|g(N-1, N-1)|` at every step. With `r = 0.3072` that factor is 1.45 and the error reaches the
size of the solution after about 105 steps; with `r = 0.26624` it is 1.12 and it takes about
330 steps. A run that is "only a little" unstable looks fine for a long time.

## What the guardrail means

For `r <= 1/4` the new value at a point is a weighted average of old values with non-negative
weights `1 - 4r, r, r, r, r` that sum to 1. The largest `|u|` therefore cannot increase: with
this initial condition `|u| <= 1` at every step. The contract's rule
`max_abs_u above 1.0 for 3 consecutive samples` checks this invariant. It is not a tuned
threshold, and it says nothing about other initial conditions.

## What the program reports

Every `--report-every` steps:

- `max_abs_u` and `l2_error` (the discrete L2 norm of the difference to the exact solution) as
  `numericos.metric.v1` records;
- a progress line `step N  t=...  norm=...`, from which the contract's parser reads `norm_l2`.

Because the initial condition is a single mode, both norms have closed forms in exact
arithmetic, which the tests of this repository check to round-off:

```text
norm_l2(n)  = 0.5 g^n                               g = g(1, 1)
l2_error(n) = 0.5 |g^n - exp(-2 pi^2 alpha n dt)|
```

`l2_error` is the error of the scheme, first order in `dt` and second order in `h`. It is not a
residual.

## Running it

Alone:

```bash
python3 heat2d.py --dt 0.0002 --grid 32 --steps 600
```

Under NumericOS, from the top of this repository, with `make api` and `make worker` running:

```bash
numericos project add "Heat 2D" --root-path "$PWD"
numericos project trust PROJECT_ID
numericos experiment run examples/heat2d-python/experiment.yaml -p PROJECT_ID -P dt=0.0002
numericos experiment run examples/heat2d-python/experiment.yaml -p PROJECT_ID -P dt=0.0003
numericos run metrics RUN_ID
```

The first run ends `succeeded`. The second is stopped by the guardrail after about 130 steps
and ends `failed` with the class `numerical_instability`; its series stay available as
evidence. Neither status says whether a result is valid: validators do that.

Both runs take a fraction of a second. `experiment-fine.yaml` is the same experiment on a
128 x 128 grid (`dt` 1.4e-05 stable, 1.7e-05 unstable): the stable run takes about 12 s on the
development machine, long enough to follow its metrics and its resource use while it runs.

```bash
numericos experiment run examples/heat2d-python/experiment-fine.yaml -p PROJECT_ID -P dt=1.4e-05
```
