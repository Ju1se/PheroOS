"""Composable runtime node implementations.

The current LangGraph runtime still lives mostly in `runtime.graph`, but new
node logic should land here so capability entrypoints can gradually take over
business-specific paths without growing the graph module.
"""
