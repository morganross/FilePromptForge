fpf = FPF = File Prompt Forge = /filepromptforge/

FPF rules:
- NEVER uses chat completions; we use the Responses API.
- NEVER uses streaming from LLMs.
- ONLY uses `openrouter` as the provider.
- ALWAYS uses web search for every request.
- NEVER uses mock responses or placeholder content.

There are NO options or configurations that go against the above rules.

Files:
- `fpf_main.py`: CLI entry and importable functions.
- `fpf_config.yaml`: Default configuration loaded at runtime; CLI args can override.

Behavior:
- Loads values from `fpf_config.yaml`.
- Takes two input files, uses them to build a prompt, calls OpenRouter Responses with web search enabled, and saves the response.
- Output is saved by default as `<second-file-name>.fpf.response.txt` next to the second input file.

Web Search specifics (applied from docs):
- Uses the model suffix `:online` automatically (and in config) to enable the web plugin.
- Also sends `web_search.enable: true` and supports options like `max_results` and a custom `search_prompt` per OpenRouter docs.
- Web results are injected before your prompt so models are grounded on live data.

CLI usage:
- Env var: set `OPENROUTER_API_KEY` to your API key.
- Example:
  - `python fpf_main.py path/to/a.txt path/to/b.md`
  - `python fpf_main.py a.txt b.md --model openai/gpt-4o-mini`
  - `python fpf_main.py a.txt b.md --out result.txt`
  - `python fpf_main.py a.txt b.md --env fpf/.env`

API key via .env:


Config (`fpf_config.yaml`):
- `model`: model id to use (defaults to `...:online`; CLI also auto-appends if missing)
- `web_search`: always enabled; supports `max_results` and optional `search_prompt`
- `referer`, `title`: optional headers recommended by OpenRouter
- `prompt_template`: uses `{{file_a_name}}`, `{{file_b_name}}`, `{{file_a}}`, `{{file_b}}`

fpf_main's pirpose is to allow for other software to programaticly call fpf for various differnt llm's without having to have llm specific knowlege.

fpf does not have any knowelge, its provider folders do, it simply routes requests from the 3rd party softrware to the applicaable provider logic. this allows other software to use different llms without having per model knowelege and logic.

fpf_main acts like a router and translator, since different llms use different syntax. 



https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses

https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses

https://platform.openai.com/docs/guides/tools-web-search?api-mode=responses