#!/usr/bin/env python3
"""
Quick verification script to check the current state of recommendation agent components.
Run this while the refactoring workflow is in progress.
"""

import sys
import os
import importlib.util

# Add the project root to the path
sys.path.append(os.path.dirname(os.path.abspath(__file__)))

def check_module_exists(module_path):
    """Check if a module file exists and can be imported."""
    if os.path.exists(module_path):
        try:
            module_name = os.path.basename(module_path).replace('.py', '')
            spec = importlib.util.spec_from_file_location(module_name, module_path)
            module = importlib.util.module_from_spec(spec)
            # Don't actually import to avoid side effects
            return True, f"✓ Module exists: {module_path}"
        except Exception as e:
            return False, f"✗ Module error: {module_path} - {str(e)}"
    else:
        return False, f"✗ Module missing: {module_path}"

def check_database_config():
    """Check database configuration."""
    env_path = os.path.join(os.path.dirname(__file__), '.env')
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            content = f.read()
            if 'DATABASE_URL' in content:
                if 'psycopg2' in content:
                    return True, "✓ Database configured with psycopg2"
                elif 'psycopg3' in content:
                    return False, "✗ Database still using psycopg3 (problematic)"
                else:
                    return True, "✓ Database URL configured"
            else:
                return False, "✗ DATABASE_URL not found in .env"
    else:
        return False, "✗ .env file not found"

def check_polyvore_data():
    """Check if Polyvore training data exists."""
    data_dir = os.path.join(os.path.dirname(os.path.dirname(__file__)), 'polyvore_data')
    if os.path.exists(data_dir):
        files = os.listdir(data_dir)
        if any('polyvore' in f.lower() or 'train' in f.lower() for f in files):
            return True, f"✓ Polyvore data found ({len(files)} files)"
        else:
            return False, f"✗ Polyvore data directory exists but no training files found"
    else:
        return False, "✗ polyvore_data directory not found"

def main():
    print("=== Current State Verification ===")
    print("Checking while refactoring workflow runs...\n")
    
    # Key modules to check
    modules_to_check = [
        ('backend/app/agents/recommendation_agent_v2.py', 'Main recommendation agent'),
        ('backend/app/ml/recommendation_llm.py', 'LLM integration'),
        ('backend/app/ml/outfit_composition_sft_model.py', 'SFT model'),
        ('backend/app/services/weather_verification.py', 'Weather service'),
        ('backend/app/ml/explanation_engine.py', 'Explanation engine'),
        ('backend/train_sft_simple.py', 'SFT training script'),
        ('backend/app/api/rlhf.py', 'RLHF API'),
    ]
    
    all_ok = True
    for module_path, description in modules_to_check:
        full_path = os.path.join(os.path.dirname(os.path.dirname(__file__)), module_path)
        exists, message = check_module_exists(full_path)
        print(f"{description}: {message}")
        if not exists:
            all_ok = False
    
    print("\n=== Configuration Checks ===")
    
    # Database config
    db_ok, db_msg = check_database_config()
    print(f"Database: {db_msg}")
    if not db_ok:
        all_ok = False
    
    # Polyvore data
    data_ok, data_msg = check_polyvore_data()
    print(f"Training data: {data_msg}")
    if not data_ok:
        all_ok = False
    
    print("\n=== Summary ===")
    if all_ok:
        print("✓ All key components appear to be in place.")
        print("The refactoring workflow should focus on code quality and bug fixes.")
    else:
        print("⚠ Some components are missing or misconfigured.")
        print("The refactoring workflow will need to address these issues.")
    
    return 0 if all_ok else 1

if __name__ == "__main__":
    sys.exit(main())