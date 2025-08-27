# FilePromptForge — GPT Processor

Overview
--------
FilePromptForge is a small toolkit for batch-processing text files with an LLM. It includes:
- A GUI installer (Tkinter) to create install folders, write defaults, copy the main executable, and run a quick test.
- A main processing script that combines prompt files, reads input files, sends prompts to an LLM provider (OpenAI or OpenRouter), and writes responses to an output directory.
- Documentation and helper files for configuration and usage.

Features
--------
- Prompt management: combine multiple prompt files into a single system prompt.
- File processing: process multiple input files sequentially and write model responses to the output directory.
- Configurable provider: supports OpenAI and OpenRouter via configuration or environment variables.
- Logging: configurable logging to console and to timestamped log files.
- Installer GUI: creates required directories, default prompts and config, and can copy the main executable into the install directory.



###Installation


install dependancies

Usage
-----
1. Prepare directories (the installer GUI can create these):
   - prompts/  (place one or more prompt files, e.g. standard_prompt.txt)
   - input/    (place files you want processed)
   - output/   (responses will be written here)

2. Run the main processor:
   python gpt_processor_main.py [options]

CLI options supported:
- --config <path>       Path to configuration YAML file
- --prompt <files...>   One or more prompt filenames (from prompts/ directory)
- --input_dir <path>    Directory containing input files
- --output_dir <path>   Directory where responses will be saved
- --model <model>       Model id to use (overrides config)
- --temperature <val>   Temperature for the model
- --max_tokens <int>    Max tokens for completions
- --verbose             Enable verbose (debug) logging
- --log_file <path>     Path to a specific log file

Behavioral details
------------------
- If no config file is provided, the script looks for `default_config.yaml` next to the script and then falls back to environment variables (.env) and sensible defaults.
- If no prompt files are passed on the CLI, the script loads all files in the `prompts/` directory.
- If no API key is configured, the script will generate mock responses rather than calling the remote API.
- The script processes input files sequentially and writes each response to `response_<original_filename>` in the output directory.

Configuration example (YAML)
---------------------------
openai:
  api_key: your_openai_api_key
  model: gpt-4
  temperature: 0.7
  max_tokens: 1500

prompts_dir: prompts
input_dir: input
output_dir: output
provider: OpenAI


