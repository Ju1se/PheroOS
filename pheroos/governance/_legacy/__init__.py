"""Private namespace for frozen v1 compatibility implementations.

The package initializer is deliberately inert.  Legacy owners that still need
the process-local authority registry import its private module explicitly;
merely importing an unrelated compatibility helper must not initialize that
registry in an otherwise durable v2 process.
"""

__all__: list[str] = []
