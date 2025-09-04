import asyncio
import argparse
import json
import os
import sys
import uuid
from copy import deepcopy

# Adjust path for importing multi_agents
sys.path.insert(0, os.path.abspath(os.path.join(os.path.dirname(__file__), '..')))

from multi_agents.agents import ChiefEditorAgent
from gpt_researcher.utils.enum import Tone # Assuming Tone is needed
from dotenv import load_dotenv

# Load default task configuration
DEFAULT_TASK = {
  "query": "Is AI in a hype cycle?",
  "max_sections": 3,
  "publish_formats": {
    "markdown": True,
    "pdf": True,
    "docx": True
  },
  "include_human_feedback": False,
  "follow_guidelines": False,
  "model": "gpt-4o",
  "guidelines": [
    "The report MUST be written in APA format",
    "Each sub section MUST include supporting sources using hyperlinks. If none exist, erase the sub section or rewrite it to be a part of the previous section",
    "The report MUST be written in spanish"
  ],
  "verbose": True
}

def deep_merge(dict1, dict2):
    """
    Deep merge two dictionaries. dict2 values override dict1 values.
    Handles nested dictionaries.
    """
    for key, value in dict2.items():
        if key in dict1 and isinstance(dict1[key], dict) and isinstance(value, dict):
            deep_merge(dict1[key], value)
        else:
            dict1[key] = value

def open_task():
    """
    Loads the task configuration from a Local repo task.json if present.
    This implementation intentionally avoids reading or writing any System-level
    config next to the Python executable. If no Local task.json is found or it
    cannot be parsed, DEFAULT_TASK is returned in-memory (no file writes).
    """
    # Candidate local paths (relative to repository and this script)
    repo_root = os.path.abspath(os.path.join(os.path.dirname(__file__), '..'))
    candidates = [
        os.path.join(repo_root, 'gpt-researcher', 'multi_agents', 'task.json'),
        os.path.join(repo_root, 'multi_agents', 'task.json'),
        os.path.join(os.path.dirname(__file__), 'task.json'),
    ]

    task = None
    for p in candidates:
        try:
            if os.path.exists(p):
                with open(p, 'r', encoding='utf-8') as f:
                    task = json.load(f)
                print(f"Loaded Local task.json from '{p}'")
                break
        except json.JSONDecodeError:
            # If Local task.json is malformed, warn and continue to next candidate
            print(f"Warning: Could not decode JSON from Local task.json at '{p}'. Ignoring.")
        except Exception as e:
            print(f"Warning: Error reading Local task.json at '{p}': {e}")

    # If no local task.json was loaded, fall back to an in-memory default (do NOT write to disk)
    if task is None:
        task = deepcopy(DEFAULT_TASK)

    # Override model with STRATEGIC_LLM if defined in environment
    strategic_llm = os.environ.get("STRATEGIC_LLM")
    if strategic_llm and ":" in strategic_llm:
        # Extract the model name (part after the first colon)
        model_name = strategic_llm.split(":", 1)[1]
        task["model"] = model_name
    elif strategic_llm:
        task["model"] = strategic_llm # Use the full strategic_llm value if no colon

    return task

def load_task_config(args):
    """
    Load and assemble configuration based on the specified hierarchy:
    task.json (from open_task) -> Specified task file -> Query file -> Guidelines file -> Command-line arguments.
    """
    # 1. Start with configuration from open_task()
    config = open_task()

    # 2. Load from a specified task config file if provided
    if args.task_config:
        if not os.path.exists(args.task_config):
            print(f"Error: Task config file '{args.task_config}' not found.")
            sys.exit(1)
        try:
            with open(args.task_config, 'r') as f:
                task_from_file = json.load(f)
            deep_merge(config, task_from_file)
        except json.JSONDecodeError:
            print(f"Error: Could not decode JSON from '{args.task_config}'")
            sys.exit(1)

    # 3. Override with command-line arguments
    # Directly use parsed arguments, which argparse has already handled based on defined types
    args_dict = vars(args)
    for key in DEFAULT_TASK.keys(): # Iterate through default keys to apply overrides
        # Check if the argument was provided and is not the default value set by argparse
        # This requires comparing to the default value set in add_argument
        # A simpler approach is to check if the argument is present in the parsed args
        # and not None, assuming argparse handles defaults appropriately.
        # For boolean flags, argparse sets the value based on presence, so check if the key exists
        if key in args_dict and args_dict[key] is not None:
             # Special handling for boolean flags where the argument name might be different (--no-key)
            if isinstance(DEFAULT_TASK.get(key), bool):
                 # Check if the flag was explicitly set (either --key or --no-key)
                 # This is tricky with argparse's default handling.
                 # A more robust way is to check if the argument's source is not the default.
                 # For now, assume if the key is in args_dict and not None, it was set.
                 config[key] = args_dict[key]
            elif not isinstance(DEFAULT_TASK.get(key), bool): # Handle non-boolean overrides
                 config[key] = args_dict[key]

    # Handle guidelines file argument - overrides default, task config, and query file
    if args.guidelines_file:
        if not os.path.exists(args.guidelines_file):
            print(f"Error: Guidelines file '{args.guidelines_file}' not found.")
            sys.exit(1)
        try:
            with open(args.guidelines_file, 'r') as f:
                # Assuming guidelines file contains a string or a JSON list
                # Adjust reading logic based on expected file format
                guidelines_content = f.read().strip()
                # If guidelines are expected to be a list, you might need to parse JSON
                # try:
                #     config['guidelines'] = json.loads(guidelines_content)
                # except json.JSONDecodeError:
                #     print(f"Warning: Could not decode JSON from guidelines file '{args.guidelines_file}'. Using raw content as string.")
                config['guidelines'] = guidelines_content.splitlines() # Assuming each line is a guideline
        except IOError:
            print(f"Error: Could not read guidelines file '{args.guidelines_file}'")
            sys.exit(1)

    # Handle output folder argument - overrides default, task config, query file, and guidelines file
    if args.output_folder:
        config['output_folder'] = args.output_folder

    # Handle output filename argument - overrides default, task config, query file, guidelines file, and output folder
    if args.output_filename:
        config['output_file'] = args.output_filename

    # Handle nested publish_formats separately
    if args.publish_markdown is not None:
        config['publish_formats']['markdown'] = args.publish_markdown
    if args.publish_pdf is not None:
        config['publish_formats']['pdf'] = args.publish_pdf
    if args.publish_docx is not None:
        config['publish_formats']['docx'] = args.publish_docx

    # Collect and concatenate query parts from command line arguments in order
    all_query_parts = []
    i = 1 # Start from the second element (index 1) to skip the script name
    while i < len(sys.argv):
        arg = sys.argv[i]
        if arg == "--query":
            if i + 1 < len(sys.argv):
                all_query_parts.append(sys.argv[i+1])
                i += 1 # Skip the value
            else:
                print("Error: --query requires a value.")
                sys.exit(1)
        elif arg == "--query-file":
            if i + 1 < len(sys.argv):
                file_path = sys.argv[i+1]
                if not os.path.exists(file_path):
                    print(f"Error: Query file '{file_path}' not found.")
                    sys.exit(1)
                try:
                    with open(file_path, 'r') as f:
                        all_query_parts.append(f.read().strip())
                except IOError:
                    print(f"Error: Could not read query file '{file_path}'")
                    sys.exit(1)
                i += 1 # Skip the file path
            else:
                print("Error: --query-file requires a file path.")
                sys.exit(1)
        # Add checks for other arguments if necessary to skip their values
        # For now, assuming other arguments are handled by argparse and don't need special skipping here
        # If an argument takes multiple values (like --guidelines), this simple skipping might not be sufficient
        # However, since we are only concerned with --query and --query-file order here, this should be okay.
        i += 1 # Move to the next argument

    # If command line arguments for query were provided, concatenate them
    if all_query_parts:
        config['query'] = " ".join(all_query_parts)
    # If no command line query arguments, the query from task config or default will be used

    return config

async def main():
    parser = argparse.ArgumentParser(description="Multi-agent research CLI")

    # Positional argument for the query
    parser.add_argument("--query", nargs='*', type=str, help="The research query (optional if provided in task config or query file). Can be provided multiple times and will be concatenated.")

    # Optional argument for a task configuration file
    parser.add_argument("--task-config", type=str, help="Path to a task configuration JSON file.")

    # Optional argument for a query file
    parser.add_argument("--query-file", nargs='*', type=str, help="Path to a file containing the research query. Can be provided multiple times and will be concatenated.")

    # Optional argument for guidelines file
    parser.add_argument("--guidelines-file", type=str, help="Path to a file containing the research guidelines.")

    # Optional argument for output folder
    parser.add_argument("--output-folder", type=str, help=f"Set the output folder (default: {DEFAULT_TASK.get('output_folder', 'outputs')})")

    # Optional argument for output filename
    parser.add_argument("--output-filename", type=str, help=f"Set the output filename (default: {DEFAULT_TASK.get('output_file', 'multi_agent_report_<uuid>.md')})")

    # Hardcoded arguments based on task.json
    parser.add_argument("--max-sections", type=int, help=f"Set max_sections (default: {DEFAULT_TASK.get('max_sections')})")

    # Arguments for publish_formats (nested dictionary)
    parser.add_argument("--publish-markdown", action=argparse.BooleanOptionalAction, help=f"Enable/disable markdown output (default: {DEFAULT_TASK.get('publish_formats', {}).get('markdown')})")
    parser.add_argument("--publish-pdf", action=argparse.BooleanOptionalAction, help=f"Enable/disable PDF output (default: {DEFAULT_TASK.get('publish_formats', {}).get('pdf')})")
    parser.add_argument("--publish-docx", action=argparse.BooleanOptionalAction, help=f"Enable/disable DOCX output (default: {DEFAULT_TASK.get('publish_formats', {}).get('docx')})")

    parser.add_argument("--include-human-feedback", action=argparse.BooleanOptionalAction, help=f"Enable/disable human feedback (default: {DEFAULT_TASK.get('include_human_feedback')})")
    parser.add_argument("--follow-guidelines", action=argparse.BooleanOptionalAction, help=f"Enable/disable following guidelines (default: {DEFAULT_TASK.get('follow_guidelines')})")
    parser.add_argument("--model", type=str, help=f"Set the model (default: {DEFAULT_TASK.get('model')})")
    parser.add_argument("--guidelines", nargs="+", type=str, help=f"Set guidelines (default: {DEFAULT_TASK.get('guidelines')})")
    parser.add_argument("--verbose", action=argparse.BooleanOptionalAction, help=f"Enable/disable verbose output (default: {DEFAULT_TASK.get('verbose')})")

    # Add arguments for API keys
    parser.add_argument("--openai-api-key", type=str, help="Set the OpenAI API key.")
    parser.add_argument("--tavily-api-key", type=str, help="Set the Tavily API key.")

    args = parser.parse_args()

    # --- API Key Handling ---
    openai_api_key = args.openai_api_key or os.environ.get("OPENAI_API_KEY")
    tavily_api_key = args.tavily_api_key or os.environ.get("TAVILY_API_KEY")

    keys_obtained_interactively = {}

    if not openai_api_key:
        openai_api_key = input("Please enter your OPENAI_API_KEY: ")
        keys_obtained_interactively["OPENAI_API_KEY"] = openai_api_key

    if not tavily_api_key:
        tavily_api_key = input("Please enter your TAVILY_API_KEY: ")
        keys_obtained_interactively["TAVILY_API_KEY"] = tavily_api_key

    # Write interactively obtained keys to .env file
    if keys_obtained_interactively:
        write_keys_to_env(keys_obtained_interactively)
        # Reload environment variables to include the newly written keys
        load_dotenv(override=True)

    # Ensure keys are available in environment for subsequent calls
    os.environ["OPENAI_API_KEY"] = openai_api_key
    os.environ["TAVILY_API_KEY"] = tavily_api_key
    # --- End API Key Handling ---


    # Load and assemble the task configuration based on the hierarchy
    task_config = load_task_config(args)

    # Ensure query is present after loading config
    if not task_config.get('query'):
        print("Error: No research query provided. Please specify a query via argument or in the task config.")
        sys.exit(1)

    # Instantiate and run the ChiefEditorAgent
    chief_editor = ChiefEditorAgent(task_config)
    print(f"Starting research for query: {task_config['query']}")
    research_report = await chief_editor.run_research_task(task_id=uuid.uuid4())

    if research_report is None:
        print("Error: Research task failed and returned None.")
        return # Exit the main function

    # Handle output (e.g., write to file)
    output_folder = task_config.get('output_folder', 'outputs')
    os.makedirs(output_folder, exist_ok=True)
    output_filename = task_config.get('output_file', f"multi_agent_report_{uuid.uuid4()}.md")
    output_path = os.path.join(output_folder, output_filename)

    # Determine publish formats - default to markdown if not specified
    publish_formats = task_config.get('publish_formats', {'markdown': True})

    # Basic handling for writing the report based on formats
    if publish_formats.get('markdown'):
        md_output_path = os.path.splitext(output_path)[0] + ".md"
        with open(md_output_path, "w", encoding='utf-8') as f:
            # Ensure research_report['report'] is not None before writing
            report_content = research_report.get('report') if research_report else "Research report content not available."
            f.write(report_content)
        print(f"Multi-agent report (Markdown) written to {md_output_path}")

    # Add logic here for PDF and DOCX if the ChiefEditorAgent returns them or if there's a separate publishing step

def write_keys_to_env(keys):
    """
    Writes or updates API keys in a .env file in the ./gpt-researcher/ directory.
    """
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    env_vars = {}

    # Read existing .env file if it exists
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#'):
                    key, value = line.split('=', 1)
                    env_vars[key] = value

    # Update with new keys
    env_vars.update(keys)

    # Write back to .env file
    with open(env_path, 'w') as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    print(f"Updated .env file at {env_path}")


if __name__ == "__main__":
    load_dotenv()
    asyncio.run(main())
