# Lab Results Monitor

A Telegram bot that monitors lab results at https://lablaudo.com.br/acesso_paciente and provides notifications when results are ready. Available as both a Python application and a standalone executable binary.

## Features

- 🤖 Interactive Telegram bot interface
- 🔐 Secure credential storage in SQLite database
- ⏰ Automatic monitoring every 30 minutes
- 📱 Instant Telegram notifications when results are ready
- 📄 **Automatic PDF download and delivery** when results are available
- 🔓 **Base64 PDF decoding** from embedded HTML responses
- 👥 Multi-user support
- 📊 Status tracking and monitoring history
- ✅ **Immediate startup check** - Checks all users when bot starts
- 🔄 **Auto-removal from monitoring after PDF delivery**
- 📦 **Standalone executable binary** - No Python installation required

## Quick Start (Executable Binary)

### Download and Run
```bash
# Download the latest release (or build from source)
wget https://github.com/your-repo/lablaudo/releases/latest/download/lablaudo

# Make executable
chmod +x lablaudo

# Run with your bot token
TELEGRAM_BOT_TOKEN=your_bot_token_here ./lablaudo
```

### Build from Source
```bash
# Clone repository
git clone https://github.com/your-repo/lablaudo.git
cd lablaudo

# Build executable (requires UV)
python build.py

# Run
TELEGRAM_BOT_TOKEN=your_token ./dist/lablaudo
```

## Development Setup

1. Create and activate virtual environment:
```bash
python3 -m venv venv
source venv/bin/activate
```

2. Install dependencies:
```bash
pip install -e .
```

3. Run in development mode:
```bash
export TELEGRAM_BOT_TOKEN=your_bot_token_here
python3 main.py
```

## Usage

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram
2. Get your bot token
3. Run the application (binary or Python)
4. Start a chat with your bot and use `/start` to begin

### Bot Commands

- `/start` - Welcome message and setup instructions
- `/add` - Add your lab portal credentials
- `/remove` - Remove your stored credentials  
- `/check` - Check your results immediately
- `/status` - Show your monitoring status
- `/help` - Show help message

## How it Works

1. **Startup Check**: When the bot starts, it immediately checks all stored users for ready results
2. **Login**: Authenticates with the patient portal using provided credentials
3. **Parse Results**: Finds all table rows (`<tr>`) containing lab results
4. **Check Status**: Examines each row's background color/style for green indicators (`bgcolor="#8FF08F"` and "Liberado" status)
5. **PDF Download**: When all results are ready, searches for "Visualizar Laudo" or "Baixar" links
6. **Base64 Decoding**: Extracts PDF content from embedded base64 data in HTML responses
7. **Delivery**: Downloads PDF using authenticated session and sends directly to user via Telegram
8. **Auto-cleanup**: Removes user from monitoring after successful PDF delivery
9. **Periodic Monitoring**: Continues checking every 30 minutes for remaining users

## Binary Distribution

### Features
- **Self-contained**: Includes Python runtime and all dependencies
- **No installation required**: Just download and run
- **Cross-platform**: Available for macOS, Linux, and Windows
- **Small size**: ~12MB executable
- **Fast startup**: Optimized for quick bot initialization

### System Requirements
- **macOS**: 10.14+ (arm64/x86_64)
- **Linux**: glibc 2.17+ (x86_64/arm64)
- **Windows**: Windows 10+ (x86_64)

### Deployment Options

#### As a systemd service (Linux):
```bash
sudo cp lablaudo /usr/local/bin/
sudo tee /etc/systemd/system/lablaudo.service > /dev/null <<EOF
[Unit]
Description=Lab Results Monitor Bot
After=network.target

[Service]
Type=simple
Environment=TELEGRAM_BOT_TOKEN=your_token_here
ExecStart=/usr/local/bin/lablaudo
Restart=always

[Install]
WantedBy=multi-user.target
EOF

sudo systemctl enable lablaudo
sudo systemctl start lablaudo
```

#### As a launchd daemon (macOS):
```bash
sudo cp lablaudo /usr/local/bin/
# See BUILD.md for complete launchd setup
```

## Database Schema

The bot uses SQLite to store user data:

```sql
CREATE TABLE users (
    telegram_id INTEGER PRIMARY KEY,
    username TEXT NOT NULL,
    password TEXT NOT NULL,
    active INTEGER DEFAULT 1,
    created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
    last_check TIMESTAMP,
    last_status TEXT
);
```

## Dependencies

- `requests`: HTTP client for web scraping
- `beautifulsoup4`: HTML parsing
- `python-telegram-bot`: Telegram bot framework
- `apscheduler`: Periodic task scheduling

## Security

- Credentials are stored locally in SQLite database
- No data is transmitted to external services except the lab portal
- Bot token should be kept secure and not committed to version control
- PDF files are temporarily processed in memory and not stored on disk

## Development

### Run tests:
```bash
source venv/bin/activate
python3 test_bot.py
python3 test_pdf.py
```

### Build executable:
```bash
python build.py
```

See [BUILD.md](BUILD.md) for detailed build and deployment instructions.