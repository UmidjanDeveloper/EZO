"""Optional multi-agent missions behind one interface (``OrchestrationProvider``).

EzoCore stays the decision maker. Simple requests go straight to one agent;
only requests that need several specialists become a *mission*, run by the
native provider (always available) or — later, when enabled — by Ruflo through
a restricted MCP boundary. See docs/RUFLO_INTEGRATION_PLAN.md.
"""
