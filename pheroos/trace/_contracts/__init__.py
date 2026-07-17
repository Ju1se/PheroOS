"""Immutable built-in Trace ABI contract declarations.

The declarations are intentionally private.  Runtime code consumes one
closed, static tuple assembled by :mod:`pheroos.trace.validation`; there is no
registration API and therefore no way for a runtime extension to acquire
authority by mutating the built-in contract set.
"""
