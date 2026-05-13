"""Basic usage example - generate a document using OpenAI"""

from FilePromptForge import file_handler
from pathlib import Path

# Create test files if they don't exist
Path("test_input.txt").write_text("This is a sample document about AI safety.", encoding="utf-8")
Path("test_instructions.txt").write_text("Summarize this document and provide key safety recommendations.", encoding="utf-8")

# Run FPF
result_path = file_handler.run(
    file_a="test_input.txt",
    file_b="test_instructions.txt",
    out_path="result.md",
    provider="openai",
    model="gpt-5-mini"
)

print(f"Result written to: {result_path}")

# Read and display result
with open(result_path, "r", encoding="utf-8") as f:
    print("\n--- Result ---")
    print(f.read())
