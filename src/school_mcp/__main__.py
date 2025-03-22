#!/usr/bin/env python3
"""CLI script to run the School MCP server."""

import sys
import argparse
from school_mcp.server import mcp

def main():
    """Run the School MCP server."""
    parser = argparse.ArgumentParser(description="School MCP Server")
    parser.add_argument(
        "--transport", 
        default="stdio", 
        choices=["stdio", "sse"], 
        help="Transport protocol to use"
    )
    parser.add_argument(
        "--host", 
        default="localhost", 
        help="Host for SSE transport (ignored for stdio)"
    )
    parser.add_argument(
        "--port", 
        type=int, 
        default=8080, 
        help="Port for SSE transport (ignored for stdio)"
    )
    
    args = parser.parse_args()
    
    try:
        if args.transport == "stdio":
            mcp.run(transport="stdio")
        else:
            mcp.run(transport="sse", host=args.host, port=args.port)
    except Exception as e:
        print(f"Error running server: {str(e)}", file=sys.stderr)
        sys.exit(1)

if __name__ == "__main__":
    main()
