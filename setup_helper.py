#!/usr/bin/env python3
"""
Setup helper for School-MCP

This script helps users set up School-MCP with Claude Desktop by:
1. Finding the Claude Desktop config file
2. Adding the necessary configuration to the mcpServers section
3. Setting up environment variables from .env file
"""

import os
import json
import sys
import shutil
import subprocess
from pathlib import Path
import site

def find_claude_config():
    """Find the Claude Desktop configuration file"""
    # Common locations for the Claude Desktop config file
    possible_locations = []
    
    # macOS
    if sys.platform == 'darwin':
        possible_locations.append(Path.home() / "Library/Application Support/Claude/claude_desktop_config.json")
    
    # Windows
    elif sys.platform == 'win32':
        app_data = os.environ.get('APPDATA', '')
        if app_data:
            possible_locations.append(Path(app_data) / "Claude/claude_desktop_config.json")
    
    # Linux
    else:
        config_home = os.environ.get('XDG_CONFIG_HOME', Path.home() / '.config')
        possible_locations.append(Path(config_home) / "Claude/claude_desktop_config.json")
    
    # Check all possible locations
    for location in possible_locations:
        if location.exists():
            return location
    
    return None

def get_package_path():
    """Get the path to the school_mcp package"""
    try:
        # Try to import the module to see if it's installed
        import school_mcp
        return os.path.dirname(os.path.abspath(school_mcp.__file__))
    except ImportError:
        # If the module isn't importable, search in site-packages
        for site_dir in site.getsitepackages():
            potential_path = os.path.join(site_dir, 'school_mcp')
            if os.path.exists(potential_path):
                return potential_path
        
        # If not found in site-packages, check if it's in the current directory
        current_dir = os.getcwd()
        src_path = os.path.join(current_dir, 'src', 'school_mcp')
        if os.path.exists(src_path):
            return src_path
        
        # Last resort: search in the directory structure
        for root, dirs, files in os.walk(current_dir):
            if 'school_mcp' in dirs:
                return os.path.join(root, 'school_mcp')
    
    return None

def find_python_executable():
    """Find the Python executable that has school_mcp installed"""
    # First, try the current Python executable
    current_python = sys.executable
    try:
        # Check if school_mcp is importable with this Python
        result = subprocess.run(
            [current_python, "-c", "import school_mcp; print('Found')"],
            capture_output=True, text=True
        )
        if "Found" in result.stdout:
            return current_python
    except Exception:
        pass
    
    # Try common Python executables
    for python_cmd in ["python", "python3", "python3.8", "python3.9", "python3.10", "python3.11"]:
        try:
            python_path = shutil.which(python_cmd)
            if python_path:
                result = subprocess.run(
                    [python_path, "-c", "import school_mcp; print('Found')"],
                    capture_output=True, text=True
                )
                if "Found" in result.stdout:
                    return python_path
        except Exception:
            continue
    
    # If we can't find a Python with school_mcp, return the current one
    return sys.executable

def get_script_path():
    """Find the path to the school-mcp script"""
    # Look for the script in common locations
    script_name = "school-mcp"
    if sys.platform == 'win32':
        script_name += ".exe"
    
    # Check if the script is in PATH
    script_path = shutil.which(script_name)
    if script_path:
        return script_path
    
    # Check in common locations
    python_path = find_python_executable()
    scripts_dir = os.path.join(os.path.dirname(python_path), "Scripts" if sys.platform == 'win32' else "bin")
    potential_script = os.path.join(scripts_dir, script_name)
    
    if os.path.exists(potential_script):
        return potential_script
    
    # If we can't find the script, we'll use the Python module approach
    return None

def load_env_file(env_path):
    """Load environment variables from .env file"""
    env_vars = {}
    
    if os.path.exists(env_path):
        with open(env_path, 'r') as f:
            for line in f:
                line = line.strip()
                if not line or line.startswith('#'):
                    continue
                    
                key, value = line.split('=', 1)
                env_vars[key.strip()] = value.strip()
    
    return env_vars

def setup_claude_config():
    """Set up the Claude Desktop configuration for School-MCP"""
    config_file = find_claude_config()
    
    if not config_file:
        print("Could not find Claude Desktop configuration file.")
        print("Please manually add the configuration to your Claude Desktop config.")
        print_manual_instructions()
        return False
    
    print(f"Found Claude Desktop configuration at: {config_file}")
    
    # Read the existing config
    try:
        with open(config_file, 'r') as f:
            config = json.load(f)
    except (json.JSONDecodeError, FileNotFoundError):
        # If the file doesn't exist or is not valid JSON, start with an empty config
        config = {}
    
    # Ensure mcpServers section exists
    if 'mcpServers' not in config:
        config['mcpServers'] = {}
    
    # Find the script path or use Python module approach
    script_path = get_script_path()
    package_path = get_package_path()
    python_path = find_python_executable()
    
    if not package_path:
        print("Error: Could not find the school_mcp package.")
        print("Please make sure you have installed the package with 'pip install -e .'")
        return False
    
    print(f"Found Python executable: {python_path}")
    if script_path:
        print(f"Found school-mcp script: {script_path}")
    else:
        print(f"Using Python module approach with package at: {package_path}")
    
    # Look for .env file
    env_path = os.path.join(os.getcwd(), '.env')
    if not os.path.exists(env_path):
        # Try copying from template
        template_path = os.path.join(os.getcwd(), '.env.template')
        if os.path.exists(template_path):
            use_template = input(f"\n.env file not found. Create from template? [Y/n]: ").strip().lower()
            if not use_template or use_template in ('y', 'yes'):
                shutil.copy(template_path, env_path)
                print(f"Created .env file from template. Please edit {env_path} with your credentials.")
                print("After editing, run this script again.")
                return False
    
    # Load environment variables
    env_vars = {}
    if os.path.exists(env_path):
        env_vars = load_env_file(env_path)
        print(f"\nLoaded environment variables from {env_path}")
        
        # Check if credentials are set
        required_vars = ['CANVAS_ACCESS_TOKEN', 'CANVAS_DOMAIN', 'GRADESCOPE_EMAIL', 'GRADESCOPE_PASSWORD']
        missing_vars = [var for var in required_vars if var not in env_vars]
        
        if missing_vars:
            print(f"Warning: Missing required environment variables: {', '.join(missing_vars)}")
            print(f"Please edit {env_path} to include these variables.")
            
            continue_anyway = input("Continue with setup anyway? [y/N]: ").strip().lower()
            if continue_anyway not in ('y', 'yes'):
                return False
    else:
        print("\nNo .env file found.")
        create_env = input("Create .env file now? [Y/n]: ").strip().lower()
        if not create_env or create_env in ('y', 'yes'):
            with open(env_path, 'w') as f:
                f.write("""# Canvas API credentials
CANVAS_ACCESS_TOKEN=your_canvas_token_here
CANVAS_DOMAIN=canvas.your_institution.edu

# Gradescope credentials
GRADESCOPE_EMAIL=your_email@your_institution.edu
GRADESCOPE_PASSWORD=your_gradescope_password
""")
            print(f"Created .env file. Please edit {env_path} with your credentials.")
            print("After editing, run this script again.")
            return False
    
    # Create the configuration
    if script_path:
        # Use the script directly
        school_mcp_config = {
            "command": script_path,
        }
    else:
        # Use the Python module approach
        school_mcp_config = {
            "command": python_path,
            "args": ["-m", "school_mcp"]
        }
    
    # Add environment variables if available
    if env_vars:
        school_mcp_config["env"] = env_vars
    
    # Add to the config
    config['mcpServers']['school-tools'] = school_mcp_config
    
    # Write the updated config back to the file
    try:
        with open(config_file, 'w') as f:
            json.dump(config, f, indent=2)
        
        print("\nSuccessfully updated Claude Desktop configuration!")
        print("School-MCP has been configured as 'school-tools' in Claude Desktop.")
        print("Please restart Claude Desktop for the changes to take effect.")
        return True
    except Exception as e:
        print(f"Error updating configuration file: {str(e)}")
        print_manual_instructions()
        return False

def print_manual_instructions():
    """Print instructions for manual configuration"""
    script_path = get_script_path()
    python_path = find_python_executable()
    
    print("\nManual Configuration Instructions:")
    print("1. Open Claude Desktop")
    print("2. Go to Settings > Developer > Edit Config")
    print("3. Add the following to your claude_desktop_config.json:")
    
    # Create config example based on what we found
    if script_path:
        config_example = {
            "mcpServers": {
                "school-tools": {
                    "command": script_path,
                    "env": {
                        "CANVAS_ACCESS_TOKEN": "your_canvas_token_here",
                        "CANVAS_DOMAIN": "canvas.your_institution.edu",
                        "GRADESCOPE_EMAIL": "your_email@your_institution.edu",
                        "GRADESCOPE_PASSWORD": "your_gradescope_password"
                    }
                }
            }
        }
    else:
        config_example = {
            "mcpServers": {
                "school-tools": {
                    "command": python_path,
                    "args": ["-m", "school_mcp"],
                    "env": {
                        "CANVAS_ACCESS_TOKEN": "your_canvas_token_here",
                        "CANVAS_DOMAIN": "canvas.your_institution.edu",
                        "GRADESCOPE_EMAIL": "your_email@your_institution.edu",
                        "GRADESCOPE_PASSWORD": "your_gradescope_password"
                    }
                }
            }
        }
    
    print(json.dumps(config_example, indent=4))
    print("\n4. Replace the environment variable values with your actual credentials.")
    print("5. Save the file and restart Claude Desktop")

def main():
    """Main function"""
    print("School-MCP Setup Helper")
    print("======================")
    print("This utility will help you configure Claude Desktop to use School-MCP.")
    
    # Run the setup
    success = setup_claude_config()
    
    # Exit with appropriate code
    sys.exit(0 if success else 1)

if __name__ == "__main__":
    main()
