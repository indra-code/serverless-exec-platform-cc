#!/usr/bin/env python3
"""
Fixes Docker credential store issues by patching the .docker/config.json file temporarily.
This script will:
1. Back up the current Docker config
2. Create a simple config that doesn't use credential store
3. Apply the patch to the FastAPI app
"""

import os
import json
import shutil
import sys
import subprocess

# Docker config path
docker_config_path = os.path.expanduser('~/.docker/config.json')
backup_config_path = os.path.expanduser('~/.docker/config.json.backup')
no_creds_config_path = os.path.expanduser('~/.docker-no-creds/config.json')

def backup_docker_config():
    """Back up the current Docker config"""
    if os.path.exists(docker_config_path):
        shutil.copy2(docker_config_path, backup_config_path)
        print(f"Backed up Docker config to {backup_config_path}")
    else:
        print("No Docker config found to back up")

def create_simple_config():
    """Create a simple Docker config without credential store"""
    simple_config = {
        "auths": {
            "https://index.docker.io/v1/": {}
        },
        "credsStore": ""
    }
    
    # Create a separate config for environment variable use
    os.makedirs(os.path.dirname(no_creds_config_path), exist_ok=True)
    with open(no_creds_config_path, 'w') as f:
        json.dump(simple_config, f, indent=2)
    
    # Also update the main config
    os.makedirs(os.path.dirname(docker_config_path), exist_ok=True)
    with open(docker_config_path, 'w') as f:
        json.dump(simple_config, f, indent=2)
    
    print(f"Created simple Docker config at {docker_config_path}")
    print(f"Created alternative Docker config at {no_creds_config_path}")

def patch_docker_client():
    """Create a patch for the Docker client in the FastAPI app"""
    patch_file = 'api/app/patches/docker_patch.py'
    os.makedirs(os.path.dirname(patch_file), exist_ok=True)
    
    with open(patch_file, 'w') as f:
        f.write("""
# Docker client patch to bypass credential store issues
from docker import client
from docker.utils import config

# The config module has changed, we need to patch config._get_credstore_env function
if hasattr(config, '_get_credstore_env'):
    original_get_credstore_env = config._get_credstore_env
    
    def patched_get_credstore_env(*args, **kwargs):
        # Skip credential store entirely
        return None
    
    # Apply the patch
    config._get_credstore_env = patched_get_credstore_env
    
# Simpler approach: modify the config.get_config_header function if it exists
if hasattr(config, 'get_config_header'):
    original_get_config_header = config.get_config_header
    
    def patched_get_config_header(*args, **kwargs):
        cfg = original_get_config_header(*args, **kwargs)
        if isinstance(cfg, dict) and 'credsStore' in cfg:
            cfg['credsStore'] = ''
        return cfg
    
    # Apply the patch
    config.get_config_header = patched_get_config_header

# Another approach: directly patch the config data structure
if hasattr(config, 'load_config'):
    original_load_config = config.load_config
    
    def patched_load_config(*args, **kwargs):
        cfg = original_load_config(*args, **kwargs)
        if 'credsStore' in cfg:
            cfg['credsStore'] = ''
        return cfg
    
    # Apply the patch
    config.load_config = patched_load_config

# If no specific patch worked, create a general monkey patch for config.py
try:
    # Tell Docker not to use credential helpers
    import os
    os.environ['DOCKER_CONFIG'] = os.path.expanduser('~/.docker-no-creds')
except Exception as e:
    print(f"Warning: Failed to set up Docker config environment: {e}")

# Add a warning function to inform that we're patching Docker client
def show_patched_warning():
    import warnings
    warnings.warn("Docker credentials store has been patched to prevent authentication errors", UserWarning)

# Show the warning
show_patched_warning()
""")
    
    print(f"Created Docker client patch at {patch_file}")

def create_init_file():
    """Create __init__.py in the patches directory"""
    init_file = 'api/app/patches/__init__.py'
    with open(init_file, 'w') as f:
        f.write('# Docker client patches')
    
    print(f"Created {init_file}")

def create_env_file():
    """Create a .env file for the FastAPI app"""
    env_file = '.env'
    
    # Check if the .env file already exists
    env_vars = {}
    if os.path.exists(env_file):
        with open(env_file, 'r') as f:
            for line in f:
                if '=' in line and not line.strip().startswith('#'):
                    key, value = line.strip().split('=', 1)
                    env_vars[key] = value
    
    # Add the DOCKER_CONFIG variable
    env_vars['DOCKER_CONFIG'] = os.path.expanduser('~/.docker-no-creds')
    
    # Write the .env file
    with open(env_file, 'w') as f:
        for key, value in env_vars.items():
            f.write(f"{key}={value}\n")
    
    print(f"Created/updated {env_file} with DOCKER_CONFIG environment variable")

def modify_main_app():
    """Modify the main.py file to import the patch"""
    main_file = 'api/app/main.py'
    
    if not os.path.exists(main_file):
        print(f"Error: {main_file} not found")
        return False
    
    with open(main_file, 'r') as f:
        content = f.read()
    
    # Check if the patch is already imported
    if "from .patches import docker_patch" in content:
        print("Patch already imported in main.py")
        return True
    
    # Add the import right after the existing imports
    import_line = "from .patches import docker_patch  # Fix Docker credential store issues\n"
    
    # Find the last import line
    import_section_end = 0
    lines = content.split('\n')
    for i, line in enumerate(lines):
        if line.startswith('import ') or line.startswith('from '):
            import_section_end = i + 1
    
    # Insert our import
    lines.insert(import_section_end, import_line)
    
    # Write the modified content
    with open(main_file, 'w') as f:
        f.write('\n'.join(lines))
    
    print(f"Modified {main_file} to import the Docker credential store patch")
    return True

def start_api_server():
    """Start the API server with environment variables"""
    env = os.environ.copy()
    env['DOCKER_CONFIG'] = os.path.expanduser('~/.docker-no-creds')
    
    # Run the server with the updated environment
    subprocess.run(
        ['python', '-m', 'uvicorn', 'api.app.main:app', '--reload'],
        env=env
    )

if __name__ == "__main__":
    print("Fixing Docker credential store issues...")
    
    backup_docker_config()
    create_simple_config()
    patch_docker_client()
    create_init_file()
    create_env_file()
    modify_main_app()
    
    print("\nFix applied! You can now run the FastAPI server with:")
    print("DOCKER_CONFIG=~/.docker-no-creds python -m uvicorn api.app.main:app --reload")
    
    choice = input("\nWould you like to run the server now? (y/n): ")
    if choice.lower() == 'y':
        start_api_server()
    else:
        print("Run the server manually when you're ready!") 