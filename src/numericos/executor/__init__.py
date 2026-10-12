"""Execution of runs.

Two kinds of process cooperate. A **monitor** (one per run) starts the program, observes it and
enforces its limits, writing everything to the run's directory; it needs no database and outlives
whoever started it. The **worker** is the supervisor proper: it launches monitors for queued
runs, turns what they wrote into database state and ledger events, and reconciles after a
restart. The API never executes anything.
"""
