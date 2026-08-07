"""aiwiki.render package — split out of monolithic app_render.py.

EP-017A: horizontal split of app_render.py (2795 lines) into cohesive
submodules. Import from aiwiki.render.* owner modules directly
re-exporting all public symbols from the submodules below to preserve
external import sites and (lack of) test patch seams.

Submodules:
- paths: filesystem destinations + wiki log helpers
- furnace_center: markdown furnace-center dashboard
- compile_status: markdown compile-status dashboard
- judgment_assets: judgment asset views
- ask_report: ask report scaffold
- protocols: protocol page renderers
- views: dashboard renderers (curated / review-queue / master index)
"""
