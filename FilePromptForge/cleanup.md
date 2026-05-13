# FilePromptForge — Cleanup Suggestions

These are suggested improvements only. No code has been changed.

---

## 1. Consolidate the two README files

Two overlapping readme files exist at the package root:
- `readme.md` — 79 lines, overview of FPF rules and config
- `ReadMe-Newest.md` — 97 lines, expanded version with component details

Pick one as the canonical `README.md` (standard casing), merge any content that
exists only in the other, and delete the duplicate.

---

## 2. Remove test artifacts from the package root

Three scratch files are sitting at the top level alongside production modules:
- `test_a.txt` — 14 bytes
- `test_b.txt` — 14 bytes
- `test_out.md` — 36 bytes

Move them into `test/` or delete them. They are not importable and not
documentation.

---

## 3. Establish a .gitignore for logs/ and __pycache__

The `logs/` directory holds runtime output and should not be committed.
`__pycache__/` directories are scattered through the tree.

Add a `.gitignore` at the FPF root:
```
__pycache__/
*.pyc
logs/*
!logs/.gitignore
```

---

## 4. Clarify the repo boundary

FPF is embedded inside the `acm2` backend repo. If it is a reusable library it
should have its own repository and be consumed as a dependency (e.g. via a local
path in `pyproject.toml` or a private package index). If it is permanently
internal, it needs a clear `__init__.py` public API so callers don't reach into
provider internals.

---

## 5. The `pricing/` subpackage has its own README

`pricing/README.md` documents the pricing fetch logic. That level of
documentation is better placed as a docstring in `fetch_pricing.py` or as a
section in the top-level README, not as a separate file inside a subpackage.

---

## 6. Rename providers for consistency

Provider subdirectory names are inconsistent:
- `openai/`, `anthropic/`, `google/` — plain provider names
- `openaidp/`, `googledp/`, `openrouter/` — suffixed names

Decide on one naming convention and apply it uniformly.
