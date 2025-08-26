import tkinter as tk
from tkinter import messagebox, filedialog, ttk
import subprocess
import logging
import os
from datetime import datetime
import yaml
import shutil
import sys
import threading
import requests


# Set up logging
def setup_logger(log_level=logging.INFO, log_file=None):
    logger = logging.getLogger('gpt_processor_installer_gui')
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

# Create a directory named after the current time by default
current_time = datetime.now().strftime("%Y%m%d_%H%M%S")
default_log_dir = f"logs_{current_time}"
os.makedirs(default_log_dir, exist_ok=True)

# Initialize logger with default log file in the new directory
default_log_file = os.path.join(default_log_dir, 'installer_gui.log')
logger = setup_logger(log_level=logging.DEBUG, log_file=default_log_file)

def list_directory_contents(directory):
    try:
        contents = os.listdir(directory)
        logger.debug(f"Contents of directory '{directory}': {contents}")
    except FileNotFoundError:
        logger.error(f"Directory '{directory}' not found.")
    except Exception as e:
        logger.error(f"Error listing contents of directory '{directory}': {e}")

def create_default_prompt_file(prompt_path, logger):
    """Create a default prompt file at the specified path."""
    default_prompt = (
        "You are ChatGPT, a large language model trained by OpenAI. "
        "Provide clear and concise answers to the user's queries."
    )
    try:
        os.makedirs(os.path.dirname(prompt_path), exist_ok=True)
        with open(prompt_path, 'w', encoding='utf-8') as file:
            file.write(default_prompt)
        logger.info(f"Created default prompt file at '{prompt_path}'.")
    except Exception as e:
        logger.error(f"Failed to create default prompt file: {e}")
        sys.exit(1)

def create_default_prompts(install_dir, logger):
    """Create default prompt files in prompts and input directories."""
    prompts_dir = os.path.join(install_dir, 'prompts')
    input_dir = os.path.join(install_dir, 'input')
    default_prompt_path_prompts = os.path.join(prompts_dir, 'standard_prompt.txt')
    default_prompt_path_input = os.path.join(input_dir, 'standard_prompt.txt')

    create_default_prompt_file(default_prompt_path_prompts, logger)
    create_default_prompt_file(default_prompt_path_input, logger)

def create_default_config_file(config_file_path, install_dir, selected_provider, openai_key, openrouter_key, model, logger):
    """Create a default YAML configuration file."""
    default_config = {
        'prompts_dir': os.path.join(install_dir, 'prompts'),
        'input_dir': os.path.join(install_dir, 'input'),
        'output_dir': os.path.join(install_dir, 'output'),
        'provider': selected_provider.lower(),
        'openai': {
            'api_key': openai_key,
            'model': model if selected_provider == "OpenAI" else "",
            'temperature': 0.7,
            'max_tokens': 1500
        },
        'openrouter': {
            'api_key': openrouter_key,
            'model': model if selected_provider == "OpenRouter" else "",
            'temperature': 0.7,
            'max_tokens': 1500
        }
    }
    try:
        os.makedirs(os.path.dirname(config_file_path), exist_ok=True)
        with open(config_file_path, 'w', encoding='utf-8') as file:
            yaml.dump(default_config, file)
        logger.info(f"Created default config file at '{config_file_path}'.")
    except Exception as e:
        logger.error(f"Failed to create default config file: {e}")
        sys.exit(1)

def copy_main_executable(source_path, dest_dir, logger):
    """Copy the main executable to the installation directory."""
    if not os.path.isfile(source_path):
        logger.error(f"Main executable '{source_path}' not found.")
        sys.exit(1)
    try:
        shutil.copy(source_path, dest_dir)
        logger.info(f"Copied main executable to '{dest_dir}'.")
    except Exception as e:
        logger.error(f"Failed to copy main executable: {e}")
        sys.exit(1)

def add_to_system_path_windows(directory, logger):
    """Add the installation directory to the system PATH on Windows."""
    try:
        # Get current PATH
        current_path = os.environ['PATH']
        if directory in current_path:
            logger.info(f"'{directory}' is already in the system PATH.")
            return
        # Add directory to PATH
        os.environ['PATH'] = f"{directory};{current_path}"
        logger.info(f"Added '{directory}' to the system PATH.")
    except Exception as e:
        logger.error(f"Failed to add '{directory}' to the system PATH: {e}")
        sys.exit(1)

def add_to_system_path_unix(directory, shell, logger):
    """Add the installation directory to the system PATH on Unix-like systems."""
    try:
        shell_config_files = {
            'bash': '~/.bashrc',
            'zsh': '~/.zshrc',
            'fish': '~/.config/fish/config.fish'
        }
        config_file = os.path.expanduser(shell_config_files.get(shell, '~/.bashrc'))
        
        with open(config_file, 'a') as f:
            f.write(f'\nexport PATH="{directory}:$PATH"\n')
        
        logger.info(f"Added '{directory}' to PATH in {config_file}")
    except Exception as e:
        logger.error(f"Failed to add '{directory}' to the system PATH: {e}")
        sys.exit(1)

def run_test(base_dir, executable_path):
    install_dir = os.path.join(base_dir, 'filepromptforge')
    logger.debug(f"Starting run_test with install_dir={install_dir}, executable_path={executable_path}")
    logger.debug(f"Install directory exists: {os.path.exists(install_dir)}")
    input_dir = os.path.join(install_dir, 'input')
    logger.debug(f"Input directory path: {input_dir}, exists: {os.path.exists(input_dir)}")
    output_dir = os.path.join(install_dir, 'output')
    prompt_file = os.path.join(install_dir, 'prompts', 'standard_prompt.txt')
    try:
        input_contents = os.listdir(input_dir)
        logger.debug(f"Input directory contents: {input_contents}")
        if not input_contents:
            raise ValueError("Input directory is empty.")
    except FileNotFoundError as e:
        logger.error(f"Input directory not found: {e}")
        list_directory_contents(install_dir)
        messagebox.showerror("Directory Not Found", f"Input directory not found: {e}")
    except ValueError as e:
        logger.error(f"Value error: {e}")
        messagebox.showerror("Input Directory Error", f"{e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        messagebox.showerror("Unexpected Error", f"An unexpected error occurred: {e}")

    try:
        # Ensure openai dependency is installed for the test
        try:
            dep = subprocess.run([sys.executable, '-m', 'pip', 'install', 'openai'], capture_output=True, text=True)
            logger.debug(f"Test dependency install stdout: {dep.stdout}")
            logger.debug(f"Test dependency install stderr: {dep.stderr}")
            dep.check_returncode()
            logger.info("OpenAI package installed for test.")
        except Exception as e_dep:
            logger.error(f"Failed to install openai for test: {e_dep}")
            messagebox.showerror("Dependency Installation Error", f"Failed to install openai package for test: {e_dep}")
            return

        # Change working directory to the installation directory
        # No global cwd change; run subprocess in install_dir instead

        command = [
            sys.executable, executable_path,
            '--verbose',
            '--prompt', prompt_file,
            '--input_dir', input_dir,
            '--output_dir', output_dir
        ]
        logger.debug(f"Running command: {command}")
        result = subprocess.run(command, capture_output=True, text=True, cwd=install_dir)
        logger.debug(f"Command output: {result.stdout}")
        logger.debug(f"Command error: {result.stderr}")
        result.check_returncode()
        logger.info("Test completed successfully.")
        messagebox.showinfo("Test Completed", "Test completed successfully.")
    except subprocess.CalledProcessError as e:
        logger.error(f"Subprocess error: {e}")
        logger.error(f"Command output: {e.output}")
        logger.error(f"Command stderr: {e.stderr}")
        messagebox.showerror("Test Error", f"An error occurred during the test: {e}")
    except Exception as e:
        logger.error(f"Unexpected error: {e}")
        messagebox.showerror("Unexpected Error", f"An unexpected error occurred: {e}")

def select_install_dir(entry):
    directory = filedialog.askdirectory()
    if directory:
        entry.delete(0, tk.END)
        entry.insert(0, directory)

def select_executable_path(entry):
    file_path = filedialog.askopenfilename(filetypes=[("Python Files", "*.py"), ("All Files", "*.*")])
    if file_path:
        entry.delete(0, tk.END)
        entry.insert(0, file_path)

def update_config_file(config_file_path, selected_provider, openai_key, openrouter_key, model, logger):
    """Update the config file with new provider, keys, and model."""
    try:
        if not os.path.exists(config_file_path):
            raise FileNotFoundError(f"Config file not found at '{config_file_path}'")
            
        # Read existing config
        with open(config_file_path, 'r', encoding='utf-8') as file:
            config = yaml.safe_load(file)
        
        # Update provider and keys
        config['provider'] = selected_provider.lower()
        config['openai']['api_key'] = openai_key
        config['openrouter']['api_key'] = openrouter_key

        # Update models based on provider
        if selected_provider == "OpenAI":
             config['openai']['model'] = model
             config['openrouter']['model'] = "" # Clear OpenRouter model if switching to OpenAI
        elif selected_provider == "OpenRouter":
             config['openrouter']['model'] = model
             config['openai']['model'] = "" # Clear OpenAI model if switching to OpenRouter

        # Write updated config
        with open(config_file_path, 'w', encoding='utf-8') as file:
            yaml.dump(config, file)

        logger.info(f"Updated config file at '{config_file_path}' with provider '{selected_provider}' and model '{model}'")
        return True
    except Exception as e:
        logger.error(f"Failed to update config file: {e}")
        return False

def fetch_openrouter_models(logger):
    """Fetches available models from the OpenRouter API."""
    url = "https://openrouter.ai/api/v1/models"
    try:
        response = requests.get(url)
        response.raise_for_status()  # Raise an HTTPError for bad responses (4xx or 5xx)
        data = response.json()
        # Filter models to include only those with 'text' input modality
        text_models = [model for model in data.get('data', []) if 'text' in model.get('architecture', {}).get('input_modalities', [])]
        logger.info(f"Successfully fetched and filtered {len(text_models)} text models from OpenRouter.")
        return text_models
    except requests.exceptions.RequestException as e:
        logger.error(f"Error fetching OpenRouter models: {e}")
        return None

def create_gui():
    root = tk.Tk()
    root.title("GPT Processor Installer")

    tk.Label(root, text="Install Directory:").grid(row=0, column=0, sticky=tk.W)
    install_dir_entry = tk.Entry(root, width=50)
    install_dir_entry.grid(row=0, column=1, padx=10, pady=5)
    tk.Button(root, text="Browse...", command=lambda: select_install_dir(install_dir_entry)).grid(row=0, column=2, padx=10, pady=5)
    # Default install directory to current working directory
    install_dir_entry.insert(0, os.getcwd())

    tk.Label(root, text="Executable Path:").grid(row=1, column=0, sticky=tk.W)
    executable_path_entry = tk.Entry(root, width=50)
    executable_path_entry.grid(row=1, column=1, padx=10, pady=5)
    tk.Button(root, text="Browse...", command=lambda: select_executable_path(executable_path_entry)).grid(row=1, column=2, padx=10, pady=5)
    # Default executable path to gpt_processor_main.py in workspace
    executable_path_entry.insert(0, os.path.join(os.getcwd(), 'gpt_processor_main.py'))

    # Add API Provider selection dropdown
    tk.Label(root, text="API Provider:").grid(row=2, column=0, sticky=tk.W)
    provider_var = tk.StringVar(value="OpenAI")  # Default provider
    provider_dropdown = ttk.Combobox(root, textvariable=provider_var, width=47, state="readonly")
    providers = ["OpenAI", "OpenRouter"]
    provider_dropdown['values'] = providers
    provider_dropdown.grid(row=2, column=1, padx=10, pady=5)

    # Add API Key fields
    openai_api_key_label = tk.Label(root, text="OpenAI API Key:")
    openai_api_key_label.grid(row=3, column=0, sticky=tk.W)
    openai_api_key_entry = tk.Entry(root, width=50, show="*")  # Mask the API key
# Add labels for OpenRouter model info
    token_limit_label = tk.Label(root, text="Token Limit:")
    token_limit_value = tk.Label(root, text="")
    pricing_label = tk.Label(root, text="Pricing (Prompt/Completion per 1M tokens):")
    pricing_value = tk.Label(root, text="")
    openai_api_key_entry.grid(row=3, column=1, padx=10, pady=5)

    openrouter_api_key_label = tk.Label(root, text="OpenRouter API Key:")
    openrouter_api_key_entry = tk.Entry(root, width=50, show="*")  # Mask the API key

    def on_provider_select(event):
        selected_provider = provider_var.get()
        if selected_provider == "OpenAI":
            openai_api_key_label.grid(row=3, column=0, sticky=tk.W)
            openai_api_key_entry.grid(row=3, column=1, padx=10, pady=5)
            openrouter_api_key_label.grid_forget()
            openrouter_api_key_entry.grid_forget()
            model_dropdown.grid(row=4, column=1, padx=10, pady=5) # Show model dropdown for OpenAI
            model_label.grid(row=4, column=0, sticky=tk.W) # Show model label for OpenAI
            # Populate with OpenAI models
            openai_models = [
                "gpt-4o-mini-audio-preview-2024-12-17", "dall-e-3", "gpt-4-turbo-2024-04-09", "dall-e-2",
                "gpt-4o-audio-preview-2024-10-01", "gpt-4o-audio-preview", "o1-mini-2024-09-12",
                "gpt-4o-mini-realtime-preview-2024-12-17", "o1-preview-2024-09-12", "o1-mini", "o1-preview",
                "gpt-4o-mini-realtime-preview", "whisper-1", "gpt-4-turbo", "gpt-4o-mini-audio-preview",
                "gpt-4o-realtime-preview-2024-10-01", "babbage-002", "tts-1-hd-1106", "gpt-4o-audio-preview-2024-12-17",
                "gpt-4o", "gpt-4o-2024-08-06", "tts-1-hd", "chatgpt-4o-latest", "text-embedding-3-large",
                "tts-1", "tts-1-1106", "gpt-4o-2024-11-20", "davinci-002", "gpt-3.5-turbo-1106",
                "omni-moderation-2024-09-26", "gpt-3.5-turbo-instruct", "gpt-3.5-turbo-instruct-0914",
                "gpt-3.5-turbo-0125", "gpt-4o-realtime-preview-2024-12-17", "gpt-3.5-turbo",
                "gpt-4o-realtime-preview", "gpt-3.5-turbo-16k", "gpt-4o-mini-2024-07-18",
                "text-embedding-3-small", "gpt-4", "gpt-4o-mini", "text-embedding-ada-002",
                "gpt-4-1106-preview", "omni-moderation-latest", "gpt-4-0613", "gpt-4o-2024-05-13",
                "gpt-4-turbo-preview", "gpt-4-0125-preview"
            ]
            openai_models.sort()
            model_dropdown['values'] = openai_models
            model_var.set("gpt-4") # Set default model
        elif selected_provider == "OpenRouter":
            openai_api_key_label.grid_forget()
            openai_api_key_entry.grid_forget()
            openrouter_api_key_label.grid(row=3, column=0, sticky=tk.W)
            openrouter_api_key_entry.grid(row=3, column=1, padx=10, pady=5)
            # Fetch and populate OpenRouter models
            openrouter_models_data = fetch_openrouter_models(logger)
            if openrouter_models_data:
                openrouter_model_names = [model['id'] for model in openrouter_models_data]
                openrouter_model_names.sort()
                model_dropdown['values'] = openrouter_model_names
                if openrouter_model_names: # Set default to the first model if available
                    model_var.set(openrouter_model_names[0])
                    # Store the fetched model data for later use
                    root.openrouter_models_data = openrouter_models_data
                    # Update the token and pricing info for the default model
                    update_openrouter_model_info(openrouter_model_names[0], openrouter_models_data)
                else:
                    model_var.set("") # Clear selection if no models
                    root.openrouter_models_data = []
                    update_openrouter_model_info(None, []) # Clear info if no models
                model_dropdown.grid(row=4, column=1, padx=10, pady=5) # Show model dropdown for OpenRouter
                model_label.grid(row=4, column=0, sticky=tk.W) # Show model label for OpenRouter
                # Show OpenRouter specific info labels
                token_limit_label.grid(row=5, column=0, sticky=tk.W)
                token_limit_value.grid(row=5, column=1, sticky=tk.W, padx=10)
                pricing_label.grid(row=6, column=0, sticky=tk.W)
                pricing_value.grid(row=6, column=1, sticky=tk.W, padx=10)
            else:
                messagebox.showerror("API Error", "Failed to fetch models from OpenRouter.")
                model_dropdown.grid_forget() # Hide model dropdown if fetching failed
                model_label.grid_forget() # Hide model label if fetching failed
                model_dropdown['values'] = [] # Clear model list
                model_var.set("") # Clear selection
                root.openrouter_models_data = []
                # Hide OpenRouter specific info labels
                token_limit_label.grid_forget()
                token_limit_value.grid_forget()
                pricing_label.grid_forget()
                pricing_value.grid_forget()


    provider_dropdown.bind("<<ComboboxSelected>>", on_provider_select)

    # Add model selection dropdown (initially for OpenAI)
    model_label = tk.Label(root, text="Model:")
    model_label.grid(row=4, column=0, sticky=tk.W)
    model_var = tk.StringVar(value="gpt-4")  # Default model
    model_dropdown = ttk.Combobox(root, textvariable=model_var, width=47, state="readonly")
    # Populate with initial OpenAI models
    openai_models_initial = [
        "gpt-4o-mini-audio-preview-2024-12-17", "dall-e-3", "gpt-4-turbo-2024-04-09", "dall-e-2",
        "gpt-4o-audio-preview-2024-10-01", "gpt-4o-audio-preview", "o1-mini-2024-09-12",
        "gpt-4o-mini-realtime-preview-2024-12-17", "o1-preview-2024-09-12", "o1-mini", "o1-preview",
        "gpt-4o-mini-realtime-preview", "whisper-1", "gpt-4-turbo", "gpt-4o-mini-audio-preview",
        "gpt-4o-realtime-preview-2024-10-01", "babbage-002", "tts-1-hd-1106", "gpt-4o-audio-preview-2024-12-17",
        "gpt-4o", "gpt-4o-2024-08-06", "tts-1-hd", "chatgpt-4o-latest", "text-embedding-3-large",
        "tts-1", "tts-1-1106", "gpt-4o-2024-11-20", "davinci-002", "gpt-3.5-turbo-1106",
        "omni-moderation-2024-09-26", "gpt-3.5-turbo-instruct", "gpt-3.5-turbo-instruct-0914",
        "gpt-3.5-turbo-0125", "gpt-4o-realtime-preview-2024-12-17", "gpt-3.5-turbo",
        "gpt-4o-realtime-preview", "gpt-3.5-turbo-16k", "gpt-4o-mini-2024-07-18",
        "text-embedding-3-small", "gpt-4", "gpt-4o-mini", "text-embedding-ada-002",
        "gpt-4-1106-preview", "omni-moderation-latest", "gpt-4-0613", "gpt-4o-2024-05-13",
        "gpt-4-turbo-preview", "gpt-4-0125-preview"
    ]
    model_dropdown['values'] = openai_models_initial
    model_dropdown.grid(row=4, column=1, padx=10, pady=5)

    # Add model selection dropdown (initially for OpenAI)
    model_label = tk.Label(root, text="Model:")
    model_label.grid(row=4, column=0, sticky=tk.W)
    model_var = tk.StringVar(value="gpt-4")  # Default model
    model_dropdown = ttk.Combobox(root, textvariable=model_var, width=47, state="readonly")
    models = [
        "gpt-4o-mini-audio-preview-2024-12-17", "dall-e-3", "gpt-4-turbo-2024-04-09", "dall-e-2",
        "gpt-4o-audio-preview-2024-10-01", "gpt-4o-audio-preview", "o1-mini-2024-09-12",
        "gpt-4o-mini-realtime-preview-2024-12-17", "o1-preview-2024-09-12", "o1-mini", "o1-preview",
        "gpt-4o-mini-realtime-preview", "whisper-1", "gpt-4-turbo", "gpt-4o-mini-audio-preview",
        "gpt-4o-realtime-preview-2024-10-01", "babbage-002", "tts-1-hd-1106", "gpt-4o-audio-preview-2024-12-17",
        "gpt-4o", "gpt-4o-2024-08-06", "tts-1-hd", "chatgpt-4o-latest", "text-embedding-3-large",
        "tts-1", "tts-1-1106", "gpt-4o-2024-11-20", "davinci-002", "gpt-3.5-turbo-1106",
        "omni-moderation-2024-09-26", "gpt-3.5-turbo-instruct", "gpt-3.5-turbo-instruct-0914",
        "gpt-3.5-turbo-0125", "gpt-4o-realtime-preview-2024-12-17", "gpt-3.5-turbo",
        "gpt-4o-realtime-preview", "gpt-3.5-turbo-16k", "gpt-4o-mini-2024-07-18",
        "text-embedding-3-small", "gpt-4", "gpt-4o-mini", "text-embedding-ada-002",
        "gpt-4-1106-preview", "omni-moderation-latest", "gpt-4-0613", "gpt-4o-2024-05-13",
        "gpt-4-turbo-preview", "gpt-4-0125-preview"
    ]
    model_dropdown['values'] = models
    model_dropdown.grid(row=4, column=1, padx=10, pady=5)

    # Initially hide OpenRouter API key field and info labels
    openrouter_api_key_label.grid_forget()
    openrouter_api_key_entry.grid_forget()
    token_limit_label.grid_forget()
    token_limit_value.grid_forget()
    pricing_label.grid_forget()
    pricing_value.grid_forget()


    def update_openrouter_model_info(selected_model_name, models_data):
        """Updates the token limit and pricing labels for the selected OpenRouter model."""
        token_limit_value.config(text="")
        pricing_value.config(text="")
        if selected_model_name and models_data:
            for model in models_data:
                if model.get('id') == selected_model_name:
                    context_length = model.get('context_length', 'N/A')
                    pricing = model.get('pricing', {})
                    prompt_price = pricing.get('prompt', 'N/A')
                    completion_price = pricing.get('completion', 'N/A')
                    token_limit_value.config(text=str(context_length))
                    pricing_value.config(text=f"${prompt_price} / ${completion_price}")
                    break

    def on_model_select(event):
        """Handles model selection change."""
        selected_provider = provider_var.get()
        if selected_provider == "OpenRouter":
            selected_model_name = model_var.get()
            update_openrouter_model_info(selected_model_name, root.openrouter_models_data)

    model_dropdown.bind("<<ComboboxSelected>>", on_model_select)

    def update_config():
        base_dir = install_dir_entry.get()
        if not base_dir:
            messagebox.showerror("Error", "Please select an installation directory")
            return

        install_dir = os.path.join(base_dir, 'filepromptforge')
        config_file_path = os.path.join(install_dir, 'default_config.yaml')

        selected_provider = provider_var.get()
        openai_key = openai_api_key_entry.get() if selected_provider == "OpenAI" else ""
        openrouter_key = openrouter_api_key_entry.get() if selected_provider == "OpenRouter" else ""
        model = model_var.get() # Get the selected model regardless of provider

        if update_config_file(config_file_path, selected_provider, openai_key, openrouter_key, model, logger):
            messagebox.showinfo("Success", "Config file updated successfully")
        else:
            messagebox.showerror("Error", "Failed to update config file")

    def install_with_api_key():
        base_dir = install_dir_entry.get()
        install_dir = os.path.join(base_dir, 'filepromptforge')
        
        # Create installation directory if it doesn't exist
        try:
            os.makedirs(install_dir, exist_ok=True)
        except Exception as e:
            logger.error(f"Failed to create installation directory: {e}")
            messagebox.showerror("Directory Error", f"Failed to create installation directory: {e}")
            return

        # Ensure input and output directories are created
        input_dir = os.path.join(install_dir, 'input')
        output_dir = os.path.join(install_dir, 'output')

        # Update the config file with selected provider, keys, and model
        config_file_path = os.path.join(install_dir, 'default_config.yaml')
        selected_provider = provider_var.get()
        openai_key = openai_api_key_entry.get() if selected_provider == "OpenAI" else ""
        openrouter_key = openrouter_api_key_entry.get() if selected_provider == "OpenRouter" else ""
        model = model_var.get()

        create_default_config_file(config_file_path, install_dir, selected_provider, openai_key, openrouter_key, model, logger)
        if not update_config_file(config_file_path, selected_provider, openai_key, openrouter_key, model, logger):
            messagebox.showerror("Error", "Failed to update config file during installation.")
            return
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)

        # Create default prompt files
        create_default_prompts(install_dir, logger)

        # Create default config file
        config_file_path = os.path.join(install_dir, 'default_config.yaml')
        selected_provider = provider_var.get()
        openai_key = openai_api_key_entry.get() if selected_provider == "OpenAI" else ""
        openrouter_key = openrouter_api_key_entry.get() if selected_provider == "OpenRouter" else ""
        model = model_var.get() if selected_provider == "OpenAI" else "" # Only save model for OpenAI for now

        # Copy main executable
        executable_source_path = executable_path_entry.get()
        copy_main_executable(executable_source_path, install_dir, logger)

        # Add to system PATH (Windows example)
        if sys.platform.startswith('win'):
            add_to_system_path_windows(install_dir, logger)
        else:
             # For Unix-like systems, you might need to prompt the user for their shell
             # or provide instructions on how to manually add to PATH.
             # For simplicity, we'll just log a message for now.
             logger.info("Manual step: Add the installation directory to your system PATH.")
             messagebox.showinfo("Manual Step Required", "Please manually add the installation directory to your system PATH.")


        messagebox.showinfo("Installation Complete", "GPT Processor installed successfully!")

    def run_test_thread():
        base_dir = install_dir_entry.get()
        executable_path = executable_path_entry.get()
        if not base_dir or not executable_path:
            messagebox.showerror("Error", "Please select installation directory and executable path")
            return
        threading.Thread(target=run_test, args=(base_dir, executable_path)).start()

    # Installation button
    install_button = tk.Button(root, text="Install", command=install_with_api_key)
    install_button.grid(row=7, column=0, columnspan=3, pady=10)

    # Update Config button
    update_config_button = tk.Button(root, text="Update Config", command=update_config)
    update_config_button.grid(row=8, column=0, columnspan=3, pady=5)

    # Run Test button
    run_test_button = tk.Button(root, text="Run Test", command=run_test_thread)
    run_test_button.grid(row=9, column=0, columnspan=3, pady=5)

    root.mainloop()

if __name__ == "__main__":
    create_gui()
