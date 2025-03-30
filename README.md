# School MCP

[![smithery badge](https://smithery.ai/badge/@54yyyu/school-mcp)](https://smithery.ai/server/@54yyyu/school-mcp)

A Model Context Protocol (MCP) server for academic tools, integrating with Canvas and Gradescope platforms.

## Features

- **Assignment Deadlines**: Fetch and display upcoming deadlines from Canvas and Gradescope
- **Calendar Integration**: Add deadlines to macOS Calendar or Reminders using AppleScript
- **File Management**: Download course materials from Canvas

## Quickstart

### Installation

#### Installing via Smithery

To install School MCP for Claude Desktop automatically via [Smithery](https://smithery.ai/server/@54yyyu/school-mcp):

```bash
npx -y @smithery/cli install @54yyyu/school-mcp --client claude
```

1. Clone the repository:
```bash
git clone https://github.com/yourusername/school-mcp.git
cd school-mcp
```

2. Install the package:
```bash
pip install -e .
```

3. Set up your environment variables by either:
   - Using the included setup helper (recommended)
   - Creating a `.env` file manually

### Using the Setup Helper

Run the setup helper to configure Claude Desktop automatically:

```bash
python setup_helper.py
```

The setup helper will:
- Find your Claude Desktop configuration file
- Create a `.env` file if needed
- Configure the MCP server with proper paths
- Add your environment variables to the Claude Desktop configuration

### Manual Setup

If you prefer to set up manually:

1. Copy the environment template:
```bash
cp .env.template .env
# Edit .env with your credentials
```

2. Configure Claude Desktop by following the [Claude Desktop Integration Guide](docs/claude_desktop.md).

### Running the server

Run directly:
```bash
python -m school_mcp
```

Or use the convenience script:
```bash
./run_server.py
```

## Tools

- `get_deadlines`: Fetch upcoming assignment deadlines from Canvas and Gradescope
- `add_to_reminders`: Add assignments to macOS Reminders
- `list_courses`: List all available Canvas courses
- `download_course_files`: Download files from a Canvas course
- `set_download_path`: Configure where downloaded files are saved
- `get_download_path_info`: Check the current download location

## Configuration

The server tries to find configuration in this order:
1. Environment variables
2. `.env` file in the current directory
3. Existing `config.json` file in the home directory

## License

MIT
