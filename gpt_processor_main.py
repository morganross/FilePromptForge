#!/usr/bin/env python3
"""
GPT Processor Main Application

Features:
- Combine multiple prompt files into a single system prompt.
- Process multiple input files concurrently.
- Save AI-generated responses to output directory.
- Comprehensive logging to console and optional log file.
"""

import os
import argparse
import logging
import sys
import time
from concurrent.futures import ThreadPoolExecutor
import openai
from openai.error import OpenAIError, RateLimitError
from datetime import datetime

# Attempt to import required packages and handle missing dependencies
try:
    import yaml
    from dotenv import load_dotenv
except ImportError as e:
    missing_package = str(e).split("'")[1]
    print(f"Error: Missing required package '{missing_package}'.")
    print("Please install all dependencies using:")
    print("    pip install openai PyYAML python-dotenv")
    sys.exit(1)

# Setting up the logger
def setup_logger(log_level=logging.INFO, log_file=None):
    logger = logging.getLogger('gpt_processor')
    logger.setLevel(log_level)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')

    # Console handler
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
        os.makedirs(directory)

# Configuration class
class Config:
    def __init__(self, config_file=None, base_dir=None):
        if base_dir is None:
            base_dir = os.path.dirname(os.path.abspath(__file__))
        load_dotenv()  # Load environment variables from .env if present
        default_config = {
            'prompts_dir': os.path.join(base_dir, 'prompts'),
            'input_dir': os.path.join(base_dir, 'input'),
            'output_dir': os.path.join(base_dir, 'output'),
            'openai': {
                'api_key': os.getenv('OPENAI_API_KEY'),
                'model': 'gpt-4',
                'temperature': 0.7,
                'max_tokens': 1500
            }
        }
        if config_file:
            if not os.path.isfile(config_file):
                raise FileNotFoundError(f"Configuration file '{config_file}' not found.")
            with open(config_file, 'r') as file:
                user_config = yaml.safe_load(file)
            # Merge user_config into default_config
            self.prompts_dir = os.path.join(base_dir, user_config.get('prompts_dir', 'prompts'))
            self.input_dir = os.path.join(base_dir, user_config.get('input_dir', 'input'))
            self.output_dir = os.path.join(base_dir, user_config.get('output_dir', 'output'))
            self.openai = self.OpenAI(user_config.get('openai', {}))
        else:
            self.prompts_dir = default_config['prompts_dir']
            self.input_dir = default_config['input_dir']
            self.output_dir = default_config['output_dir']
            self.openai = self.OpenAI(default_config['openai'])

    class OpenAI:
        def __init__(self, config):
            self.api_key = config.get('api_key', 'DUMMY_API_KEY')
            self.model = config.get('model', 'gpt-4')
            self.temperature = config.get('temperature', 0.7)
            self.max_tokens = config.get('max_tokens', 1500)

# PromptManager class
class PromptManager:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir

    def load_prompts(self, prompt_files):
        prompts = []
        for prompt_file in prompt_files:
            try:
                # Ensure full path is used
                full_path = os.path.join(self.prompts_dir, prompt_file)
                with open(full_path, 'r', encoding='utf-8') as file:
                    prompts.append(file.read())
            except Exception as e:
                logger.error(f"Error reading prompt file '{prompt_file}': {e}")
        return "\n".join(prompts)

# FileHandler class
class FileHandler:
    def __init__(self, input_dir, output_dir):
        self.input_dir = input_dir
        self.output_dir = output_dir

    def list_input_files(self):
        try:
            return [f for f in os.listdir(self.input_dir) if os.path.isfile(os.path.join(self.input_dir, f))]
        except Exception as e:
            logger.error(f"Error listing input files in directory '{self.input_dir}': {e}")
            return []

    def read_file(self, file_path):
        try:
            with open(file_path, 'r', encoding='utf-8') as file:
                return file.read()
        except Exception as e:
            logger.error(f"Error reading file '{file_path}': {e}")
            return ""

    def write_file(self, file_path, content):
        try:
            with open(file_path, 'w', encoding='utf-8') as file:
                file.write(content)
        except Exception as e:
            logger.error(f"Error writing to file '{file_path}': {e}")

# APIClient class
class APIClient:
    def __init__(self, api_key, model, temperature, max_tokens, max_retries=3, backoff_factor=2):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens
        self.max_retries = max_retries
        self.backoff_factor = backoff_factor

    def send_prompt(self, system_prompt, user_prompt, logger):
        # If no API key is provided, generate a mock response
        if not self.api_key or self.api_key == 'DUMMY_API_KEY':
            logger.warning("No valid API key. Generating mock response.")
            return f"Mock response to: {user_prompt}"
        
        try:
            openai.api_key = self.api_key
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return response.choices[0].message['content'].strip()
        except Exception as e:
            logger.error(f"OpenAI API error: {e}")
            logger.warning("Generating mock response due to API error.")
            return f"Mock response to: {user_prompt}"

# Function to create default prompt file if not exists
def create_default_prompt(prompts_dir):
    default_prompt_path = os.path.join(prompts_dir, 'standard_prompt.txt')
    if not os.path.isfile(default_prompt_path):
        default_prompt = (
            "You are ChatGPT, a large language model trained by OpenAI. "
            "Provide clear and concise answers to the user's queries."
        )
        try:
            with open(default_prompt_path, 'w', encoding='utf-8') as file:
                file.write(default_prompt)
        except Exception as e:
            logger.error(f"Error creating default prompt file '{default_prompt_path}': {e}")

def main():
    parser = argparse.ArgumentParser(description='GPT Processor Main Application')

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

    # Create a directory named after the current time for logs
    current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
    log_dir = os.path.join(exec_dir, f"logs_{current_time}")
    ensure_directory(log_dir)

    # Set log file path
    log_file_path = os.path.join(log_dir, 'gpt_processor.log')

    # Setup logger
    logger = setup_logger(log_level=log_level, log_file=log_file_path)

    # Load configuration
    # Try to load configuration, but don't fail if config file doesn't exist
    # First, check if a config file was explicitly provided
    if args.config:
        config_file = args.config
    else:
        # Determine input directory first
        input_dir = args.input_dir if args.input_dir else None
        
        # Check for config in the installation directory (input_dir's parent)
        potential_config_paths = [
            os.path.join(exec_dir, 'default_config.yaml'),  # script directory
        ]
        
        # If input_dir is provided, add its parent directory to potential config paths
        if input_dir:
            potential_config_paths.append(os.path.join(os.path.dirname(input_dir), 'default_config.yaml'))
        
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
    except Exception as e:
        logger.error(f"Error loading configuration: {e}")
        config = Config(base_dir=exec_dir)

    # Override config with CLI arguments if provided
    prompt_files = args.prompt if args.prompt else os.listdir(config.prompts_dir)
    input_dir = args.input_dir if args.input_dir else config.input_dir
    output_dir = args.output_dir if args.output_dir else config.output_dir
    model = args.model if args.model else config.openai.model
    temperature = args.temperature if args.temperature else config.openai.temperature
    max_tokens = args.max_tokens if args.max_tokens else config.openai.max_tokens

    # Log paths and check if they exist
    logger.debug(f"Prompt files: {prompt_files}")
    logger.debug(f"Input directory: {input_dir}")
    logger.debug(f"Output directory: {output_dir}")
    for path in [input_dir, output_dir] + prompt_files:
        if not os.path.exists(path):
            logger.error(f"Path does not exist: {path}")

    # Ensure necessary directories exist
    ensure_directory(input_dir)
    ensure_directory(output_dir)

    # Load and combine prompts
    prompt_manager = PromptManager(config.prompts_dir)
    system_prompt = prompt_manager.load_prompts(prompt_files)

    # Initialize file handler and API client
    file_handler = FileHandler(input_dir, output_dir)
    api_client = APIClient(config.openai.api_key, model, temperature, max_tokens)

    # List input files
    input_files = file_handler.list_input_files()
    logger.debug(f"Input files: {input_files}")
    if not input_files:
        logger.info("No input files found. Exiting.")
        sys.exit(0)

    # Process files sequentially with a delay
    for input_file in input_files:
        process_file(os.path.join(input_dir, input_file), file_handler, api_client, system_prompt, logger)
        time.sleep(60)  # Delay to ensure only one file is processed per minute

def process_file(input_file, file_handler, api_client, system_prompt, logger):
    user_prompt = file_handler.read_file(input_file)
    if not user_prompt:
        logger.error(f"User prompt is empty for file '{input_file}'")
        return
    try:
        response = api_client.send_prompt(system_prompt, user_prompt, logger)
        output_file = os.path.join(file_handler.output_dir, f"response_{os.path.basename(input_file)}")
        file_handler.write_file(output_file, response)
    except Exception as e:
        logger.error(f"Error processing file '{input_file}': {e}")
    finally:
        # Delay to ensure only one file is processed per minute
        time.sleep(60)

if __name__ == "__main__":
    main()
