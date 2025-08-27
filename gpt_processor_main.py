#!/usr/bin/env python3
"""
GPT Processor Main Application

Features:
- Combine multiple prompt files into a single system prompt.
- Process multiple input files sequentially.
- Save AI-generated responses to output directory.
- Comprehensive logging to console and optional log file.
"""
import os
import argparse
import logging
import sys
import time
from datetime import datetime
from concurrent.futures import ThreadPoolExecutor
from grounding.grounder import Grounder

# External dependencies (do NOT install at import time).
# Ensure these are installed (see requirements.txt) before running the script:
# pip install -r requirements.txt

try:
    from openai import OpenAI
except Exception as e:
    print("Missing dependency: openai. Install required packages with:")
    print("    pip install -r requirements.txt")
    sys.exit(1)

try:
    import yaml
    from dotenv import load_dotenv
except Exception as e:
    missing_package = None
    try:
        missing_package = str(e).split("'")[1]
    except Exception:
        missing_package = str(e)
    print(f"Error: Missing required package '{missing_package}'.")
    print("Please install all dependencies using:")
    print("    pip install -r requirements.txt")
    sys.exit(1)


# Setting up the logger
def setup_logger(log_level=logging.INFO, log_file=None):
    logger = logging.getLogger('gpt_processor')
    logger.setLevel(log_level)
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(filename)s:%(funcName)s:%(lineno)d - %(message)s'
    )

    # Console handler
    if not logger.handlers:
        ch = logging.StreamHandler()
        ch.setLevel(log_level)
        ch.setFormatter(formatter)
        logger.addHandler(ch)

    # File handler
    if log_file:
        fh = logging.FileHandler(log_file)
        fh.setLevel(log_level)
        fh.setFormatter(formatter)
        logger.addHandler(fh)

    return logger


# Ensure directory exists
def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory, exist_ok=True)


# Configuration class
class Config:
    def __init__(self, config_file=None, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        load_dotenv()  # Load environment variables from .env if present
        default_config = {
            'prompts_dir': os.path.join(base_dir, 'test', 'prompts'),
            'input_dir': os.path.join(base_dir, 'test', 'input'),
            'output_dir': os.path.join(base_dir, 'test', 'output'),
            'provider': 'OpenAI',  # Default provider
            'openai': {
                'api_key': os.getenv('OPENAI_API_KEY'),
                'model': 'gpt-4',
                'temperature': 0.7,
                'max_tokens': 1500
            },
            'openrouter': {
                'api_key': os.getenv('OPENROUTER_API_KEY', '').strip(),
                'model': '',
                'temperature': 0.7,
                'max_tokens': 1500
            },
            'google': {
                'api_key': os.getenv('GOOGLE_API_KEY', '').strip(),
                'model': '',
                'temperature': 0.7,
                'max_tokens': 1500
            },
            'grounding': {
                'enabled': False,
                'provider': 'openai',
                'max_results': 3,
                'search_prompt': 'Incorporate and cite these sources:',
                'allow_external_fallback': False,
                'approve_tool_calls': False
            }
        }
        if config_file:
            if not os.path.isfile(config_file):
                raise FileNotFoundError(f"Configuration file '{config_file}' not found.")
            with open(config_file, 'r', encoding='utf-8') as file:
                user_config = yaml.safe_load(file) or {}
            # Merge user_config into configuration values
            self.prompts_dir = os.path.join(base_dir, user_config.get('prompts_dir', 'prompts'))
            self.input_dir = os.path.join(base_dir, user_config.get('input_dir', 'input'))
            self.output_dir = os.path.join(base_dir, user_config.get('output_dir', 'output'))
            self.provider = user_config.get('provider', 'OpenAI')
            self.openai = self.ProviderConfig(user_config.get('openai', {}), 'openai')
            self.openrouter = self.ProviderConfig(user_config.get('openrouter', {}), 'openrouter')
            self.google = self.ProviderConfig(user_config.get('google', {}), 'google')
            self.grounding = self.GroundingConfig(user_config.get('grounding', default_config.get('grounding', {})))
        else:
            self.prompts_dir = default_config['prompts_dir']
            self.input_dir = default_config['input_dir']
            self.output_dir = default_config['output_dir']
            self.provider = default_config['provider']
            self.openai = self.ProviderConfig(default_config['openai'], 'openai')
            self.openrouter = self.ProviderConfig(default_config['openrouter'], 'openrouter')
            self.google = self.ProviderConfig(default_config['google'], 'google')
            self.grounding = self.GroundingConfig(default_config.get('grounding', {}))

    class ProviderConfig:
        def __init__(self, config, provider_name=None):
            # Read API keys exclusively from environment variables for safety.
            if provider_name == 'openai':
                self.api_key = os.getenv('OPENAI_API_KEY', '').strip()
            elif provider_name == 'openrouter':
                self.api_key = os.getenv('OPENROUTER_API_KEY', '').strip()
            elif provider_name == 'google':
                # Read Google API key from environment (GOOGLE_API_KEY)
                self.api_key = os.getenv('GOOGLE_API_KEY', '').strip()
            else:
                self.api_key = ''.strip()
            self.model = config.get('model', '')
            self.temperature = config.get('temperature', 0.7)
            self.max_tokens = config.get('max_tokens', 1500)

    class GroundingConfig:
        def __init__(self, config):
            # config is expected to be a dict-like mapping
            cfg = config or {}
            self.enabled = cfg.get('enabled', False)
            self.provider = cfg.get('provider', 'openai')
            self.max_results = cfg.get('max_results', 3)
            self.search_prompt = cfg.get('search_prompt', 'Incorporate and cite these sources:')
            self.allow_external_fallback = cfg.get('allow_external_fallback', False)
            self.approve_tool_calls = cfg.get('approve_tool_calls', False)


# PromptManager class
class PromptManager:
    def __init__(self, prompts_dir, logger=None):
        self.prompts_dir = prompts_dir
        self.logger = logger

    def load_prompts(self, prompt_files):
        prompts = []
        for prompt_file in prompt_files:
            try:
                full_path = os.path.join(self.prompts_dir, prompt_file)
                with open(full_path, 'r', encoding='utf-8') as file:
                    content = file.read()
                    prompts.append(content)
            except Exception:
                if self.logger:
                    self.logger.exception(f"Error reading prompt file '{prompt_file}'")
        return "\n".join(prompts)


# FileHandler class
class FileHandler:
    def __init__(self, input_dir, output_dir, logger=None):
        self.input_dir = input_dir
        self.output_dir = output_dir
        self.logger = logger

    def list_input_files(self):
        try:
            files = []
            for root, _, filenames in os.walk(self.input_dir):
                for fname in filenames:
                    full = os.path.join(root, fname)
                    rel = os.path.relpath(full, self.input_dir)
                    files.append(rel)
            return files
        except Exception:
            if self.logger:
                self.logger.exception(f"Error listing input files in directory '{self.input_dir}'")
            return []

    def read_file(self, file_path):
        try:
            if self.logger:
                self.logger.debug(f"Reading file '{file_path}'")
            with open(file_path, 'r', encoding='utf-8') as file:
                content = file.read()
            if self.logger:
                self.logger.debug(f"Read file '{file_path}', length {len(content)}")
            return content
        except Exception:
            if self.logger:
                self.logger.exception(f"Error reading file '{file_path}'")
            return ""

    def write_file(self, file_path, content):
        try:
            if self.logger:
                self.logger.debug(f"Writing file '{file_path}' with content length {len(content)}")
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
            if self.logger:
                self.logger.debug(f"Wrote file '{file_path}', length {len(content)}")
        except Exception:
            if self.logger:
                self.logger.exception(f"Error writing to file '{file_path}'")


# APIClient class
class APIClient:
    def __init__(self, config, max_retries=3, backoff_factor=2, logger=None):
        self.config = config
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor
        self.logger = logger

    def send_prompt(self, system_prompt, user_prompt):
        """
        Send the prompt to the configured provider. If grounding is enabled in the
        configuration and the selected model supports provider-side grounding, attempt
        a provider-side grounding call via the Grounder. If grounding is unavailable
        and external fallback is permitted by configuration/options, fall back to the
        standard chat completion call.
        """
        provider = self.config.provider
        # Resolve provider-specific credentials and defaults
        if provider.lower() == "openai":
            api_key = self.config.openai.api_key
            model = self.config.openai.model
            temperature = self.config.openai.temperature
            max_tokens = self.config.openai.max_tokens
            api_base = None  # Use default OpenAI API base
        elif provider.lower() == "openrouter":
            api_key = self.config.openrouter.api_key
            model = self.config.openrouter.model
            temperature = self.config.openrouter.temperature
            max_tokens = self.config.openrouter.max_tokens
            api_base = "https://openrouter.ai/api/v1"
        elif provider.lower() == "google":
            api_key = self.config.google.api_key
            model = self.config.google.model
            temperature = self.config.google.temperature
            max_tokens = self.config.google.max_tokens
            api_base = None
        else:
            if self.logger:
                self.logger.error(f"Unknown API provider: {provider}.")
            raise RuntimeError(f"Unknown API provider: {provider}")

        if not api_key or api_key == 'DUMMY_API_KEY':
            if self.logger:
                self.logger.error(f"No valid API key for {provider}.")
            raise RuntimeError(f"No valid API key configured for {provider}. Please set the API key in configuration or environment variables.")

        # Attempt provider-side grounding if configured
        grounding_cfg = getattr(self.config, 'grounding', None)
        grounder = Grounder(self.config, logger=self.logger)
        if grounding_cfg and getattr(grounding_cfg, 'enabled', False):
            if self.logger:
                self.logger.info("Grounding enabled in configuration; attempting provider-side grounding.")
            grounding_options = {
                "max_results": getattr(grounding_cfg, 'max_results', None),
                "search_prompt": getattr(grounding_cfg, 'search_prompt', None),
                "allow_external_fallback": getattr(grounding_cfg, 'allow_external_fallback', False)
            }
            try:
                grounding_result = grounder.run(system_prompt, user_prompt, grounding_options=grounding_options)
                if grounding_result and grounding_result.get("method") == "provider-tool" and grounding_result.get("text"):
                    if self.logger:
                        self.logger.debug("Provider-side grounding succeeded; returning grounded text.")
                    return grounding_result.get("text")
                # If grounding returned method none with allow_external_fallback true, fall through to provider-specific normal call
                allow_fallback = grounding_result.get("tool_details", {}).get("allow_external_fallback", False) if isinstance(grounding_result, dict) else False
                if grounding_result.get("tool_details", {}).get("error") == "provider_grounding_unavailable" and not allow_fallback:
                    if self.logger:
                        self.logger.warning("Provider-side grounding unavailable and external fallback not permitted. Proceeding without grounding.")
                    # Continue to provider-specific normal call below (no grounding)
                else:
                    if grounding_result.get("tool_details", {}).get("error"):
                        if self.logger:
                            self.logger.warning(f"Grounding tool returned error: {grounding_result.get('tool_details')}. Falling back to provider-specific standard API call.")
            except Exception as e:
                if self.logger:
                    self.logger.exception(f"Exception while attempting provider-side grounding: {e}. Falling back to provider-specific standard API call.")

        # Standard (non-grounded) API call (chat completion)
        client = OpenAI(api_key=api_key, base_url=api_base)
        messages = [
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": user_prompt}
        ]
        if self.logger:
            self.logger.debug(
                f"API request payload ({provider}): model={model}, temperature={temperature}, max_tokens={max_tokens}"
            )
        try:
            response = client.chat.completions.create(
                model=model,
                messages=messages,
                temperature=temperature,
                max_tokens=max_tokens
            )
            if self.logger:
                self.logger.debug(f"API raw response ({provider}): {response}")
            result = response.choices[0].message.content.strip()
            if self.logger:
                self.logger.debug(f"API response content ({provider}): {result}")
            return result
        except Exception as e:
            if self.logger:
                self.logger.exception(f"{provider} API error: {e}")
            # Re-raise so the caller can handle the error and we never return fake data
            raise


# Function to create default prompt file if not exists
def create_default_prompt(prompts_dir, logger=None):
    default_prompt_path = os.path.join(prompts_dir, 'standard_prompt.txt')
    if not os.path.isfile(default_prompt_path):
        default_prompt = (
            "You are ChatGPT, a large language model trained by OpenAI. "
            "Provide clear and concise answers to the user's queries."
        )
        try:
            os.makedirs(os.path.dirname(default_prompt_path), exist_ok=True)
            with open(default_prompt_path, 'w', encoding='utf-8') as file:
                file.write(default_prompt)
            if logger:
                logger.info(f"Created default prompt at {default_prompt_path}")
        except Exception:
            if logger:
                logger.exception(f"Error creating default prompt file '{default_prompt_path}'")


def main():
    parser = argparse.ArgumentParser(
        description='GPT Processor Main Application',
        epilog='Enable --verbose for debug logs.'
    )
    parser.add_argument('--config', type=str, help='Path to configuration file.')
    parser.add_argument('--log_file', type=str, help='Path to log file.')
    parser.add_argument('--verbose', action='store_true', help='Enable verbose logging.')
    parser.add_argument('--prompt', type=str, nargs='+', help='List of prompt files.')
    parser.add_argument('--input_dir', type=str, help='Directory for input files.')
    parser.add_argument('--output_dir', type=str, help='Directory for output files.')
    parser.add_argument('--model', type=str, help='OpenAI model to use.')
    parser.add_argument('--temperature', type=float, help='Temperature setting for the OpenAI model.')
    parser.add_argument('--max_tokens', type=int, help='Maximum number of tokens for the OpenAI model.')
    args = parser.parse_args()

    # Set log level based on verbosity
    log_level = logging.DEBUG if args.verbose else logging.INFO

    # Determine execution directory
    exec_dir = os.path.dirname(os.path.abspath(__file__))

    # Create a logs subdirectory and a timestamped directory inside it for logs
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(exec_dir, 'logs', current_time)
    ensure_directory(log_dir)

    # Set log file path
    log_file_path = os.path.join(log_dir, 'gpt_processor.log') if not args.log_file else args.log_file

    # Setup logger
    global logger
    logger = setup_logger(log_level=log_level, log_file=log_file_path)
    logger.debug(f"Parsed CLI args: {vars(args)}")

    try:
        # Load configuration
        if args.config:
            config_file = args.config
        else:
            input_dir_arg = args.input_dir if args.input_dir else None
            potential_config_paths = [os.path.join(exec_dir, 'default_config.yaml')]
            if input_dir_arg:
                potential_config_paths.append(os.path.join(os.path.dirname(input_dir_arg), 'default_config.yaml'))
            config_file = None
            for path in potential_config_paths:
                if os.path.isfile(path):
                    config_file = path
                    break

        try:
            if config_file:
                config = Config(config_file, base_dir=exec_dir)
                logger.debug(f"Configuration loaded from {config_file}: {config.__dict__}")
            else:
                logger.warning("No configuration file found. Using default configuration.")
                config = Config(base_dir=exec_dir)
                logger.debug(f"Default configuration: {config.__dict__}")
        except Exception:
            logger.exception("Error loading configuration")
            config = Config(base_dir=exec_dir)

        # Ensure necessary directories exist
        ensure_directory(config.prompts_dir)
        ensure_directory(config.input_dir)
        ensure_directory(config.output_dir)

        # If no prompt files provided on the CLI, try to list prompts in prompts_dir
        if args.prompt:
            prompt_files = args.prompt
        else:
            try:
                prompt_files = os.listdir(config.prompts_dir)
            except Exception:
                prompt_files = []
        if not prompt_files:
            # create a default prompt if none exist
            create_default_prompt(config.prompts_dir, logger)
            prompt_files = os.listdir(config.prompts_dir)

        # Override config with CLI arguments if provided
        input_dir = args.input_dir if args.input_dir else config.input_dir
        output_dir = args.output_dir if args.output_dir else config.output_dir

        # Determine model based on provider from config, overridden by CLI arg
        if args.model:
            model = args.model
        elif config.provider == "OpenAI":
            model = config.openai.model
        elif config.provider == "OpenRouter":
            model = config.openrouter.model
        else:
            model = "gpt-4"  # Default model if provider is unknown or not set

        temperature = args.temperature if args.temperature else config.openai.temperature
        max_tokens = args.max_tokens if args.max_tokens else config.openai.max_tokens

        # Log paths
        logger.debug(f"Prompt files: {prompt_files}")
        logger.debug(f"Input directory: {input_dir}")
        logger.debug(f"Output directory: {output_dir}")

        for path in [input_dir, output_dir] + [os.path.join(config.prompts_dir, p) for p in prompt_files]:
            if not os.path.exists(path):
                logger.error(f"Path does not exist: {path}")

        # Load and combine prompts
        prompt_manager = PromptManager(config.prompts_dir, logger=logger)
        system_prompt = prompt_manager.load_prompts(prompt_files)
        logger.debug(f"System prompt content:\n{system_prompt}")

        # Initialize file handler and API client
        file_handler = FileHandler(input_dir, output_dir, logger=logger)
        api_client = APIClient(config, max_retries=3, backoff_factor=2, logger=logger)

        # List input files
        input_files = file_handler.list_input_files()
        logger.debug(f"Input files: {input_files}")
        if not input_files:
            logger.info("No input files found. Exiting.")
            sys.exit(0)

        # Process files sequentially
        for idx, input_file in enumerate(input_files):
            process_file(os.path.join(input_dir, input_file), file_handler, api_client, system_prompt, logger)
            # Respectful delay between files (configurable later)
            # Only sleep between files, not after the last one
            if idx < len(input_files) - 1:
                time.sleep(60)

    except Exception:
        logger.exception("Unhandled exception in main")
        sys.exit(1)


def process_file(input_file, file_handler, api_client, system_prompt, logger):
    logger.debug(f"Processing file: {input_file}")
    user_prompt = file_handler.read_file(input_file)
    logger.debug(f"User prompt length for '{input_file}': {len(user_prompt)}")
    if not user_prompt:
        logger.error(f"User prompt is empty for file '{input_file}'")
        return
    try:
        response = api_client.send_prompt(system_prompt, user_prompt)
        # Log request and response to console
        logger.info(f"System prompt for '{os.path.basename(input_file)}':\n{system_prompt}")
        logger.info(f"User prompt for '{os.path.basename(input_file)}':\n{user_prompt}")
        logger.info(f"Response for '{os.path.basename(input_file)}':\n{response}")
        # Compute relative path from input_dir to preserve folder structure in output_dir
        rel = os.path.relpath(input_file, file_handler.input_dir)
        out_subdir = os.path.dirname(rel)
        out_dir = os.path.join(file_handler.output_dir, out_subdir) if out_subdir else file_handler.output_dir
        ensure_directory(out_dir)
        output_file = os.path.join(out_dir, f"response_{os.path.basename(input_file)}")
        file_handler.write_file(output_file, response)
        if logger:
            logger.info(f"Wrote response to '{output_file}'")
    except Exception:
        logger.exception(f"Error processing file '{input_file}'")
    finally:
        # small pause after processing (configurable if needed)
        time.sleep(1)


if __name__ == "__main__":
    main()
