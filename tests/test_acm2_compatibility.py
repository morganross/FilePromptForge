"""Tests to ensure acm2 compatibility is maintained"""

import sys
import inspect
from pathlib import Path

# Add parent to path for imports
sys.path.insert(0, str(Path(__file__).parent))

from FilePromptForge.file_handler import run
from FilePromptForge.grounding_enforcer import ValidationError

def test_run_signature():
    """Verify run() has all parameters acm2 expects"""
    sig = inspect.signature(run)
    params = sig.parameters
    
    # All these must exist for acm2 compatibility
    required = [
        "file_a", "file_b", "out_path", "config_path", 
        "env_path", "provider", "model", "reasoning_effort",
        "max_completion_tokens", "timeout", "fpf_max_retries",
        "fpf_retry_delay", "request_json", "web_search"
    ]
    
    for param in required:
        assert param in params, f"Missing required parameter: {param}"
    
    print("✅ test_run_signature passed")

def test_validation_error_attributes():
    """Verify ValidationError has required attributes"""
    assert hasattr(ValidationError, "missing_grounding")
    assert hasattr(ValidationError, "missing_reasoning")
    
    # Create instance and check
    err = ValidationError("test", missing_grounding=True, missing_reasoning=False)
    assert err.missing_grounding == True
    assert err.missing_reasoning == False
    assert err.category == "validation_grounding"
    
    print("✅ test_validation_error_attributes passed")

def test_no_acm2_imports():
    """Verify core FPF files have no acm2 imports"""
    import FilePromptForge.file_handler as fh
    import FilePromptForge.grounding_enforcer as ge
    
    # Check that no acm2 imports exist
    for module in [fh, ge]:
        source = inspect.getsource(module)
        assert "from app." not in source, "Found acm2 import in core file"
        assert "import app." not in source, "Found acm2 import in core file"
        assert "from acm2." not in source, "Found acm2 import in core file"
    
    print("✅ test_no_acm2_imports passed")

def test_cli_help():
    """Test that CLI help works"""
    import subprocess
    
    result = subprocess.run(
        [sys.executable, "-m", "FilePromptForge.fpf_main", "--help"],
        capture_output=True,
        text=True,
        cwd=str(Path(__file__).parent)
    )
    
    assert result.returncode == 0, f"CLI help failed: {result.stderr}"
    assert "--file-a" in result.stdout
    assert "--provider" in result.stdout
    
    print("✅ test_cli_help passed")

if __name__ == "__main__":
    test_run_signature()
    test_validation_error_attributes()
    test_no_acm2_imports()
    test_cli_help()
    print("\n✅ All acm2 compatibility tests passed!")
