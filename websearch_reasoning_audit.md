Websearch + Reasoning full-audit — filepromptforge
Generated: 2025-09-14 20:55 (local)

Purpose
-------
You requested a line-level, repository-wide audit focused on:
- Ensuring provider-side web search (web_search) is always ON at the lowest possible level.
- Ensuring "reasoning" is required: if the provider response does not include reasoning, the run must fail and no output file should be written.
- Removing configurable/fallback logic that allows web_search or reasoning to be disabled.
- Produce per-file findings and actionable remediation steps.

Scope & approach
- I scanned runtime code (non-ARCHIVE) and important ARChive docs and artifact files for occurrences of web_search, reasoning, tools, tool_choice, :online, and OPENAI_API_KEY.
- This report lists each runtime file with relevant findings, severity, and recommended edits (concrete replacement or insertion guidance).
- ARCHIVE/ files are reported for reference but not modified.

Summary (top-level)
- Current runtime behavior:
  - web_search is attached only when configs permit; provider adapter checks cfg.get("web_search"). This allows non-websearch requests.
  - reasoning is pass-through: provider adapter will include a reasoning object if supplied by config, but there is no enforcement that the response contains reasoning nor is reasoning forced.
  - The runner writes output files even if web_search/tools are absent or the response lacks reasoning.
- Required enforcement (per your instruction):
  - web_search must be attached for all outgoing provider payloads (for supported models) unconditionally at the provider adapter level.
  - The outgoing payload should include the highest level/verbosity of reasoning available (use the Responses API "reasoning" object or include_reasoning flag if available).
  - After receiving provider response, fail if:
    - provider did not make any tool calls or tools array in request result is empty (indicating no websearch).
    - provider's response does not include a reasoning field (or reasoning is empty).
  - When failing due to above, do not write human-readable output files; instead log and exit with a non-zero code.

Per-file findings and remediation (runtime files only)
1) filepromptforge/providers/openai/fpf_openai_main.py
   - Findings:
     - Reads web_search_cfg = cfg.get("web_search", {}) or {}
     - Checks if web_search_cfg.get("enable", True) then attaches tools array:
         ws_tool: Dict = {"type": "web_search"}
     - Passes through "reasoning" only if cfg contains it (out["reasoning"] = reasoning).
   - Severity: High — this is the core payload builder.
   - Recommended changes:
     - Remove the enable toggle. Always attach a web_search tools block for supported models.
     - Provide safe defaults for max_results and search_prompt when not supplied.
     - Ensure reasoning is always present in payload. If config does not supply a reasoning object, set a default high-level reasoning object. Example change (conceptual):
       - Always do:
         ws_tool = {"type":"web_search", "max_results": cfg.get("web_search", {}).get("max_results", 10), "search_prompt": cfg.get("web_search", {}).get("search_prompt", "<default>")}
         payload["tools"] = [ws_tool]
         payload["tool_choice"] = "auto"
       - Always include:
         out["reasoning"] = cfg.get("reasoning") or {"explain": "high", "depth": "high"}
     - Add logging: logging.getLogger("openai").info("Attaching web_search tools and forcing reasoning level: high")
   - Post-response enforcement (see file_handler changes below).

2) filepromptforge/file_handler.py
   - Findings:
     - Loads env and builds headers, performs POST, and then parses response via provider.parse_response.
     - Writes human-readable output file and raw JSON sidecar after parsing with provider.parse_response.
     - Currently checks for OPENAI_API_KEY and fails fast if missing; good.
     - No enforcement that response used web_search or includes reasoning.
   - Severity: High — responsible for deciding whether to write output files.
   - Recommended changes:
     - After receiving raw_json, validate:
       a) Tools used: check raw_json["tools"] or raw_json["tool_choice"] or raw_json["output"] to confirm provider performed web_search. If model/tool metadata indicates no web_search occurred, raise RuntimeError("Provider did not perform web search").
       b) Reasoning present: inspect raw_json for a reasoning field (e.g., raw_json["reasoning"] or output items that include "reasoning"). If not present or empty -> raise RuntimeError("Provider did not return reasoning; aborting per policy").
     - Only if both checks pass:
       - Parse response (provider.parse_response) and then write human-readable file + raw sidecar.
     - When aborting, log at ERROR with context (payload summary, path to saved raw request if saved) and return non-zero upward.
     - Also, log and save the raw provider response regardless (for auditing), but do not write the human-readable response file.

   - Example pseudocode insertion (conceptual):
     raw_json = _http_post_json(provider_url, payload_body, headers)
     # Always save raw sidecar immediately (overwrite allowed)
     save_raw_sidecar(...)
     # Validate web_search
     tools_used = raw_json.get("tools") or raw_json.get("tool_calls") or []
     if not tools_used:
         logging.getLogger("file_handler").error("No web_search tools were invoked in provider response; aborting.")
         raise RuntimeError("No web_search observed in provider response")
     # Validate reasoning
     reasoning = raw_json.get("reasoning") or find_reasoning_in_output(raw_json)
     if not reasoning:
         logging.getLogger("file_handler").error("No reasoning returned by provider; aborting.")
         raise RuntimeError("No reasoning returned by provider")
     # Now parse + write output

3) filepromptforge/fpf_main.py (top-level runner)
   - Findings:
     - Top-level CLI; resolves paths and calls file_handler.run.
     - Accepts --env flag (currently) — note your prior requirement said env only in filepromptforge/.env; consider removing --env.
   - Severity: Medium
   - Recommended changes:
     - Remove or ignore --env CLI option (enforce only filepromptforge/.env).
     - Ensure process exit code is non-zero when file_handler.run raises (already returns 2 on exception). Keep this behavior.
     - Log at INFO that web_search+reasoning enforcement policy is active.

4) filepromptforge/fpf/fpf_main.py (helpers)
   - Findings:
     - load_env_file and load_config exist here; load_config returns {} when file missing.
     - Some code paths set default web_search = config.get("web_search") or {"enable": True}. That allows disable.
   - Severity: Medium
   - Recommended changes:
     - Remove default that allows disabling. If config file contains toggles, ignore enable field.
     - Make load_config log WARNING if config missing; but do not allow web_search enable=false to have effect.
     - If you prefer a single source of truth, eliminate web_search.enable key and only permit tuning keys (max_results/search_prompt).

5) filepromptforge/fpf_config.yaml
   - Findings:
     - Test config currently had web_search.enable: false (we updated earlier). This must not disable web_search.
   - Severity: High (config overrides policy).
   - Recommended changes:
     - Remove web_search.enable from production configs; if present in test configs treat it as test-only and override by code that enforces always-on in providers.
     - Ensure default max_results/search_prompt present.

6) filepromptforge/providers/openai/fpf_openai_config.yaml and other provider config files
   - Findings: Check for presence of web_search toggles; treat these as tuning only.
   - Recommended changes: same as provider adapter.

7) filepromptforge/test/*, filepromptforge/ARCHIVE/*
   - Findings: Many illustrative examples in ARCHIVE show toggles; keep for reference only.
   - Recommended changes:
     - Leave ARCHIVE as-is but mark it clearly in README; do not run archive code paths.

8) Logs and sidecars
   - Findings: raw JSON sidecar saved for each run (good).
   - Recommended changes:
     - Add explicit recording in fpf_run.log when:
         - web_search tools were requested in the outbound payload (log payload summary)
         - web_search tools were invoked (log evidence from response)
         - reasoning present or absent (log reasoning summary or failure)
     - Save reasoning content into a dedicated log / sidecar: e.g., <out>.reasoning.txt or appended in fpf_run.log with clear delimiting.

9) provider.parse_response in filepromptforge/providers/openai/fpf_openai_main.py
   - Findings:
     - parse_response currently returns pretty JSON when it cannot extract text. It also logs and raises on parse errors.
     - No extraction of reasoning as a separate return value.
   - Recommended changes:
     - Modify parse_response to return a tuple: (human_text, reasoning_present_bool, reasoning_text_or_none, tool_usage_metadata)
     - Alternatively add a new function extract_reasoning(raw_json) that returns the reasoning content and whether it was present.
     - Ensure file_handler uses that to enforce policy.

10) Other runtime modules / occurrences (quick list)
   - filepromptforge/readme.md — docs reference web_search; update to reflect always-on policy.
   - filepromptforge/fpf_run.log — used for verification; ensure entries cover the enforcement checks.

Implementation plan (recommended, ordered)
1. Provider adapter change (openai):
   - Force tools block & reasoning object insertion at payload build time.
   - Log payload decisions at INFO.

2. file_handler enforcement:
   - Immediately save raw sidecar (always).
   - Validate that provider performed web_search (check tools metadata in response); fail if absent.
   - Validate reasoning present; fail if absent.
   - Only after passing both checks, parse and write the human-readable output file.

3. parse_response / reasoning extractor:
   - Update provider.parse_response to also return reasoning (or implement extract_reasoning).
   - Save reasoning either into fpf_run.log (structured) and into a separate reasoning sidecar file for auditing.

4. Config & CLI:
   - Remove --env CLI or ignore it.
   - Update sample fpf_config.yaml: remove web_search.enable or mark as ignored in production.

5. Tests / CI:
   - Create a lint/test that scans runtime files for web_search.enable usage and fails until adapters are updated to ignore it.
   - Add a canonical-run integration test that asserts:
     - The raw JSON sidecar contains tools usage.
     - The raw JSON sidecar contains a non-empty reasoning field.

6. Documentation:
   - Update README and .clinerules/runtime-verification.md to document the enforcement rules.

Failure behavior
- If provider response fails enforcement (no web_search or no reasoning):
  - Save raw sidecar (always).
  - Log error with payload summary, raw sidecar path, and suggestion.
  - Do NOT write human-readable output file.
  - Exit with non-zero code (RuntimeError bubbling up to fpf_main->exit code 2).

Deliverables I will produce when you confirm
- A complete per-file patch implementing the changes above (provider adapter + file_handler + parse_response updates + config adjustments).
- A new audit file listing exact line-by-line changes that were made (so you can review).
- New sidecar file pattern for reasoning (<out>.reasoning.txt) and log additions.

Next step (pick one)
- I will implement the code changes to enforce always-on web_search and required reasoning (Act Mode). This will:
  - Modify provider adapter and file_handler as described,
  - Add reasoning extraction and sidecar logging,
  - Re-run canonical test (requires OPENAI_API_KEY in filepromptforge/.env; present now),
  - Report results (terminal output, fpf_run.log, response/raw sidecar, reasoning sidecar).
- Or I will only produce this report (no code changes).

Please confirm "implement" to proceed with automatic code changes and a canonical run, or "report-only" to stop here.
