"""Opt-in fault injection used to PROVE transactional atomicity from black-box tests.

When ENABLE_TEST_HOOKS=true (and APP_ENV != production), a request carrying
`X-Test-Fault: <point>` makes the matching `fault_point(<point>)` call raise mid-transaction.
The correct application must then roll back completely. Without the flag the header is ignored.
"""

from contextvars import ContextVar

FAULT_POINTS = frozenset({"after_inventory_decrement", "after_order_insert"})

active_fault: ContextVar[str | None] = ContextVar("active_fault", default=None)


class InjectedFault(RuntimeError):
    """Deliberate failure raised at a named point inside a transaction."""


def fault_point(name: str) -> None:
    if active_fault.get() == name:
        raise InjectedFault(f"Injected fault at '{name}'")
