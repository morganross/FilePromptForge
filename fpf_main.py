"""
FPF top-level runner script.

Run this from the repository like:

  cd filepromptforge
  python fpf_main.py --help

Notes / guarantees implemented:
- Works when invoked from any working directory. The script resolves the package root
  (the directory containing this file) and inserts its parent into sys.path so that
  imports like `filepromptforge.file_handler` succeed regardless of cwd.
- Sets up logging to console and to a rotating log file located next to this script
  (fpf_run.log). All important steps are logged.
- Resolves relative paths against the repository package dir when the path is not
  found in the caller's cwd. This allows config or input files to be referenced
  relative to the package directory.
- Delegates the heavy work to filepromptforge.file_handler.run(...)
"""

from __future__ import annotations
import argparse
import logging
import logging.handlers
import sys
from pathlib import Path
from typing import Optional

# Ensure imports find the package when called from other directories.
SCRIPT_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = SCRIPT_DIR
# Add the parent of the package to sys.path so `import filepromptforge.*` works.
if str(PROJECT_ROOT.parent) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT.parent))

from filepromptforge.file_handler import run as run_handler  # type: ignore

LOG_FILENAME = SCRIPT_DIR / "logs" / "fpf_run.log"
# Ensure logs directory exists so the rotating file handler can write there
if not LOG_FILENAME.parent.exists():
    LOG_FILENAME.parent.mkdir(parents=True, exist_ok=True)


import yaml


def setup_logging(level: int = logging.INFO) -> None:
    logger = logging.getLogger()
    logger.setLevel(level)

    # Console handler
    ch = logging.StreamHandler()
    ch.setLevel(level)
    ch_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    ch.setFormatter(ch_formatter)

    # File handler (rotating)
    fh = logging.handlers.RotatingFileHandler(
        filename=str(LOG_FILENAME),
        maxBytes=5 * 1024 * 1024,
        backupCount=3,
        encoding="utf-8",
    )
    fh.setLevel(level)
    fh_formatter = logging.Formatter("%(asctime)s %(levelname)s %(name)s: %(message)s")
    fh.setFormatter(fh_formatter)

    # Avoid duplicate handlers if setup_logging called multiple times
    if not any(isinstance(h, logging.StreamHandler) for h in logger.handlers):
        logger.addHandler(ch)
    if not any(isinstance(h, logging.handlers.RotatingFileHandler) for h in logger.handlers):
        logger.addHandler(fh)

def resolve_path_candidate(candidate: Optional[str]) -> Optional[str]:
    """
    Resolve a possibly relative path.

    Order:
    1. If candidate is None -> return None
    2. If absolute -> return if exists, else still return absolute (let downstream error)
    3. If relative and exists relative to cwd -> return that
    4. If relative and exists relative to PROJECT_ROOT -> return PROJECT_ROOT / candidate
    5. Otherwise return candidate unchanged (downstream will error)
    """
    if not candidate:
        return None
    p = Path(candidate)
    if p.is_absolute():
        return str(p)
    # exists relative to cwd
    cwd_try = Path.cwd() / candidate
    if cwd_try.exists():
        return str(cwd_try)
    pkg_try = PROJECT_ROOT / candidate
    if pkg_try.exists():
        return str(pkg_try)
    # fallback - not found in cwd or package. Log and return None so caller can fail fast.
    import logging
    logging.getLogger("fpf_main").error("Path not found in cwd or package: %s", candidate)
    return None

def load_config(path: str) -> dict:
    with open(path, "r", encoding="utf-8") as f:
        return yaml.safe_load(f)

def main(argv: Optional[list[str]] = None) -> int:
    setup_logging(logging.INFO)
    log = logging.getLogger("fpf_main")
    parser = argparse.ArgumentParser(prog="fpf_main", description="File Prompt Forge runner")
    parser.add_argument("--file-a", help="First input file (left side).", dest="file_a")
    parser.add_argument("--file-b", help="Second input file (right side).", dest="file_b")
    parser.add_argument("--out", help="Output path for human-readable response", dest="out")
    parser.add_argument("--config", help="Path to fpf_config.yaml", dest="config")
    parser.add_argument("--env", help="Path to .env (optional). Defaults to package .env", dest="env")
    parser.add_argument("--model", help="Override model id", dest="model")
    parser.add_argument("--verbose", "-v", action="store_true", help="Enable verbose logging")
    args = parser.parse_args(argv)

    if args.verbose:
        setup_logging(logging.DEBUG)
        log.setLevel(logging.DEBUG)
        log.debug("Verbose logging enabled")

    log.info("Starting FPF runner")
    log.debug("Script dir: %s", SCRIPT_DIR)
    
    config_path = resolve_path_candidate(args.config) or str(PROJECT_ROOT / "fpf_config.yaml")
    cfg = load_config(config_path)

    file_a_path = args.file_a or cfg.get("test", {}).get("file_a")
    file_b_path = args.file_b or cfg.get("test", {}).get("file_b")

    file_a = resolve_path_candidate(file_a_path)
    if not file_a:
        raise FileNotFoundError(f"Input file not found: {file_a_path}")
    file_b = resolve_path_candidate(file_b_path)
    if not file_b:
        raise FileNotFoundError(f"Input file not found: {file_b_path}")

    config = config_path
    env = resolve_path_candidate(args.env) or str(PROJECT_ROOT / ".env")
    out = resolve_path_candidate(args.out)
    model = args.model

    log.debug("Resolved paths - file_a=%s, file_b=%s, config=%s, env=%s, out=%s, model=%s",
              file_a, file_b, config, env, out, model)

    try:
        result_path = run_handler(
            file_a=file_a,
            file_b=file_b,
            out_path=out,
            config_path=config,
            env_path=env,
            model=model,
        )
        log.info("Run completed. Output written to %s", result_path)
        print(result_path)
        return 0
    except Exception as exc:
        log.exception("FPF run failed: %s", exc)
        print(f"FPF run failed: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
