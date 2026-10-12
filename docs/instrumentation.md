# Making a program observable

NumericOS observes a run at four levels. Each one is reported separately, and a level without
data says so instead of looking complete.

| Level | What | Needs |
| --- | --- | --- |
| L0 | The process: output, exit status, time, CPU, memory | nothing |
| L1 | Numbers read from the program's output by a parser | a regular expression in the contract |
| L2 | Metrics the program emits as records | a `print` in the program |
| L3 | Validators that judge a result | not available yet |

Nothing at L0 to L2 says that a result is valid. They say what was measured.

## Declaring metrics

The experiment contract names every metric, its unit and who measures it:

```yaml
metrics:
  - {name: residual, unit: "1", sampled_by: instrumentation}   # the program emits it
  - {name: norm_l2, unit: "1", sampled_by: parser}              # read from the output
  - {name: wall_time, unit: s, sampled_by: supervisor}          # measured from outside
```

A declared metric that never gets a sample is reported as missing. A metric the program emits
without it being declared is kept, up to 50 names, and marked as not declared.

The supervisor measures three quantities, each with exactly one sample, taken from the
operating system when the program ends:

| Metric | Unit | What it is |
| --- | --- | --- |
| `wall_time` | `s` | the program alone, from just before it is started to its exit; build commands are not included |
| `cpu_time` | `s` | user plus system CPU time of the program and the processes it waited for |
| `max_rss` | `bytes` | the largest resident set of one process of the program |

`wall_time` includes the start of the process. To time a kernel, measure around it inside the
program and emit the result as a metric.

## Emitting records (L2)

A record is one line of standard output or standard error that is a JSON object:

```json
{"schema": "numericos.metric.v1", "name": "residual", "value": 0.00032, "step": 42, "time": 0.84}
```

| Field | Required | Meaning |
| --- | --- | --- |
| `schema` | yes | `numericos.metric.v1` |
| `name` | yes | starts with a letter; letters, digits, `_`, `.`, `-`; at most 100 characters |
| `value` | yes | a number, or one of the words `"nan"`, `"inf"`, `"-inf"` |
| `step` | no | non-negative integer: iteration or time step |
| `time` | no | the program's own time coordinate, for example simulated time |
| `unit` | no | compared with the contract's unit; a difference is reported, nothing is converted |
| `timestamp_utc` | no | the program's own clock, stored as sent; the arrival time is always recorded too |
| `run_id` | no | `$NUMERICOS_RUN_ID`; a different value is reported |

Any other field makes the record invalid. An invalid record is not half-accepted: it stays in
the output as an ordinary line, no sample is recorded, and the run lists it with the reason.

JSON has no NaN and no infinity. Write them as words. The literals `NaN` and `Infinity`, which
some libraries produce, are understood on the way in. NumericOS itself never writes them: a
non-finite sample is stored and returned with `value: null` and `non_finite: "nan"`.

Flush after every record. Standard output is fully buffered when it is a pipe, so without a
flush the values arrive when the program ends, and a guardrail cannot act in time.

Python, standard library only (from `examples/heat2d-python/heat2d.py`):

```python
import json, math

def emit_metric(name, value, step, time):
    if math.isnan(value):
        shown = "nan"
    elif math.isinf(value):
        shown = "inf" if value > 0 else "-inf"
    else:
        shown = value
    print(json.dumps({"schema": "numericos.metric.v1", "name": name,
                      "value": shown, "step": step, "time": time}), flush=True)
```

C++: copy `examples/sparse-cg-cpp/numericos_metrics.hpp` next to the solver and call
`numericos::metric("residual", value, iteration);`.

When computing what to emit, do not let the language hide a NaN. A maximum taken with
comparisons, `max()` in Python or `std::max` in C++, can return a finite value although one of
the values is NaN, depending on their order. The heat example shows a maximum that cannot.

### Events

A program can also put a note on the timeline of its run:

```json
{"schema": "numericos.event.v1", "name": "restart", "message": "time step halved", "severity": "warning", "step": 120}
```

`severity` is `info` (the default), `warning` or `error`. The first 200 events of a run are
kept; more are counted.

### Cost

Recording one record takes the monitor about 6 microseconds on the development machine
(160,000 records per second, measured with 300,000 records, none lost). A program that emits
faster is slowed down to that rate by its output pipe. Emit at the rate at which the values
will be looked at, for example every tenth step, not from an inner loop.

## Parsing output (L1)

For a program that cannot be changed, the contract can read numbers from its output lines:

```yaml
observability:
  parsers:
    - name: progress
      stream: stdout          # stdout (default), stderr or any
      pattern: '^step\s+(?P<step>\d+)\s+t=(?P<time>\S+)\s+norm=(?P<norm_l2>\S+)'
```

`pattern` is a Python regular expression searched in every line. Every named group is a metric
of that name, except `step` and `time`, which place the sample. Numbers are read as programs
print them: `1.5e-3`, the Fortran form `1.5D-03`, `NaN`, `Infinity`. Captured text that is not
a number (a field overflow such as `******`) records no sample and is reported. A parser that
matches no line at all is reported too.

Parsed lines remain part of the output. Records do not: a valid record is kept as a sample
and is not shown among the output lines.

Parsers read standard output and standard error only. Files a program writes are not parsed.

## Guardrails

A guardrail is an explicit statement of the contract. NumericOS assumes no threshold.

```yaml
guardrails:
  non_finite: halt            # or "record" (the default)
  rules:
    - {metric: max_abs_u, above: 1.0, patience: 3, action: halt}
```

- A NaN or an infinity in any metric is always an error event of the run. With
  `non_finite: halt` the program is stopped as well.
- A rule is violated when its metric has been beyond the bound (`above` or `below`) for
  `patience` consecutive samples. A non-finite sample is beyond every bound. One sample inside
  the bound resets the count, so a noisy metric does not trip a rule with patience.
- `action: halt` stops the program: SIGTERM to its process group, SIGKILL after the grace
  period. The run ends `failed` with the class `numerical_instability` and says which metric,
  bound, value and step. `action: record` only leaves a warning event.

Guardrails are evaluated by the run's monitor, so they hold even when no supervisor is alive.
A stopped run keeps its series: it is evidence.

State a bound you can justify. The heat example uses an invariant of its scheme, not a tuned
number: see `examples/heat2d-python/README.md`.

## Reading the result

```bash
numericos run metrics RUN_ID              # coverage, one line per series, diagnostics
numericos run metric RUN_ID NAME -f       # the samples of one metric, following the run
```

| Request | Returns |
| --- | --- |
| `GET /v1/runs/{id}/metrics` | series summaries, coverage per level and per declared metric, diagnostics |
| `GET /v1/runs/{id}/metrics/{name}?after=&tail=&limit=` | samples in arrival order, by cursor |
| `GET /v1/runs/{id}/metrics/{name}/overview?buckets=` | the whole series in a bounded number of buckets, each with first, last, minimum, maximum and the count of non-finite samples |

Samples are stored in one file per metric in the run directory, up to `limits.max_metrics_mb`
(256 MB by default). Beyond that they are still counted and summarised, not stored, and the
run says so.

## What is reported when something is off

| Diagnostic | Meaning | What was done |
| --- | --- | --- |
| `malformed_record` | a line looks like a record but is not valid | left in the output, no sample |
| `unsupported_schema` | a record of an unknown `numericos.*` schema | left in the output |
| `undeclared_metric` | a metric the contract does not declare | kept, marked as not declared |
| `undeclared_dropped` | more than 50 undeclared metric names | ignored |
| `unit_mismatch` | the record's unit differs from the contract's | value kept as sent |
| `source_mismatch` | a record for a metric the contract assigns to a parser or the supervisor | ignored |
| `run_id_mismatch` | the record names another run | kept |
| `name_collision` | two names differ only by case | the second is ignored |
| `unparsable_value` | a parser captured text that is not a number | no sample |
