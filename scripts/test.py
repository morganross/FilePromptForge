"""Build the wheel in isolation and run the complete local test suite."""

from __future__ import annotations

import os
from pathlib import Path
import shutil
import subprocess
import sys
import tempfile
import venv


ROOT = Path(__file__).resolve().parents[1]
KEY_VARIABLES = (
    "ANTHROPIC_API_KEY",
    "CODEXEXECAPI_API_KEY",
    "CODEX_EXEC_API_TOKEN",
    "GOOGLEDP_API_KEY",
    "GOOGLE_API_KEY",
    "OPENAIDP_API_KEY",
    "OPENAI_API_KEY",
    "OPENROUTER_API_KEY",
    "PERPLEXITY_API_KEY",
    "TAVILY_API_KEY",
)


def run(command: list[str], *, cwd: Path, env: dict[str, str]) -> None:
    print("+", " ".join(command), flush=True)
    subprocess.run(command, cwd=cwd, env=env, check=True)


def main() -> int:
    clean_env = os.environ.copy()
    for name in KEY_VARIABLES:
        clean_env.pop(name, None)

    with tempfile.TemporaryDirectory(prefix="filepromptforge-test-") as temp_name:
        temp = Path(temp_name)
        environment = temp / "venv"
        distributions = temp / "dist"
        source = temp / "source"
        shutil.copytree(
            ROOT,
            source,
            ignore=shutil.ignore_patterns(
                ".git",
                ".pytest_cache",
                "__pycache__",
                "*.egg-info",
                "build",
                "dist",
            ),
        )
        venv.EnvBuilder(with_pip=True).create(environment)

        if os.name == "nt":
            python = environment / "Scripts" / "python.exe"
        else:
            python = environment / "bin" / "python"

        run(
            [str(python), "-m", "pip", "install", "build", "pytest", "pytest-asyncio"],
            cwd=temp,
            env=clean_env,
        )
        run(
            [str(python), "-m", "build", "--outdir", str(distributions), str(source)],
            cwd=temp,
            env=clean_env,
        )

        wheels = sorted(distributions.glob("*.whl"))
        if len(wheels) != 1:
            raise RuntimeError(f"Expected one wheel, found {len(wheels)}")

        run(
            [str(python), "-m", "pip", "install", str(wheels[0])],
            cwd=temp,
            env=clean_env,
        )
        run(
            [str(python), "-m", "FilePromptForge", "--help"],
            cwd=temp,
            env=clean_env,
        )
        run(
            [str(python), "-m", "pytest", "-q", str(ROOT / "tests")],
            cwd=ROOT,
            env=clean_env,
        )

    print("FilePromptForge test command completed successfully.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
