"""Planner state I/O for repair-plan and query-route telemetry.

Removed: AgentOS signal-to-plan dry-run pipeline (``planner/dry_run``, ``signals/``).
Live: ``planner.state`` and ``planner.paths`` (compile / lint / shell / ask importers).
Note: LLM universal-drop planning lives in ``input_planner.py``, not this package.
"""
