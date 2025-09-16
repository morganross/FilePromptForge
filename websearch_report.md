Web Search (web_search) logic audit — filepromptforge
Generated: 2025-09-14 20:42 (local)

Summary
-------
Objective: Inspect repository code for all occurrences of web search / grounding logic, document where it is implemented / toggled, and provide clear recommendations to make web_search behavior explicit, auditable, and enforced.

High-level finding
- Web-search/grounding logic appears in provider adapters (OpenAI, OpenRouter) and in some helper/run modules.
- There are multiple places that consult a config key named `web_search` or `web-search`. Some code defaults that to True; other artifacts (test config) may set it to False for test runs. Archive copies contain older variants and additional references.
- The repository currently mixes two styles of grounding:
  1. Provider-side grounding (preferred) — enabled by adding tools/plugins to the provider payload (Responses API tools or provider-specific plugin blocks)
  2. Client-side websearch (external search) — implemented in ARCHIVE and explicitly allowed only when configured as an opt-in fallback.
- Your instruction: "websearch is not configurable. it must always be on." The current codebase does not fully enforce that rule: it allows enabling/disabling via config in several places.

Files & Findings (by file)
- filepromptforge/providers/openai/fpf_openai_main.py
  - Location: provider adapter translate/build payload
  - Behavior:
    - Reads cfg.get("web_search", {}) or {}
    - If web_search_cfg.get("enable", True) then adds a tool {"type": "web_search"} to payload["tools"] and sets payload["tool_choice"] = cfg.get("tool_choice", "auto")
    - Also honors max_results and search_prompt values if present
  - Note: This is provider-side tooling usage (Responses API). It currently respects config.enable; default True if config missing.

- filepromptforge/fpf/fpf_main.py (helpers)
  - Location: helper module (the small fpf package created earlier)
  - Behavior:
    - There are documented code paths that set `web_search = config.get("web_search") or {"enable": True}`
    - Logging: `logging.info(f"Web search config: {web_search}")`
    - There are conditional code paths that choose plugin vs tools depending on model suffix and web_search settings (commented / archived variants exist)
  - Note: This file both documents and uses a config flag; it currently does not enforce "always on".

- filepromptforge/fpf_config.yaml (top-level config)
  - The test config we added sets `web_search.enable: false` for test run (intentionally disabled for the local test scenario). This conflicts with "not configurable" requirement.

- filepromptforge/readme.md / ARCHIVE/*
  - Multiple references to web_search, guidance docs, and examples showing web_search options and their configuration.
  - ARCHIVE contains older flows and examples that also use `web_search.enable` toggles and show client-side fallback implementations.

- filepromptforge/ARCHIVE/minimal_cli.py (archive)
  - Shows usage of tools=[{"type":"web_search"}] and checks for API key from environment.

- Miscellaneous
  - Several archive files contain implementation notes for client-side web search and grounding policy docs (these are informational, archived).

Implications / Risks
- Because web_search can be disabled in config in multiple places, different executions could run with or without grounding — contrary to "must always be on".
- Test runs or CI runs that set web_search:false will not include provider grounding, which may alter behavior.
- There are archived client-side websearch implementations which, if re-enabled, could perform external network calls or unintentionally change behavior. Archive files are not executed by default but could confuse maintainers.

Recommendations (concrete)
1. Enforce provider-side web search unconditionally
   - Edit provider adapters (starting with filepromptforge/providers/openai/fpf_openai_main.py) to ignore any config flag that would disable provider-side grounding.
     - Always include the appropriate tool/plugin block for supported models:
       * For OpenAI Responses API: always ensure payload["tools"] includes {"type": "web_search", "max_results": <int>, "search_prompt": <str>} with safe defaults when not provided in config.
       * Keep tool_choice as "auto" or configure to your policy.
   - Remove or ignore `web_search.enable` flags in config when building payloads. Instead accept optional tuning params (max_results, search_prompt) but do not allow disabling.

2. Centralize web_search defaults and logging
   - Add a single place (e.g., provider adapter or a dedicated config validator) that decides the final web_search payload shape.
   - Log clearly at INFO when web_search is attached to the outgoing payload and include the sidecar path where raw response will be saved.

3. Prevent accidental client-side fallbacks
   - Keep ARCHIVE code untouched (for reference) but ensure runtime code does not call any client-side websearch functions unless explicitly invoked via a clearly named opt-in API.
   - Add a linter/test that scans for `web_search` usage in non-ARCHIVE runtime files and fails CI if any use attempts to disable grounding.

4. Configuration changes
   - Remove `web_search.enable` toggles from production config examples (keep them only in archived/test configs if you need to simulate offline behavior).
   - If you still want to support a "test" mode that disables web_search, make that explicit (e.g., a command-line flag `--no-websearch-test-mode`) and ensure test configs are only used in CI or local dev flows — do not allow disabling via the general config file.

5. Audit provider support
   - Provider-side grounding is only valid for models that support it. Maintain a whitelist mapping (provider + model family -> supports_tools) and error/log clearly when attempting to attach web_search to unsupported models. Prefer failing loudly rather than silently skipping grounding.

Actions to implement (recommended next steps)
- Make code edits in these files (in order):
  1. filepromptforge/providers/openai/fpf_openai_main.py — remove web_search enable toggle; always attach tools block. Honor max_results/search_prompt only as optional tuning.
  2. filepromptforge/fpf/fpf_main.py — remove defaulting logic that allows disabling; update logs to show final web_search config and source.
  3. filepromptforge/fpf_config.yaml — remove/ignore any web_search.enable:false in production config; keep only tuning keys (max_results/search_prompt).
  4. Add tests/lint rule scanning for `web_search` disable patterns and failing CI if found in non-archive files.

Appendix — Exact occurrences found (non-exhaustive; search matched 70 results including ARCHIVE)
- filepromptforge/providers/openai/fpf_openai_main.py
  - Adds tools array when web_search_cfg.get("enable", True)
  - Handles max_results, search_prompt, filters
- filepromptforge/fpf/fpf_main.py (helpers)
  - web_search defaulting: `web_search = config.get("web_search") or {"enable": True}`
  - Logging of web_search config
  - Plugin vs tools code for web plugins
- filepromptforge/fpf_config.yaml
  - (test config) web_search: enable: false
- ARCHIVE/ files contain numerous examples, docs, and older code paths

If you want, I will:
- Implement the "always on" changes described above (edit provider adapter and helper), and
- Add a small lint/check step that scans the codebase for `web_search.*enable` occurrences in non-ARCHIVE files and fails or reports them.

Next step (pick one)
- I will implement the code changes to enforce web_search always-on (requires Act mode confirmation).
- I will only produce the above report (no code changes).
- I will implement changes and then run the canonical test (requires OPENAI_API_KEY in filepromptforge/.env).
