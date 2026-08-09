@echo off
cd /d "%~dp0"
echo Starting discord-mcp server on port 8091...
uv run python -m discord_mcp.main
pause
