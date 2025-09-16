OpenAI API Key handling audit — filepromptforge
Generated: 2025-09-14 20:43 (local)

Summary
-------
Objective: Inspect repository code for all occurrences of OpenAI API key handling, verify where the key is loaded from, and confirm there are no fallbacks or alternate configuration paths. Your requirement: "the openai key, it lives in .env and nowhere else, it is not configurable and without fallback."

High-level finding
- The running code enforces the presence of an OpenAI API key and expects it to be present in the environment (OPENAI_API_KEY).
- Currently the repository includes an env loader (load_env_file) that can be invoked with a path; file_handler.run calls load_env_file with either an explicit env_path argument or a repository-default .env path.
- The runtime behavior that actually reads the key is: os.environ.get("OPENAI_API_KEY") in filepromptforge/file_handler.py. If the value is missing, the code raises a RuntimeError and fails fast. This is correct behavior for "no fallback".
- There are archived files and sample code that sometimes read OPENAI_API_KEY via os.getenv("OPENAI_API_KEY", "").strip(), and may raise if empty. These are in ARCHIVE/ and do not impact runtime unless resurrected.

Exact (not exhaustive) occurrences inspected
- filepromptforge/file_handler.py
  - load_env_file is called (either with env_path argument or default repo .env).
  - api_key = os.environ.get("OPENAI_API_KEY")
  - If not api_key: raise RuntimeError("API key not found. Set OPENAI_API_KEY in filepromptforge/.env")
  - This enforces fail-fast; current code allows env_path to be passed into run() which will load the specified .env instead of repo .env.

- filepromptforge/fpf/fpf_main.py (helpers)
  - load_env_file(path: str) is implemented in the helper module to read KEY=VALUE lines into os.environ and does not overwrite existing envs.

- filepromptforge/providers/openai/fpf_openai_main.py
  - Provider adapter reads cfg and builds payload but does not read API keys directly. Authorization is handled centrally in file_handler.

- ARCHIVE/*
  - Several archived scripts check for OPENAI_API_KEY in different ways (os.getenv, os.environ), usually raising if missing. These are not part of runtime unless restored.

Assessment vs requirement
- "Key lives in .env and nowhere else" — current runtime requires OPENAI_API_KEY in the process environment. The loader used to populate the environment is load_env_file called by file_handler. By default file_handler calls load_env_file(str(repo_env)) where repo_env is filepromptforge/.env, but file_handler.run currently supports an env_path argument which, if supplied, will be loaded instead. That means the key can be sourced from another file if the CLI caller intentionally passes --env. This conflicts with the strict requirement "nowhere else".
- "it is not configurable and without fallback" — current behavior fails fast (no fallback) when the environment variable is missing. That part is implemented correctly. The only configurability is the env_path argument which lets a caller load a different .env file.

Risks / edge cases
- If a user or CI process sets OPENAI_API_KEY in the shell environment (outside of filepromptforge/.env), the runtime will accept that value. This may be acceptable, but based on your requirement we should treat only filepromptforge/.env as the canonical source and disallow other sources (including process env and --env override).
- load_env_file intentionally does not overwrite existing environment variables; if the process already has an OPENAI_API_KEY from the environment, filepromptforge/.env will not overwrite it. That allows external override even if the file contains a different key.

Recommended code changes (concrete)
1. Enforce single canonical source: filepromptforge/.env only
   - Change file_handler.run to always call load_env_file(str(repo_env)) and ignore env_path CLI argument entirely (or deprecate it).
   - After loading repo .env, read os.environ["OPENAI_API_KEY"] (use direct key access to ensure KeyError if missing, or keep the explicit existence check but do not accept empty string).
   - If OPENAI_API_KEY is not present after loading repo .env -> log and raise RuntimeError (fail fast).

2. Prevent runtime env overrides
   - Change load_env_file behavior or its usage so that it always overwrites the OPENAI_API_KEY from the repo .env (i.e., load_env_file(..., overwrite=True) for OPENAI_API_KEY), or after loading, explicitly set os.environ["OPENAI_API_KEY"] = value_from_repo if present. This prevents an external process env from bypassing the repo-controlled key.
   - Alternatively, read the key directly from the repo .env file instead of using process environment at all (parse the file for OPENAI_API_KEY and use that value). That makes the source unambiguous.

3. Remove or ignore alternate env file handling
   - Remove the env_path CLI option from fpf_main.py and file_handler.run, or make it private/internal for debugging only and not supported in production.

4. Logging & documentation
   - Add an explicit INFO log line at startup indicating the canonical .env path being used (filepromptforge/.env).
   - Document in README that OPENAI_API_KEY must be present in filepromptforge/.env and the code will not accept other sources.

Implementation plan (ordered steps)
- Edit filepromptforge/file_handler.py:
  1. Remove accepting env_path as a configurable input (or ignore it).
  2. Call load_env_file(str(repo_env)) unconditionally.
  3. After loading, attempt to read OPENAI_API_KEY from the repo .env content or from os.environ and fail fast if missing.
  4. Optionally ensure repo .env value takes precedence over process environment (overwrite behavior).
- Update fpf_main.py CLI help text to remove --env option so users cannot configure it.
- Add a short unit/check script (or a startup assertion) that verifies OPENAI_API_KEY is present in filepromptforge/.env and logs the absolute path.

Next steps I can take now (pick one)
- Implement the recommended code changes to enforce .env-only key handling (I will update file_handler.py and fpf_main.py accordingly), then re-run the canonical test (requires OPENAI_API_KEY in filepromptforge/.env).
- Only produce this report (no code changes).
- Implement changes but keep an override flag (not recommended) if you want a temporary escape hatch.

I will proceed with the code changes to enforce .env-only key handling if you confirm; otherwise I will wait for your instruction.
