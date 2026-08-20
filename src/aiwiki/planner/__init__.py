"""Planner state I/O for query-route telemetry and retired apply-queue schema.

Removed: AgentOS signal-to-plan dry-run pipeline (``planner/dry_run``, ``signals/``).
Live: ``planner.state`` and ``planner.paths`` (compile / lint / nightly / ask importers).
Live queues (``pending_proposals`` / ``priority_queue`` / ``next_action``) stay empty;
``executed_actions`` history is preserved. LLM universal-drop planning lives in
``input_planner.py``, not this package.
"""
