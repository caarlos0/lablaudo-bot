# Agent Configuration

## Commands

- **Setup**: `uv sync`
- **Run Bot**: `TELEGRAM_BOT_TOKEN=your_token uv run -m lablaudo`
- **Test**: `uv run python -m pytest`
- **Single test**: `uv run python -m pytest path/to/test_file.py::test_function`
- **Lint**: `uv run ruff check .`
- **Format**: `uv run ruff format .`
- **Build**: `uv build`

## Environment Variables

- **TELEGRAM_BOT_TOKEN**: Bot token from @BotFather (required)
- **DATA_DIR**: Directory for storing the SQLite database (default: `.`, Docker default: `/data`)

## Bot Commands

- `/start` - Welcome message and setup instructions
- `/add` - Add lab portal credentials (supports multiple per user)
- `/remove <username>` - Remove credentials by username
- `/check` - Check all results immediately (with PDF delivery)
- `/status` - Show monitoring status for all credentials
- `/help` - Show help message

## Bot Features

- **PDF Download**: Automatically finds and downloads PDF results using "Visualizar Laudo"/"Baixar" links
- **Base64 Decoding**: Extracts PDF from embedded base64 data in HTML responses
- **Auto-delivery**: Sends PDF files directly via Telegram
- **Multiple credentials**: Each user/group can monitor several lab results simultaneously
- **Auto-cleanup**: Removes individual credentials from monitoring after PDF delivery
- **Group support**: Works in groups — credentials and results are scoped to the chat (DM or group)
- **Startup check**: Runs full check for all users immediately when bot starts
- **Periodic monitoring**: Continues checking once a day
- **Error handling**: Comprehensive fallback notifications
- **Browser impersonation**: Uses `curl_cffi` with `impersonate="chrome"` (real Chrome TLS/JA3 fingerprint + headers) so Cloudflare doesn't 403 the crawler as a bot

## Docker

- **Image**: `ghcr.io/caarlos0/lablaudo`
- **Base**: `ghcr.io/astral-sh/uv:python3.13-trixie-slim`
- **Volume**: `/data` (stores `lablaudo.db`)
- **Run**: `docker run -v lablaudo-data:/data -e TELEGRAM_BOT_TOKEN=your_token ghcr.io/caarlos0/lablaudo`

## Code Style

- **Python version**: 3.13+
- **Imports**: Standard library first, third-party, then local imports with blank lines between groups
- **Formatting**: Use ruff for consistent formatting (120 char line length recommended)
- **Types**: Add type hints for function parameters and return values
- **Naming**: snake_case for variables/functions, PascalCase for classes, UPPER_CASE for constants
- **Error handling**: Use specific exception types, avoid bare except clauses
- **Docstrings**: Use Google-style docstrings for public functions and classes
- **Functions**: Keep functions focused and under 20 lines when possible
- **Variables**: Use descriptive names, avoid single-letter variables except for loops

## Project Structure

- Package: `src/lablaudo/` (hatchling build with src layout)
- Entry point: `src/lablaudo/__main__.py` (invoked via `python -m lablaudo`)
- Bot: `src/lablaudo/bot.py` (with PDF delivery and startup checks)
- Crawler: `src/lablaudo/crawler.py` (with PDF download and base64 decoding)
- Database: `src/lablaudo/database.py`
- Tests: `test_*.py` at project root
- Build: `pyproject.toml` with hatchling backend
- Docker: `Dockerfile`
- SQLite database: `lablaudo.db` (created at runtime in `DATA_DIR`)
