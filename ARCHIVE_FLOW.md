# Archive: Expanded Flow and Features for FilePromptForge — Detailed Blueprint

This document expands the prior blueprint into a detailed, implementation-oriented plan to archive the current codebase and guide a minimal, maintainable reimplementation. It anchors each major decision to concrete code references in the repository for traceability.

1) Intent and success criteria
- Create a compact, deterministic data flow: prompts are loaded, concatenated into a system prompt, inputs are read, and outputs are written without remote API calls by default.
- Provide a pluggable backend stack that can be swapped for real providers (OpenAI/OpenRouter/Google) or a local mock backend for testing.
- Enable local development with a small CLI surface and minimal dependencies to keep onboarding quick.
- Preserve the ability to run from CLI with clear, stable behavior and deterministic tests.

Key code anchors:
- Prompt loading and concatenation originate in [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181).
- The main orchestration, argument parsing, and end-to-end flow live in [main()](filepromptforge/gpt_processor_main.py:481).
- Core IO operations live in [FileHandler.list_input_files](filepromptforge/gpt_processor_main.py:202), [FileHandler.read_file](filepromptforge/gpt_processor_main.py:216), and [FileHandler.write_file](filepromptforge/gpt_processor_main.py:230).
- The primary API invocation is performed by [APIClient.send_prompt](filepromptforge/gpt_processor_main.py:251).
- The default prompt creation helper is [create_default_prompt](filepromptforge/gpt_processor_main.py:462).

2) Scope and boundaries
- In-scope: loading prompts, concatenating system prompts, reading inputs, writing outputs, and a minimal, mock-friendly testing pathway.
- Out-of-scope (for initial rebuild): advanced grounding workflows, multi-tenant configurations, complex logging analytics, and deep provider-side orchestration.
- The new design favors a small, well-documented surface area with a clean separation of concerns.

3) Architecture overview and interfaces
- Core modules (and responsibilities):
  - Prompt loading: load_prompts(prompt_files) -> str
  - File IO: list_input_files() -> List[str], read_file(path) -> str, write_file(path, content) -> None
  - API abstraction: send_prompt(system_prompt, user_prompt) -> str
  - Optional grounding: Grounder integration (provider-side grounding) via grounding/grounder.py
  - Configuration: centralized config loading with per-provider config blocks
- Orchestrator: main() wires the above together, handling CLI args, path resolution, and the main processing loop.

Key code anchors:
- [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181)
- [FileHandler.list_input_files](filepromptforge/gpt_processor_main.py:202)
- [FileHandler.read_file](filepromptforge/gpt_processor_main.py:216)
- [FileHandler.write_file](filepromptforge/gpt_processor_main.py:230)
- [APIClient.send_prompt](filepromptforge/gpt_processor_main.py:251)
- [Grounder integration](grounding/grounder.py)

4) Data model and lifecycle
- system_prompt: Built by concatenating prompt contents with a single newline separator between prompts.
- user_prompt: The raw text read from an input file in the input_dir.
- response: The model output saved to the output_dir with a filename pattern mirroring the input, prefixed with "response_".
- Lifecycle sequence:
  1) Load config (default_config.yaml or user-provided)
  2) Ensure directories exist (prompts_dir, input_dir, output_dir)
  3) Load prompts to form system_prompt
  4) Enumerate input files
  5) For each input, read user_prompt, call API client, write response, optionally delay between files

Code anchors:
- Loading and concatenating prompts relies on [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181)
- Directory and file IO flow is driven by [FileHandler] methods
- End-to-end flow is driven by [main()](filepromptforge/gpt_processor_main.py:481)

5) Prompt concatenation details (deep dive)
- Order of prompts:
  - If CLI passes --prompt, prompt_files preserves that user-provided order.
  - If no explicit prompts are provided, the code enumerates the prompts_dir (order dependent on filesystem listing, e.g., os.listdir in the main path).
  - The combined system_prompt is created by joining the individual prompt contents with a single newline character between prompts.
- Reading prompts:
  - Each prompt_file is opened with UTF-8 encoding and read in full, then appended to a list of prompts in the loaded order.
  - Reference for loading logic: [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181).
- Joining semantics:
  - System prompt = "\n".join(prompts)
  - Embedded newlines within each prompt are preserved; separation is strictly one newline between prompts.
- Edge and normalization notes:
  - Trailing whitespace inside prompts is preserved unless an external normalization step is introduced.
  - There is no automatic deduplication or dedent normalization in the baseline approach.

Prompts and example references:
- The test prompt used in the repository is at [`filepromptforge/test/prompts/standard_prompt.txt`](filepromptforge/test/prompts/standard_prompt.txt:1), which contains the base instruction for ChatGPT-style responses.

6) Core modules in detail (implementation-oriented)
- PromptManager
  - API: load_prompts(prompt_files) -> str
  - Process:
    - Resolve full paths for each prompt file: os.path.join(self.prompts_dir, prompt_file)
    - Read file content fully (UTF-8)
    - Append to a list in the provided order
    - Return "\n".join(prompts)
  - Key code reference: [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181)

- FileHandler
  - API:
    - list_input_files() -> List[str]
    - read_file(path) -> str
    - write_file(path, content) -> None
  - Process:
    - Recursive directory walk for input_dir to list files with relative paths
    - Read input files as UTF-8 text
    - Ensure output directories exist before writing
  - Key code references:
    - [FileHandler.list_input_files](filepromptforge/gpt_processor_main.py:202)
    - [FileHandler.read_file](filepromptforge/gpt_processor_main.py:216)
    - [FileHandler.write_file](filepromptforge/gpt_processor_main.py:230)

- APIClient
  - API surface: send_prompt(system_prompt, user_prompt) -> str
  - Responsibilities:
    - Resolve provider, credentials, model, temperature, and max_tokens
    - Construct a provider-specific request payload, including tokenization kwargs if available
    - Attempt provider API call with two attempts and a fallback path
    - Optional provider-grounding integration when enabled in configuration (Grounder)
  - Key code reference:
    - [APIClient.send_prompt](filepromptforge/gpt_processor_main.py:251)

- Grounder
  - Integration path:
    - Grounder(self.config, logger=logger).run(system_prompt, user_prompt, grounding_options=...)
  - Purpose:
    - Optional provider-side grounding prior to standard API call
    - If grounding succeeds and returns a provider-tool outcome, return the grounded text
  - Key reference:
    - [grounding/grounder.py](grounding/grounder.py)

- Config
  - Behavior:
    - Load defaults from default_config.yaml if present, otherwise use embedded defaults
    - Support per-provider configuration blocks (openai, openrouter, google)
    - Environment variable bindings for sensitive values (OPENAI_API_KEY, OPENROUTER_API_KEY, GOOGLE_API_KEY)
  - Key code references:
    - [Config.__init__](filepromptforge/gpt_processor_main.py:86)
    - [Config.ProviderConfig](filepromptforge/gpt_processor_main.py:147)
    - [Config.GroundingConfig](filepromptforge/gpt_processor_main.py:163)

- CLI and runtime behavior
  - Main entrypoint: [main()](filepromptforge/gpt_processor_main.py:481) handles CLI argument parsing, config loading, and orchestration
  - CLI options:
    - --config, --log_file, --verbose, --prompt, --input_dir, --output_dir, --model, --temperature, --max_tokens
  - Configuration precedence:
    - CLI args > config.yaml > default_config.yaml
  - Run example:
    - python gpt_processor_main.py --config filepromptforge/default_config.yaml
  - Logging:
    - Per-run timestamped log directory under a logs/ subfolder (created in main)

7) Run-time flow (step-by-step)
- Step 1: Load configuration using the provided config path or defaults
- Step 2: Ensure prompts_dir, input_dir, output_dir exist
- Step 3: Determine prompt_files:
  - If args.prompt provided: use that list
  - Else: list contents of prompts_dir
  - If no prompts are present, create a default prompt via [create_default_prompt](filepromptforge/gpt_processor_main.py:462)
- Step 4: Read and concatenate prompts to form system_prompt via [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181)
- Step 5: List input files via [FileHandler.list_input_files](filepromptforge/gpt_processor_main.py:202)
- Step 6: For each input file:
  - Read user_prompt via [FileHandler.read_file](filepromptforge/gpt_processor_main.py:216)
  - Call API client with system_prompt and user_prompt via [APIClient.send_prompt](filepromptforge/gpt_processor_main.py:251)
  - Write the response via [FileHandler.write_file](filepromptforge/gpt_processor_main.py:230)
  - Optional: delay between files as configured
- Step 7: Exit cleanly if no input files are found or if errors occur

Edge cases and safeguards
- No input files found: log an info message and exit gracefully
- Missing prompts: create a default prompt and retry prompt loading
- Grounding enabled: attempt grounding; otherwise, fall back to standard API flow
- Invalid or missing API keys: raised clearly and surfaced through logs

8) Testing and validation path
- Testing strategy emphasizes a mocked backend to exercise prompt loading and file IO without external calls
- Suggested tests:
  - Test that load_prompts respects prompt_files order and joins with a single newline
  - Test that read_file and write_file preserve content structure and directory layout
  - Test end-to-end flow with a mock API client that returns deterministic responses
- Example test artifacts you can reuse:
  - Standard prompt content: [`filepromptforge/test/prompts/standard_prompt.txt`](filepromptforge/test/prompts/standard_prompt.txt:1)
  - Test inputs: [`filepromptforge/test/input/`](filepromptforge/test/input)

9) Migration plan (phases)
- Phase 0: Archive current code as an immutable snapshot (so you can revert)
- Phase 1: Create a minimal, clean repository with a simplified architecture
- Phase 2: Implement a lightweight CLI and a mock backend
- Phase 3: Write end-to-end tests with deterministic mocks
- Phase 4: Gradually deprecate the old codebase and replace references
- Phase 5: Document how to run tests and how to extend with real providers

10) Acceptance criteria for the rebuild
- The pipeline can load prompts, read inputs, and write outputs without contacting external APIs
- Deterministic mocked responses are available for test runs
- The codebase is small, well-documented, and easy to understand and extend

11) References and anchors (quick lookup)
- Loading and concatenation: [PromptManager.load_prompts](filepromptforge/gpt_processor_main.py:181)
- IO operations: [FileHandler.list_input_files](filepromptforge/gpt_processor_main.py:202), [FileHandler.read_file](filepromptforge/gpt_processor_main.py:216), [FileHandler.write_file](filepromptforge/gpt_processor_main.py:230)
- API invocation: [APIClient.send_prompt](filepromptforge/gpt_processor_main.py:251)
- Default prompt helper: [create_default_prompt](filepromptforge/gpt_processor_main.py:462)
- Main orchestration: [main()](filepromptforge/gpt_processor_main.py:481)
- Grounding integration (optional): [grounding/grounder.py](grounding/grounder.py)

End of document