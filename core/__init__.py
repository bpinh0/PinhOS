# PinhOS Phase 1 — Core Runtime Package (core/__init__.py)
# Kept intentionally free of eager submodule imports so transient modules
# (e.g. core.sandbox) can be loaded on demand and garbage-collected cleanly.
