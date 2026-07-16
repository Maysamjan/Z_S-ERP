"""Service layer -- business rules, permissions and transaction safety.

Services never trust the UI: permissions are checked here, invariants (negative
stock, credit limits, expired-stock, duplicate documents) are enforced here, and
multi-row postings run inside a single transaction so a failure rolls the whole
operation back.
"""
