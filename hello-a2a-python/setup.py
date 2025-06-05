#!/usr/bin/env python3
"""
Simple setup script for a2a-examples-local0
"""

import subprocess
import sys
import os
from pathlib import Path

def run_command(command, description):
    """Run a command and handle errors"""
    print(f"Running: {description}")
    try:
        result = subprocess.run(command, shell=True, check=True, capture_output=True, text=True)
        print(f"✓ {description} completed successfully")
        return result.stdout
    except subprocess.CalledProcessError as e:
        print(f"✗ {description} failed: {e}")
        print(f"Error output: {e.stderr}")
        return None

def main():
    """Main setup function"""
    # Check if we're in a virtual environment
    if not hasattr(sys, 'real_prefix') and not (hasattr(sys, 'base_prefix') and sys.base_prefix != sys.prefix):
        print("⚠️  Warning: You're not in a virtual environment!")
        print("It's recommended to create and activate a virtual environment first:")
        print("  python -m venv venv")
        print("  source venv/bin/activate  # On Windows: venv\\Scripts\\activate")
        response = input("Continue anyway? (y/N): ")
        if response.lower() != 'y':
            print("Setup cancelled.")
            return

    # Install requirements
    requirements_file = Path(__file__).parent / "requirements.txt"
    if requirements_file.exists():
        run_command(f"pip install -r {requirements_file}", "Installing requirements")
    else:
        print("✗ requirements.txt not found!")
        return

    print("\n🎉 Setup complete!")
    print("\nNext steps:")
    print("1. Check the README.md for usage instructions")
    print("2. Navigate to frontend/ or backend/ directories")
    print("3. Follow the specific instructions in each component")

if __name__ == "__main__":
    main()
