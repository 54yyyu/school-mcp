#!/usr/bin/env python3
"""
Simple entry point script for the School MCP server.
"""

import sys
import os

# Add the src directory to the Python path
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "src"))

from school_mcp.server import mcp

if __name__ == "__main__":
    mcp.run()
