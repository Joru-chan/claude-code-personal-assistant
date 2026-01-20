#!/usr/bin/env python3
"""
Setup verification script.

Checks that the development environment is properly configured.

Usage:
    python scripts/verify_setup.py
"""

import os
import subprocess
import sys
from pathlib import Path


def check_python_version():
    """Check Python version >= 3.10"""
    version = sys.version_info
    if version < (3, 10):
        return False, f"Python {version.major}.{version.minor} (need 3.10+)"
    return True, f"Python {version.major}.{version.minor}.{version.micro}"


def check_file_exists(path: str, description: str):
    """Check if a file exists"""
    if Path(path).exists():
        return True, description
    return False, f"{description} (missing: {path})"


def check_env_var(name: str, description: str):
    """Check if environment variable is set"""
    value = os.getenv(name)
    if value:
        masked = value[:8] + "..." if len(value) > 8 else "***"
        return True, f"{description} ({masked})"
    return False, f"{description} (not set)"


def check_command(cmd: list, description: str):
    """Check if a command is available"""
    try:
        result = subprocess.run(
            cmd, 
            capture_output=True, 
            text=True, 
            timeout=5
        )
        if result.returncode == 0:
            return True, description
        return False, f"{description} (command failed)"
    except (FileNotFoundError, subprocess.TimeoutExpired):
        return False, f"{description} (not found)"


def main():
    print("🔍 Verifying setup...\n")
    
    checks = [
        ("Python Version", check_python_version()),
        ("AGENT_GUIDE.md", check_file_exists("AGENT_GUIDE.md", "Agent guide")),
        ("PERSONAL_CONTEXT.md", check_file_exists("PERSONAL_CONTEXT.md", "Personal context")),
        ("vm/config.sh", check_file_exists("vm/config.sh", "VM configuration")),
        ("scripts/agent.py", check_file_exists("scripts/agent.py", "Agent router")),
        ("Notion Token", check_env_var("NOTION_TOKEN", "NOTION_TOKEN env var")),
        ("Git", check_command(["git", "--version"], "Git available")),
    ]
    
    # Optional checks
    optional_checks = [
        ("Codex CLI", check_command(["codex", "--version"], "Codex CLI")),
        ("Docker", check_command(["docker", "--version"], "Docker")),
    ]
    
    passed = 0
    failed = 0
    
    print("Required:")
    for name, (success, message) in checks:
        status = "✓" if success else "✗"
        print(f"  {status} {name}: {message}")
        if success:
            passed += 1
        else:
            failed += 1
    
    print("\nOptional:")
    for name, (success, message) in optional_checks:
        status = "✓" if success else "○"
        print(f"  {status} {name}: {message}")
    
    print(f"\n{'='*60}")
    if failed == 0:
        print("✅ Setup verification passed!")
        print("\nNext steps:")
        print("  1. Review AGENT_GUIDE.md for workflows")
        print("  2. Check PERSONAL_CONTEXT.md for database IDs")
        print("  3. Run: python scripts/agent.py 'show tool requests'")
        return 0
    else:
        print(f"❌ {failed} required check(s) failed")
        print("\nPlease review:")
        print("  - SETUP_CODEX.md for setup instructions")
        print("  - PERSONAL_CONTEXT.md for configuration details")
        return 1


if __name__ == "__main__":
    sys.exit(main())
