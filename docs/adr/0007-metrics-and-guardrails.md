# ADR-0007: Scientific metrics are samples with a declared source, collected and guarded by the run's monitor

- Status: accepted (M3-T04, 2026-10-12)
- Deciders: project owner (priority: observability of experiments), implementing agent

## Context

`milestones/M3/AGENTS.md` asks for four levels of observation (process, parser, explicit
instrumentation, validators), a record format for instrumented programs, typed handling of
NaN and infinity, bounded storage that does not flood SQLite, detection of instability with a
window criterion that can halt a run, and a coverage report that names what is unknown. The
root invariants add that no numerical truth is inferred from CPU load, and that no threshold
is invented.

## Decisions

1. **A metric is declared, with its unit and who measures it.** `sampled_by` is
   `instrumentation` (the program emits records), `parser` (a regular expression of the
   contract reads output lines) or `supervisor` (wall time, CPU time and peak memory of the
   program, one exact sample each). Every stored series carries that source.
2. **The record format is strict.** `numericos.metric.v1` is one JSON object per line.
   Unknown fields, wrong types and unknown `numericos.*` schemas make a record invalid. An
   invalid record is never half-accepted: it stays in the output as an ordinary line, records
   no sample and is listed among the run's diagnostics with the reason.
3. **Non-finite values are typed.** A sample is `value: null` with `non_finite` set to `nan`,
   `inf` or `-inf`. On the way in the words are accepted, and so are the literals `NaN` and
   `Infinity` that common libraries write. NumericOS never writes them: its files and
   responses are valid JSON, which a test asserts.
4. **Collection and guardrails run in the monitor.** The monitor already reads every output
   line and can stop the program. Doing both there means that a guardrail holds when no
   supervisor is alive, and that the reaction time is one line, not one polling interval.
5. **Samples go to files, summaries to the database.** One append-only file per metric in the
   run directory, bounded by `limits.max_metrics_mb`; beyond it samples are counted and
   summarised, not stored, and the run says so. The table `metric_series` has one row per run
   and metric (count, first, last, extremes, non-finite count), which is what listing and
   comparing runs need. No raw sample is written to SQLite.
6. **A valid record is a sample, not output.** It is not stored a second time among the
   output lines. A line from which a parser extracted values remains output and is marked.
7. **Guardrails are explicit bounds.** A rule names a declared metric, one bound, a patience
   in consecutive samples and an action. A sample inside the bound resets the count. A
   non-finite sample is beyond every bound. `non_finite: halt | record` decides whether a NaN
   stops the program; either way it is an error event. A halt ends the run
   `failed / numerical_instability` with the metric, bound, value and step in its reason.
8. **Contradictions with the contract are reported, not repaired.** A different unit is
   reported and the value kept as sent, with no conversion. A record for a metric the contract
   assigns to a parser or to the supervisor is ignored. An undeclared metric is kept, up to 50
   names, and marked.
9. **Coverage is an answer per level and per declared metric**, with the states `observed`,
   `partial`, `waiting` (none yet, the run is going), `missing` (none, the run ended) and
   `not_configured`. L3 is `not_configured` until validators exist. Coverage never says that
   a result is valid.
10. **Reading.** Summaries come from the database. Samples are read by byte cursor from the
    file of the metric. An overview reduces a whole series to a bounded number of buckets that
    keep first, last, minimum, maximum and the count of non-finite samples, so a chart of a
    long series shows every spike and every NaN. It is computed by streaming the file.
11. **Programs can note events.** `numericos.event.v1` records become ledger events of the
    run, at most 200 per run.
12. **The digest of a contract covers what it states.** Values equal to the schema's defaults
    are left out of the canonical form, so adding an optional field to the schema (as this
    ticket did with `limits.max_metrics_mb`) does not change the digest of existing contracts.

## Consequences

- Emitting a record costs the program a write to a pipe and the monitor about 6 microseconds
  (measured: 160,000 records per second, none lost). A program that emits faster is slowed
  down to that rate. Nothing is dropped silently.
- Parsers read standard output and standard error. Files that a solver writes are not parsed
  yet.
- A rule looks at consecutive samples of one metric. There is no rule on trends, growth rates
  or combinations of metrics.
- The arrival time at the monitor is always recorded. A timestamp sent by the program is
  stored as sent and is never used to order samples.
- An overview reads the whole file at every request. That is fine for the series of the
  examples and slow for hundreds of megabytes; a cache for finished runs is a later
  optimisation.
- Supervisor metrics exist only for a program that ran. They describe the process, start-up
  included: timing a kernel is the program's job.
