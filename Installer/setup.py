import os
import argparse
from setuptools import setup, find_packages
import openai
import yaml
import logging


# Setting up the logger
def setup_logger():
    logger = logging.getLogger('gpt_processor')
    logger.setLevel(logging.INFO)
    ch = logging.StreamHandler()
    ch.setLevel(logging.INFO)
    formatter = logging.Formatter('%(asctime)s - %(name)s - %(levelname)s - %(message)s')
    ch.setFormatter(formatter)
    logger.addHandler(ch)
    return logger


# Ensure directory exists
def ensure_directory(directory):
    if not os.path.exists(directory):
        os.makedirs(directory)


# Configuration class
class Config:
    def __init__(self):
        self.prompts_dir = './prompts/'
        self.input_dir = './input/'
        self.output_dir = './output/'
        self.openai = self.OpenAI()

    class OpenAI:
        def __init__(self):
            self.api_key = 'your_openai_api_key'


# PromptManager class
class PromptManager:
    def __init__(self, prompts_dir):
        self.prompts_dir = prompts_dir

    def load_prompt(self, prompt_file):
        with open(prompt_file, 'r') as file:
            return file.read()


# FileHandler class
class FileHandler:
    def __init__(self, input_dir, output_dir):
        self.input_dir = input_dir
        self.output_dir = output_dir

    def list_input_files(self):
        return [os.path.join(self.input_dir, f) for f in os.listdir(self.input_dir) if os.path.isfile(os.path.join(self.input_dir, f))]

    def read_file(self, file_path):
        with open(file_path, 'r') as file:
            return file.read()

    def write_output(self, input_file, content):
        output_file = os.path.join(self.output_dir, os.path.basename(input_file))
        with open(output_file, 'w') as file:
            file.write(content)
        return output_file


# APIClient class
class APIClient:
    def __init__(self, api_key, model, temperature, max_tokens):
        self.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def send_prompt(self, system_prompt, user_prompt):
        openai.api_key = self.api_key
        response = openai.Completion.create(
            engine=self.model,
            prompt=f"{system_prompt}\n\n{user_prompt}",
            temperature=self.temperature,
            max_tokens=self.max_tokens
        )
        return response.choices[0].text.strip()


# CLI main function
def main():
    parser = argparse.ArgumentParser(description='ChatGPT Prompt Processor')
    parser.add_argument('--prompt', type=str, help='Specify a prompt file to use.')
    parser.add_argument('--input_dir', type=str, help='Specify input directory.')
    parser.add_argument('--output_dir', type=str, help='Specify output directory.')
    parser.add_argument('--model', type=str, default='gpt-4', help='Specify the OpenAI model to use.')
    parser.add_argument('--temperature', type=float, default=0.7, help='Set the temperature for the API.')
    parser.add_argument('--max_tokens', type=int, default=1500, help='Set the maximum tokens for the API.')
    args = parser.parse_args()

    # Load configuration
    config = Config()

    # Override config with CLI arguments if provided
    prompt_file = args.prompt if args.prompt else os.path.join(config.prompts_dir, 'standard_prompt.txt')
    input_dir = args.input_dir if args.input_dir else config.input_dir
    output_dir = args.output_dir if args.output_dir else config.output_dir
    model = args.model
    temperature = args.temperature
    max_tokens = args.max_tokens

    # Setup logger
    logger = setup_logger()

    # Ensure output directory exists
    ensure_directory(output_dir)

    # Initialize components
    prompt_manager = PromptManager(config.prompts_dir)
    file_handler = FileHandler(input_dir, output_dir)
    api_client = APIClient(config.openai.api_key, model, temperature, max_tokens)

    # Load prompt
    system_prompt = prompt_manager.load_prompt(prompt_file)

    # Process input files
    input_files = file_handler.list_input_files()
    for input_file in input_files:
        try:
            user_prompt = file_handler.read_file(input_file)
            response = api_client.send_prompt(system_prompt, user_prompt)
            output_filename = file_handler.write_output(input_file, response)
            logger.info(f"Processed {input_file} and saved to {output_filename}")
        except Exception as e:
            logger.error(f"Error processing {input_file}: {e}")


if __name__ == '__main__':
    main()


# Setup script for the package
setup(
    name='gpt_processor',
    version='1.0.0',
    description='A versatile tool to process text files using OpenAI ChatGPT API.',
    author='Your Name',
    author_email='your.email@example.com',
    packages=find_packages(),
    install_requires=[
        'openai',
        'PyYAML',
    ],
    entry_points={
        'console_scripts': [
            'gpt-processer=gpt_processor:main',
        ],
    },
    classifiers=[
        'Programming Language :: Python :: 3',
        'Operating System :: Microsoft :: Windows',
    ],
    python_requires='>=3.6',
)
