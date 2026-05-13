"""Custom prompt template example"""

from FilePromptForge import file_handler, helpers
from pathlib import Path

# Create a prompt template
template = """You are an expert analyst.

Instructions: {{file_b}}

Document to analyze:
{{file_a}}

Provide a detailed analysis with citations.
"""

# Save template
Path("custom_template.txt").write_text(template, encoding="utf-8")

# Create input files
Path("document.txt").write_text("AI has transformed many industries...", encoding="utf-8")
Path("task.txt").write_text("Analyze the impact of AI on healthcare.", encoding="utf-8")

# Use compose_input with template
prompt = helpers.compose_input(
    file_a="document.txt",
    file_b="task.txt",
    prompt_template="custom_template.txt"
)

print("Composed prompt:")
print(prompt[:500] + "...")
