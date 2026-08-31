# Installation

FPF requires Python 3.11 or newer.

Install the published package:

```bash
python -m pip install filepromptforge
```

Install a source checkout with development dependencies:

```bash
git clone https://github.com/morganross/FilePromptForge.git
cd FilePromptForge
python -m pip install -e ".[dev]"
```

Run `fpf --help` to confirm the command is available. Run
`python scripts/test.py` from a source checkout to build the wheel in an
isolated environment and run the complete test suite without provider keys.

Provider credentials are read from environment variables before the optional
`.env` file. The default `.env` location is the operating system's user
configuration directory; `--env` selects another file explicitly.

No credentials are included in the package or repository.
