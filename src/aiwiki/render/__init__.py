"""aiwiki.render package — split out of monolithic app_render.py.

EP-017A: horizontal split of app_render.py (2795 lines) into cohesive
submodules. The legacy aiwiki.app_render module remains as a thin facade
re-exporting all public symbols from the submodules below to preserve
external import sites and (lack of) test patch seams.

Submodules:
- paths: filesystem destinations + wiki log helpers
- packs: output-pack helpers + builders + index
- pilots: domain-pilot scorecards
- views: dashboard renderers
"""
