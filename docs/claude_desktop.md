# Using with Claude Desktop

To use this MCP server with Claude Desktop, follow these steps:

1. Install the MCP server:
```bash
cd school-mcp
pip install -e .
```

2. Configure Claude Desktop by editing the configuration file:

- macOS: `~/Library/Application Support/Claude/claude_desktop_config.json`
- Windows: `%APPDATA%\Claude\claude_desktop_config.json`

3. Add this configuration to the JSON file:

```json
{
  "mcpServers": {
    "school-tools": {
      "command": "school-mcp",
      "env": {
        "CANVAS_ACCESS_TOKEN": "your_canvas_token",
        "CANVAS_DOMAIN": "canvas.your_institution.edu",
        "GRADESCOPE_EMAIL": "your_email@your_institution.edu",
        "GRADESCOPE_PASSWORD": "your_gradescope_password"
      }
    }
  }
}
```

Alternatively, if you've set up a `.env` file in your home directory, you can use a simpler configuration:

```json
{
  "mcpServers": {
    "school-tools": {
      "command": "school-mcp"
    }
  }
}
```

4. Restart Claude Desktop to apply the changes.

## Available Tools

Once connected, you'll have access to the following tools:

- `get_deadlines`: Fetch upcoming assignment deadlines from Canvas and Gradescope
- `add_to_reminders`: Add assignments to macOS Reminders (only works on macOS)
- `list_courses`: List all available Canvas courses
- `download_course_files`: Download files from a Canvas course
- `set_download_path`: Configure where downloaded files are saved
- `get_download_path_info`: Check the current download location

## Example Prompts

Here are some example prompts to use with Claude Desktop:

- "What assignments do I have due in the next week?"
- "Add all my upcoming assignments to Reminders"
- "Download files from my biology course"
- "Show me a list of my active courses"
- "Set the download path to ~/Documents/School"
