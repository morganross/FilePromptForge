import tkinter as tk
from tkinter import messagebox, filedialog
import subprocess
import logging
import os
from datetime import datetime
import yaml
import shutil
import sys


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

def create_default_config_file(config_file_path, install_dir, api_key, logger):
    """Create a default YAML configuration file."""
    default_config = {
        'prompts_dir': os.path.join(install_dir, 'prompts'),
        'input_dir': os.path.join(install_dir, 'input'),
        'output_dir': os.path.join(install_dir, 'output'),
        'openai': {
            'api_key': api_key,
            'model': 'gpt-4',
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

def run_test(install_dir, executable_path):
    logger.debug(f"Starting run_test with install_dir={install_dir}, executable_path={executable_path}")
    input_dir = os.path.join(install_dir, 'input')
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
        # Change working directory to the installation directory
        os.chdir(install_dir)

        command = [
            'python', executable_path,
            '--prompt', prompt_file,
            '--input_dir', input_dir,
            '--output_dir', output_dir
        ]
        logger.debug(f"Running command: {command}")
        result = subprocess.run(command, capture_output=True, text=True)
        logger.debug(f"Command output: {result.stdout}")
        logger.debug(f"Command error: {result.stderr}")
        result.check_returncode()
        logger.info("Test completed successfully.")
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

def create_gui():
    root = tk.Tk()
    root.title("GPT Processor Installer")

    tk.Label(root, text="Install Directory:").grid(row=0, column=0, sticky=tk.W)
    install_dir_entry = tk.Entry(root, width=50)
    install_dir_entry.grid(row=0, column=1, padx=10, pady=5)
    tk.Button(root, text="Browse...", command=lambda: select_install_dir(install_dir_entry)).grid(row=0, column=2, padx=10, pady=5)

    tk.Label(root, text="Executable Path:").grid(row=1, column=0, sticky=tk.W)
    executable_path_entry = tk.Entry(root, width=50)
    executable_path_entry.grid(row=1, column=1, padx=10, pady=5)
    tk.Button(root, text="Browse...", command=lambda: select_executable_path(executable_path_entry)).grid(row=1, column=2, padx=10, pady=5)

    tk.Label(root, text="OpenAI API Key:").grid(row=2, column=0, sticky=tk.W)
    api_key_entry = tk.Entry(root, width=50, show="*")  # Mask the API key
    api_key_entry.grid(row=2, column=1, padx=10, pady=5)



    def install_with_api_key():
        install_dir = install_dir_entry.get()
        
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
        os.makedirs(input_dir, exist_ok=True)
        os.makedirs(output_dir, exist_ok=True)
        logger.info(f"Ensured input directory exists at '{input_dir}'")
        logger.info(f"Ensured output directory exists at '{output_dir}'")

        create_default_prompts(install_dir, logger)

        # Create default config file
        config_file_path = os.path.join(install_dir, 'default_config.yaml')
        api_key = api_key_entry.get()
        create_default_config_file(config_file_path, install_dir, api_key, logger)

        # Copy main executable
        main_executable_source = os.path.abspath(executable_path_entry.get())
        copy_main_executable(main_executable_source, install_dir, logger)

        # Add to system PATH if requested
        os_type = sys.platform
        if os_type.startswith('win'):
            add_to_system_path_windows(install_dir, logger)
        elif os_type in ['darwin', 'linux']:
            # Detect user's shell
            shell = os.environ.get('SHELL', 'bash').split('/')[-1]
            add_to_system_path_unix(install_dir, shell, logger)
        else:
            logger.warning("Could not determine shell to update PATH.")
        
        logger.info("GPT Processor installation completed successfully.")

    tk.Button(root, text="Install", command=install_with_api_key).grid(row=4, column=1, pady=10)
    tk.Button(root, text="Test", command=lambda: run_test(install_dir_entry.get(), executable_path_entry.get())).grid(row=5, column=2, pady=10)

    root.mainloop()

if __name__ == "__main__":
    logger.debug("Starting the installer GUI script")
    create_gui()
