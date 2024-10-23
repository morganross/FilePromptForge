Certainly! Below is comprehensive **documentation** for your generalized ChatGPT Python script, focusing on **how to include it in other scripts** and providing **practical examples**. This documentation is designed to help you integrate the ChatGPT functionality seamlessly into various workflows, enhancing automation and productivity.

---

# **ChatGPT Prompt Processor Documentation**

## **Table of Contents**

1. [Overview](#overview)
2. [Setup and Installation](#setup-and-installation)
3. [Project Structure](#project-structure)
4. [Configuration](#configuration)
5. [Using the Script Directly](#using-the-script-directly)
6. [Integrating with Other Scripts](#integrating-with-other-scripts)
    - [Importing Modules](#importing-modules)
    - [Example Use Cases](#example-use-cases)
        - [1. Language Translation](#1-language-translation)
        - [2. Style Conversion](#2-style-conversion)
        - [3. Summarization of Documents](#3-summarization-of-documents)
        - [4. Automated Email Drafting](#4-automated-email-drafting)
7. [Advanced Features](#advanced-features)
8. [Best Practices](#best-practices)
9. [Troubleshooting](#troubleshooting)
10. [Extending the Script](#extending-the-script)
11. [Support and Contributions](#support-and-contributions)

---

## **Overview**

The **ChatGPT Prompt Processor** is a versatile Python script designed to automate interactions with the OpenAI ChatGPT API. It facilitates reading, processing, and writing files based on predefined prompts, making it an invaluable tool for tasks such as content generation, translation, style conversion, summarization, and more.

**Key Features:**

- **Prompt Management:** Load and manage multiple prompt templates.
- **File Handling:** Read from and write to various directories and file formats.
- **API Interaction:** Interface with OpenAI's ChatGPT API with customizable parameters.
- **Modularity:** Reusable components for easy integration.
- **Logging:** Comprehensive logging for monitoring and debugging.
- **Configuration Management:** Easily customizable via configuration files and command-line arguments.
- **Command-Line Interface (CLI):** Flexible usage through the command line.

---

## **Setup and Installation**

### **1. Clone the Repository**

```bash
git clone https://github.com/yourusername/chatgpt-prompt-processor.git
cd chatgpt-prompt-processor
```

### **2. Create a Virtual Environment (Optional but Recommended)**

```bash
python -m venv venv
source venv/bin/activate  # On Windows: venv\Scripts\activate
```

### **3. Install Dependencies**

```bash
pip install -r requirements.txt
```

**`requirements.txt`**

```plaintext
openai
PyYAML
```

### **4. Configure the Script**

Edit the `config.yaml` file to set your OpenAI API key and directories.

**`config.yaml`**

```yaml
openai:
  api_key: "your-api-key"

directories:
  prompts: "prompts/"
  input: "input_files/"
  output: "output_files/"

api:
  model: "gpt-4"
  temperature: 0.7
  max_tokens: 1500
```

*Ensure that the directories specified (`prompts/`, `input_files/`, `output_files/`) exist or will be created by the script.*

---

## **Project Structure**

```
project/
├── prompts/
│   └── standard_prompt.txt
├── input_files/
│   ├── file1.txt
│   ├── file2.txt
│   └── ...
├── output_files/
│   ├── file1_response.txt
│   ├── file2_response.txt
│   └── ...
├── config.yaml
├── main.py
├── prompt_manager.py
├── file_handler.py
├── api_client.py
├── logger.py
├── cli.py
├── utils.py
├── requirements.txt
└── README.md
```

---

## **Configuration**

The script uses a `config.yaml` file to manage settings, including API keys, directory paths, and API parameters. You can also override these settings using command-line arguments when running the script.

**`config.yaml`**

```yaml
openai:
  api_key: "your-api-key"

directories:
  prompts: "prompts/"
  input: "input_files/"
  output: "output_files/"

api:
  model: "gpt-4"
  temperature: 0.7
  max_tokens: 1500
```

- **openai.api_key:** Your OpenAI API key.
- **directories.prompts:** Path to the directory containing prompt templates.
- **directories.input:** Path to the directory containing input files.
- **directories.output:** Path to the directory where output files will be saved.
- **api.model:** The OpenAI model to use (e.g., "gpt-4").
- **api.temperature:** Sampling temperature for the API (controls randomness).
- **api.max_tokens:** Maximum number of tokens in the API response.

---

## **Using the Script Directly**

To execute the script directly from the command line, use:

```bash
python main.py
```

**Command-Line Arguments:**

- `--prompt`: Specify a specific prompt file to use.
- `--input_dir`: Specify a different input directory.
- `--output_dir`: Specify a different output directory.
- `--model`: Specify a different OpenAI model.
- `--temperature`: Set the temperature for the API.
- `--max_tokens`: Set the maximum tokens for the API.
- `--log_file`: Specify a log file path.

**Example:**

```bash
python main.py --prompt custom_prompt.txt --input_dir my_inputs/ --output_dir my_outputs/ --model gpt-3.5-turbo --temperature 0.5 --max_tokens 1000 --log_file my_log.log
```

---

## **Integrating with Other Scripts**

One of the strengths of the **ChatGPT Prompt Processor** is its modular design, allowing you to integrate its functionalities into other Python scripts seamlessly. Below, we'll explore **how to include it in other scripts** and provide **practical examples**.

### **Importing Modules**

To use the functionalities of the ChatGPT Prompt Processor in another script, you can import the necessary classes from its modules.

**Example Directory Structure:**

```
project/
├── chatgpt_processor/
│   ├── __init__.py
│   ├── config.py
│   ├── logger.py
│   ├── prompt_manager.py
│   ├── file_handler.py
│   ├── api_client.py
│   ├── utils.py
│   └── cli.py
├── main.py
├── your_other_script.py
├── config.yaml
├── prompts/
├── input_files/
├── output_files/
└── requirements.txt
```

**`your_other_script.py`**

```python
from chatgpt_processor.config import Config
from chatgpt_processor.logger import setup_logger
from chatgpt_processor.prompt_manager import PromptManager
from chatgpt_processor.file_handler import FileHandler
from chatgpt_processor.api_client import APIClient
from chatgpt_processor.utils import ensure_directory

def process_files_with_chatgpt():
    # Load configuration
    config = Config()

    # Setup logger
    logger = setup_logger()

    # Ensure output directory exists
    ensure_directory(config.output_dir)

    # Initialize components
    prompt_manager = PromptManager(config.prompts_dir)
    file_handler = FileHandler(config.input_dir, config.output_dir)
    api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

    # Load a specific prompt
    system_prompt = prompt_manager.load_prompt('standard_prompt.txt')

    # List input files
    input_files = file_handler.list_input_files()

    for input_file in input_files:
        try:
            user_prompt = file_handler.read_file(input_file)
            logger.info(f"Processing file: {input_file}")

            # Send prompt to API
            response = api_client.send_prompt(system_prompt, user_prompt)
            logger.debug(f"Received response for {input_file}")

            # Write response to output file
            output_filename = file_handler.write_output(input_file, response)
            logger.info(f"Saved response to {output_filename}")

        except Exception as e:
            logger.error(f"Error processing {input_file}: {e}")

if __name__ == "__main__":
    process_files_with_chatgpt()
```

### **Example Use Cases**

Here are several creative examples demonstrating how to integrate the ChatGPT Prompt Processor into other scripts for various applications.

---

#### **1. Language Translation**

**Objective:** Automatically translate multiple text files from one language to another (e.g., English to Spanish).

**Implementation Steps:**

1. **Create a Translation Prompt:**

   **`prompts/translate_prompt.txt`**

   ```plaintext
   You are a professional translator. Translate the following text from English to Spanish, maintaining the original meaning and tone.

   Text to translate:
   ```

2. **Prepare Input Files:**

   Place the English text files you want to translate in the `input_files/` directory.

3. **Create the Translation Script:**

   **`translate_files.py`**

   ```python
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def translate_files():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load translation prompt
       system_prompt = prompt_manager.load_prompt('translate_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files()

       for input_file in input_files:
           try:
               user_prompt = file_handler.read_file(input_file)
               logger.info(f"Translating file: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, user_prompt)
               logger.debug(f"Received translation for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved translated file to {output_filename}")

           except Exception as e:
               logger.error(f"Error translating {input_file}: {e}")

   if __name__ == "__main__":
       translate_files()
   ```

4. **Run the Translation Script:**

   ```bash
   python translate_files.py
   ```

**Outcome:** Each English input file in `input_files/` is translated to Spanish and saved in `output_files/` with a `_response.txt` suffix.

---

#### **2. Style Conversion**

**Objective:** Convert the writing style of multiple documents from formal to conversational.

**Implementation Steps:**

1. **Create a Style Conversion Prompt:**

   **`prompts/style_conversion_prompt.txt`**

   ```plaintext
   You are an expert editor. Convert the following formal text into a conversational tone without altering the original meaning.

   Formal Text:
   ```

2. **Prepare Input Files:**

   Place the formal text files you want to convert in the `input_files/` directory.

3. **Create the Style Conversion Script:**

   **`style_conversion.py`**

   ```python
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def convert_style():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load style conversion prompt
       system_prompt = prompt_manager.load_prompt('style_conversion_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files()

       for input_file in input_files:
           try:
               user_prompt = file_handler.read_file(input_file)
               logger.info(f"Converting style of file: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, user_prompt)
               logger.debug(f"Received styled text for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved styled file to {output_filename}")

           except Exception as e:
               logger.error(f"Error converting style of {input_file}: {e}")

   if __name__ == "__main__":
       convert_style()
   ```

4. **Run the Style Conversion Script:**

   ```bash
   python style_conversion.py
   ```

**Outcome:** Each formal input file in `input_files/` is converted to a conversational tone and saved in `output_files/` with a `_response.txt` suffix.

---

#### **3. Summarization of Documents**

**Objective:** Summarize lengthy documents into concise summaries.

**Implementation Steps:**

1. **Create a Summarization Prompt:**

   **`prompts/summarization_prompt.txt`**

   ```plaintext
   You are a skilled summarizer. Provide a concise summary of the following text, highlighting the main points and key information.

   Text to summarize:
   ```

2. **Prepare Input Files:**

   Place the documents you want to summarize in the `input_files/` directory.

3. **Create the Summarization Script:**

   **`summarize_documents.py`**

   ```python
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def summarize_documents():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load summarization prompt
       system_prompt = prompt_manager.load_prompt('summarization_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files()

       for input_file in input_files:
           try:
               user_prompt = file_handler.read_file(input_file)
               logger.info(f"Summarizing file: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, user_prompt)
               logger.debug(f"Received summary for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved summary to {output_filename}")

           except Exception as e:
               logger.error(f"Error summarizing {input_file}: {e}")

   if __name__ == "__main__":
       summarize_documents()
   ```

4. **Run the Summarization Script:**

   ```bash
   python summarize_documents.py
   ```

**Outcome:** Each document in `input_files/` is summarized and saved in `output_files/` with a `_response.txt` suffix.

---

#### **4. Automated Email Drafting**

**Objective:** Automatically draft personalized email responses based on customer inquiries.

**Implementation Steps:**

1. **Create an Email Drafting Prompt:**

   **`prompts/email_drafting_prompt.txt`**

   ```plaintext
   You are a customer support representative. Draft a polite and professional response to the following customer inquiry, addressing all concerns and providing clear solutions.

   Customer Inquiry:
   ```

2. **Prepare Input Files:**

   Place customer inquiry texts in the `input_files/` directory.

3. **Create the Email Drafting Script:**

   **`draft_emails.py`**

   ```python
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def draft_emails():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load email drafting prompt
       system_prompt = prompt_manager.load_prompt('email_drafting_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files()

       for input_file in input_files:
           try:
               customer_inquiry = file_handler.read_file(input_file)
               logger.info(f"Drafting email for inquiry: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, customer_inquiry)
               logger.debug(f"Received email draft for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved drafted email to {output_filename}")

           except Exception as e:
               logger.error(f"Error drafting email for {input_file}: {e}")

   if __name__ == "__main__":
       draft_emails()
   ```

4. **Run the Email Drafting Script:**

   ```bash
   python draft_emails.py
   ```

**Outcome:** Each customer inquiry in `input_files/` is used to generate a drafted email saved in `output_files/` with a `_response.txt` suffix.

---

## **Advanced Features**

### **1. Parallel Processing**

For large batches of files, processing them sequentially might be time-consuming. Implementing parallel processing can significantly speed up the workflow.

**Implementation:**

Use Python's `concurrent.futures` module to process multiple files simultaneously.

**Example Modification in `main.py`:**

```python
import os
from concurrent.futures import ThreadPoolExecutor, as_completed
from config import Config
from logger import setup_logger
from prompt_manager import PromptManager
from file_handler import FileHandler
from api_client import APIClient
from utils import ensure_directory
from cli import parse_args

def process_file(input_file, prompt_manager, file_handler, api_client, system_prompt, logger):
    try:
        user_prompt = file_handler.read_file(input_file)
        logger.info(f"Processing file: {input_file}")

        # Send prompt to API
        response = api_client.send_prompt(system_prompt, user_prompt)
        logger.debug(f"Received response for {input_file}")

        # Write response to output file
        output_filename = file_handler.write_output(input_file, response)
        logger.info(f"Saved response to {output_filename}")
    except Exception as e:
        logger.error(f"Error processing {input_file}: {e}")

def main():
    # Parse command-line arguments
    args = parse_args()

    # Load configuration
    config = Config()

    # Override config with CLI arguments if provided
    prompt_dir = config.prompts_dir
    input_dir = args.input_dir if args.input_dir else config.input_dir
    output_dir = args.output_dir if args.output_dir else config.output_dir
    model = args.model if args.model else config.model
    temperature = args.temperature if args.temperature else config.temperature
    max_tokens = args.max_tokens if args.max_tokens else config.max_tokens
    log_file = args.log_file if args.log_file else 'app.log'
    max_workers = args.max_workers if hasattr(args, 'max_workers') else 5  # Default to 5 threads

    # Setup logger
    logger = setup_logger(log_file)

    logger.info("Starting ChatGPT Prompt Processor")

    # Ensure output directory exists
    ensure_directory(output_dir)

    # Initialize components
    prompt_manager = PromptManager(prompt_dir)
    file_handler = FileHandler(input_dir, output_dir)
    api_client = APIClient(config.api_key, model, temperature, max_tokens)

    # Determine which prompts to use
    if args.prompt:
        prompt_files = [args.prompt]
    else:
        prompt_files = prompt_manager.list_prompts()

    # Process each prompt
    for prompt_file in prompt_files:
        try:
            system_prompt = prompt_manager.load_prompt(prompt_file)
            logger.info(f"Loaded prompt: {prompt_file}")
        except Exception as e:
            logger.error(f"Failed to load prompt {prompt_file}: {e}")
            continue

        # Iterate through input files
        input_files = file_handler.list_input_files()

        with ThreadPoolExecutor(max_workers=max_workers) as executor:
            futures = [
                executor.submit(
                    process_file, input_file, prompt_manager, file_handler, api_client, system_prompt, logger
                )
                for input_file in input_files
            ]
            for future in as_completed(futures):
                future.result()  # To raise exceptions if any

    logger.info("Processing complete.")

if __name__ == "__main__":
    main()
```

**Note:** Modify the `cli.py` to accept `--max_workers` argument if needed.

---

### **2. Dynamic Prompt Customization**

Allow dynamic modification of prompts based on input file content or other parameters.

**Implementation:**

Enhance the `APIClient` class to accept additional context or parameters when sending prompts.

**Example in `api_client.py`:**

```python
class APIClient:
    def __init__(self, api_key, model="gpt-4", temperature=0.7, max_tokens=1500):
        openai.api_key = api_key
        self.model = model
        self.temperature = temperature
        self.max_tokens = max_tokens

    def send_prompt(self, system_prompt, user_prompt, additional_context=None):
        try:
            messages = [
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ]
            if additional_context:
                messages.append({"role": "user", "content": additional_context})

            response = openai.ChatCompletion.create(
                model=self.model,
                messages=messages,
                temperature=self.temperature,
                max_tokens=self.max_tokens
            )
            return response.choices[0].message['content'].strip()
        except Exception as e:
            raise RuntimeError(f"API request failed: {e}")
```

**Usage in Another Script:**

```python
response = api_client.send_prompt(system_prompt, user_prompt, additional_context="Please also include a summary at the end.")
```

---

### **3. Handling Different File Formats**

Extend the `FileHandler` to support different file formats such as Markdown, JSON, or XML.

**Implementation:**

Modify the `FileHandler` class to include reading and writing for various formats.

**Example in `file_handler.py`:**

```python
import os
import json

class FileHandler:
    def __init__(self, input_dir, output_dir):
        self.input_dir = input_dir
        self.output_dir = output_dir

    def list_input_files(self, extensions=['.txt', '.md', '.json']):
        return [f for f in os.listdir(self.input_dir) if os.path.splitext(f)[1] in extensions]

    def read_file(self, filename):
        path = os.path.join(self.input_dir, filename)
        if not os.path.exists(path):
            raise FileNotFoundError(f"Input file {path} does not exist.")
        _, ext = os.path.splitext(filename)
        with open(path, 'r', encoding='utf-8') as file:
            if ext == '.json':
                return json.load(file)
            else:
                return file.read()

    def write_output(self, filename, content):
        base, ext = os.path.splitext(filename)
        output_filename = f"{base}_response{ext}"
        output_path = os.path.join(self.output_dir, output_filename)
        with open(output_path, 'w', encoding='utf-8') as file:
            if isinstance(content, dict):
                json.dump(content, file, indent=4)
            else:
                file.write(content)
        return output_filename
```

**Usage in Another Script:**

Handle JSON content appropriately.

```python
import json

user_prompt = file_handler.read_file(input_file)
if isinstance(user_prompt, dict):
    user_prompt = json.dumps(user_prompt)
response = api_client.send_prompt(system_prompt, user_prompt)
# Optionally, parse JSON response
try:
    response_data = json.loads(response)
    file_handler.write_output(input_file, response_data)
except json.JSONDecodeError:
    file_handler.write_output(input_file, response)
```

---

## **Advanced Use Cases**

Here are additional creative use cases leveraging the modularity of the ChatGPT Prompt Processor.

### **1. Automated Code Documentation**

**Objective:** Generate documentation or comments for code files to improve maintainability.

**Implementation Steps:**

1. **Create a Code Documentation Prompt:**

   **`prompts/code_documentation_prompt.txt`**

   ```plaintext
   You are a professional software developer. Add detailed comments and documentation to the following code, explaining the purpose of functions, classes, and important code blocks.

   Code:
   ```

2. **Prepare Input Files:**

   Place your code files (e.g., `.py`, `.js`, `.java`) in the `input_files/` directory.

3. **Create the Code Documentation Script:**

   **`document_code.py`**

   ```python
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def document_code():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load code documentation prompt
       system_prompt = prompt_manager.load_prompt('code_documentation_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files(extensions=['.py', '.js', '.java'])

       for input_file in input_files:
           try:
               code_content = file_handler.read_file(input_file)
               logger.info(f"Documenting code file: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, code_content)
               logger.debug(f"Received documentation for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved documented code to {output_filename}")

           except Exception as e:
               logger.error(f"Error documenting {input_file}: {e}")

   if __name__ == "__main__":
       document_code()
   ```

4. **Run the Code Documentation Script:**

   ```bash
   python document_code.py
   ```

**Outcome:** Each code file in `input_files/` is annotated with detailed comments and documentation, saved in `output_files/` with a `_response.txt` suffix.

---

### **2. Automated Report Generation from Data**

**Objective:** Generate comprehensive reports based on raw data inputs, such as sales figures or survey results.

**Implementation Steps:**

1. **Create a Report Generation Prompt:**

   **`prompts/report_generation_prompt.txt`**

   ```plaintext
   You are a data analyst. Generate a detailed report based on the following data, including insights, trends, and recommendations.

   Data:
   ```

2. **Prepare Input Files:**

   Place data files (e.g., `.csv`, `.json`) in the `input_files/` directory.

3. **Create the Report Generation Script:**

   **`generate_reports.py`**

   ```python
   import csv
   import json
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def generate_reports():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load report generation prompt
       system_prompt = prompt_manager.load_prompt('report_generation_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files(extensions=['.csv', '.json'])

       for input_file in input_files:
           try:
               data_content = file_handler.read_file(input_file)
               
               # If CSV, convert to JSON
               if input_file.endswith('.csv'):
                   reader = csv.DictReader(data_content.splitlines())
                   data_content = json.dumps([row for row in reader], indent=4)

               logger.info(f"Generating report for data file: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, data_content)
               logger.debug(f"Received report for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved report to {output_filename}")

           except Exception as e:
               logger.error(f"Error generating report for {input_file}: {e}")

   if __name__ == "__main__":
       generate_reports()
   ```

4. **Run the Report Generation Script:**

   ```bash
   python generate_reports.py
   ```

**Outcome:** Each data file in `input_files/` is processed to generate a comprehensive report saved in `output_files/` with a `_response.txt` suffix.

---

### **3. Automated Meeting Minutes Generation**

**Objective:** Convert meeting transcripts or recordings into concise meeting minutes.

**Implementation Steps:**

1. **Create a Meeting Minutes Prompt:**

   **`prompts/meeting_minutes_prompt.txt`**

   ```plaintext
   You are a professional meeting secretary. Generate concise meeting minutes from the following transcript, highlighting key discussions, decisions, and action items.

   Transcript:
   ```

2. **Prepare Input Files:**

   Place meeting transcript texts in the `input_files/` directory.

3. **Create the Meeting Minutes Script:**

   **`generate_meeting_minutes.py`**

   ```python
   from chatgpt_processor.config import Config
   from chatgpt_processor.logger import setup_logger
   from chatgpt_processor.prompt_manager import PromptManager
   from chatgpt_processor.file_handler import FileHandler
   from chatgpt_processor.api_client import APIClient
   from chatgpt_processor.utils import ensure_directory

   def generate_meeting_minutes():
       # Load configuration
       config = Config()

       # Setup logger
       logger = setup_logger()

       # Ensure output directory exists
       ensure_directory(config.output_dir)

       # Initialize components
       prompt_manager = PromptManager(config.prompts_dir)
       file_handler = FileHandler(config.input_dir, config.output_dir)
       api_client = APIClient(config.openai.api_key, config.api.model, config.api.temperature, config.api.max_tokens)

       # Load meeting minutes prompt
       system_prompt = prompt_manager.load_prompt('meeting_minutes_prompt.txt')

       # List input files
       input_files = file_handler.list_input_files(extensions=['.txt'])

       for input_file in input_files:
           try:
               transcript = file_handler.read_file(input_file)
               logger.info(f"Generating meeting minutes for: {input_file}")

               # Send prompt to API
               response = api_client.send_prompt(system_prompt, transcript)
               logger.debug(f"Received meeting minutes for {input_file}")

               # Write response to output file
               output_filename = file_handler.write_output(input_file, response)
               logger.info(f"Saved meeting minutes to {output_filename}")

           except Exception as e:
               logger.error(f"Error generating meeting minutes for {input_file}: {e}")

   if __name__ == "__main__":
       generate_meeting_minutes()
   ```

4. **Run the Meeting Minutes Script:**

   ```bash
   python generate_meeting_minutes.py
   ```

**Outcome:** Each meeting transcript in `input_files/` is transformed into concise meeting minutes saved in `output_files/` with a `_response.txt` suffix.

---

## **Best Practices**

1. **Secure API Keys:**
   - Avoid hard-coding API keys. Use environment variables or secure configuration files.
   - Example: Store `OPENAI_API_KEY` in `config.yaml` and ensure the file is excluded from version control (`.gitignore`).

2. **Error Handling:**
   - Implement comprehensive error handling to manage API failures, file I/O issues, and unexpected data formats.
   - Use try-except blocks and log errors for debugging.

3. **Logging:**
   - Utilize the logging system to monitor script operations.
   - Differentiate log levels (INFO, DEBUG, ERROR) for clarity.

4. **Modularity:**
   - Keep functions and classes focused on single responsibilities.
   - Facilitate easier testing and maintenance.

5. **Documentation:**
   - Document each module, class, and function for clarity.
   - Update the `README.md` with usage instructions and examples.

6. **Testing:**
   - Implement unit tests for each module to ensure reliability.
   - Test with diverse input files to handle various edge cases.

7. **Resource Management:**
   - Be mindful of API rate limits and manage requests accordingly.
   - Implement throttling or retries as needed.

---

## **Troubleshooting**

### **1. API Request Failures**

**Symptoms:**
- Errors related to API authentication.
- Rate limit exceeded.

**Solutions:**
- Ensure the API key is correctly set in `config.yaml`.
- Check for typos or incorrect formatting in the API key.
- Monitor API usage and implement rate limiting if necessary.
- Retry failed requests with exponential backoff.

### **2. File Not Found Errors**

**Symptoms:**
- Script fails to locate input or prompt files.

**Solutions:**
- Verify the directory paths in `config.yaml` are correct.
- Ensure that input and prompt files exist in the specified directories.
- Check for correct file extensions (e.g., `.txt`).

### **3. Unexpected API Responses**

**Symptoms:**
- The API returns incomplete or malformed responses.

**Solutions:**
- Validate the prompts being sent to the API.
- Adjust the `temperature` and `max_tokens` parameters for better results.
- Ensure that input files contain appropriate and correctly formatted text.

### **4. Permission Issues**

**Symptoms:**
- Errors related to reading from or writing to directories.

**Solutions:**
- Check file and directory permissions.
- Ensure that the script has the necessary read/write access.
- Run the script with appropriate user privileges.

---

## **Extending the Script**

The **ChatGPT Prompt Processor** is designed to be extensible. Here are ways to enhance its capabilities:

### **1. Supporting Additional APIs**

Integrate other AI models or APIs alongside ChatGPT for specialized tasks.

**Implementation Steps:**

- Create a new module (e.g., `another_api_client.py`) for the additional API.
- Implement similar classes and methods to interface with the new API.
- Modify `main.py` to support selecting between different APIs based on configuration or command-line arguments.

### **2. Adding New Prompt Templates**

Expand the range of tasks by adding new prompt templates.

**Implementation Steps:**

- Create a new prompt file in the `prompts/` directory.
- Use the prompt in a new script or integrate it into existing scripts by specifying the prompt file.

### **3. Enhancing File Format Support**

Extend support to more file formats like XML, PDF, or proprietary formats.

**Implementation Steps:**

- Utilize libraries such as `xml.etree.ElementTree` for XML or `PyPDF2` for PDF handling.
- Modify the `FileHandler` class to read and write these formats appropriately.

### **4. Implementing a Graphical User Interface (GUI)**

Develop a GUI for users who prefer not to use the command line.

**Implementation Steps:**

- Use libraries like `Tkinter`, `PyQt`, or `Streamlit` to build the GUI.
- Allow users to select prompts, input files, and configure settings through the interface.
- Trigger the processing scripts based on user interactions.

---

## **Support and Contributions**

### **1. Reporting Issues**

If you encounter any issues or have suggestions for improvements, please open an issue on the [GitHub repository](https://github.com/yourusername/chatgpt-prompt-processor/issues).

### **2. Contributing**

Contributions are welcome! To contribute:

1. Fork the repository.
2. Create a new branch (`git checkout -b feature/YourFeature`).
3. Commit your changes (`git commit -m 'Add new feature'`).
4. Push to the branch (`git push origin feature/YourFeature`).
5. Open a pull request.

### **3. Contact**

For further assistance, you can reach out via [your-email@example.com](mailto:your-email@example.com).

---

# **Conclusion**

The **ChatGPT Prompt Processor** offers a robust and flexible foundation for automating a wide range of tasks by leveraging the power of OpenAI's ChatGPT API. Its modular design facilitates easy integration into existing workflows and scripts, enabling you to enhance productivity and streamline processes across various domains.

Whether you're aiming to translate documents, convert writing styles, generate reports, or automate email drafting, this script provides the necessary tools and structure to achieve your goals efficiently. By following the documentation and examples provided, you can tailor the processor to fit your specific needs and explore innovative applications.

Feel free to customize and extend the script to unlock its full potential, and don't hesitate to contribute to its development for the benefit of the community!
