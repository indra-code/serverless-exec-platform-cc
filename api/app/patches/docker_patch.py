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
    os.makedirs(os.environ['DOCKER_CONFIG'], exist_ok=True)
    with open(os.path.join(os.environ['DOCKER_CONFIG'], 'config.json'), 'w') as f:
        f.write('{"auths":{"https://index.docker.io/v1/":{}},"credsStore":""}')
except Exception as e:
    print(f"Warning: Failed to set up Docker config environment: {e}")

# Add a warning function to inform that we're patching Docker client
def show_patched_warning():
    import warnings
    warnings.warn("Docker credentials store has been patched to prevent authentication errors", UserWarning)

# Show the warning
show_patched_warning()
