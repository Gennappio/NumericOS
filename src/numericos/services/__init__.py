"""Use cases: the only place where business rules live. API routes and tools stay thin.

Every successful mutation writes exactly one ledger event in the same transaction as the state
change. A request that changes nothing writes no event and does not bump any version.
"""
