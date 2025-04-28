todo

Cycle through API key

add prepend folder, write output to pretend folder check box
(instructed to make list of reivisions, reads files, outputs list to prepend. intructions to carryout those revisons, reads prepend file then reads file again, outputs to output

need not be a prepend folder, could do more robust inout handling, define behaviour for adding multiple folders to single run

erse completed input files (good for stopping mid way)




























--config: Path to the configuration file.

Usage: --config <path_to_config_file>
Example: --config config.yaml
--prompt: List of prompt files.

Usage: --prompt <prompt_file1> <prompt_file2> ...
Example: --prompt prompt1.txt prompt2.txt
--input_dir: Directory for input files.

Usage: --input_dir <path_to_input_directory>
Example: --input_dir ./input
--output_dir: Directory for output files.

Usage: --output_dir <path_to_output_directory>
Example: --output_dir ./output
--model: OpenAI model to use.

Usage: --model <model_name>
Example: --model gpt-4
--temperature: Temperature setting for the OpenAI model.

Usage: --temperature <temperature_value>
Example: --temperature 0.7
--max_tokens: Maximum number of tokens for the OpenAI model.

Usage: --max_tokens <max_tokens_value>
Example: --max_tokens 1500
--verbose: Enable verbose logging.

Usage: --verbose
Example: --verbose
--log_file: Path to log file.

Usage: --log_file <path_to_log_file>
Example: --log_file gpt_processor.log# FilePromtForge01
# GPT Processor Application

## Overview

This repository contains scripts for installing and running a GPT processor application. The application processes input files by sending prompts to the OpenAI API and stores the responses in the output directory.

## Features

### GPT Processor Installer

- **Directory Creation**: Creates necessary directories (`prompts/`, `input/`, `output/`).
- **Executable Copying**: Copies the main application executable to the installation directory.
- **Default Prompt File**: Creates a default prompt file if it doesn't exist.
- **System PATH**: Optionally adds the installation directory to the system PATH.
- **Logging**: Provides user-friendly logging and error handling.

### GPT Processor Main Application

- **Prompt Management**: Combines multiple prompt files into a single system prompt.
- **File Processing**: Processes multiple input files concurrently and saves AI-generated responses to the output directory.
- **Logging**: Comprehensive logging to console and optional log file.
- **Concurrency**: Utilizes `ThreadPoolExecutor` for concurrent processing of input files.

## Installation

1. **Clone the Repository**:
    ```sh
    git clone https://github.com/morganross/FilePromtForge01.git
    cd FilePromtForge01
    ```

2. **Install Dependencies**:
    ```sh
    pip install -r requirements.txt
    ```

3. **Run the Installer**:
    ```sh
    python gpt_processor_installer.py --main_executable path/to/gpt_processor.exe
    ```
    Options:
    - `--install_dir`: Directory to install GPT Processor.
    - `--add_to_path`: Add the installation directory to the system PATH.
    - `--log_file`: Path to the log file.
    - `--verbose`: Enable verbose logging.

## Usage

1. **Prepare Input Files**: Place the files you want to process in the `input` directory.

2. **Run the Processor**:
    ```sh
    python gpt_processor_main.py
    ```
    Options:
    - `--prompt`: Specify one or more prompt files to use.
    - `--input_dir`: Specify input directory.
    - `--output_dir`: Specify output directory.
    - `--model`: Specify the OpenAI model to use.
    - `--temperature`: Set the temperature for the API.
    - `--max_tokens`: Set the maximum tokens for the API.
    - `--config`: Path to configuration file.
    - `--log_file`: Path to the log file.
    - `--verbose`: Enable verbose logging.

## Configuration

The application can be configured using a YAML configuration file or environment variables. Example configuration:

```yaml
openai:
  api_key: your_openai_api_key
  model: gpt-4
  temperature: 0.7
  max_tokens: 1500
# FilePromptForge01

