100% vibe coded btw

---

# Lab Results Monitor

A Telegram bot that monitors lab results at https://lablaudo.com.br/acesso_paciente and notifies you when results are ready, delivering the PDF directly via Telegram.

## Features

- Interactive Telegram bot interface
- Secure credential storage in SQLite database
- Automatic monitoring every 30 minutes
- Instant Telegram notifications when results are ready
- Automatic PDF download and delivery
- Base64 PDF decoding from embedded HTML responses
- Multi-user and group support
- Immediate startup check for all users
- Auto-removal from monitoring after PDF delivery

## Quick Start (Docker)

```bash
docker run -e TELEGRAM_BOT_TOKEN=your_token ghcr.io/caarlos0/lablaudo
```

## Development Setup

# Build wheel

uv build

````

## Usage

1. Create a bot with [@BotFather](https://t.me/BotFather) on Telegram
2. Get your bot token
3. Run the application
4. Start a chat with your bot and use `/start` to begin

### Bot Commands

- `/start` - Welcome message and setup instructions
- `/add` - Add your lab portal credentials (supports multiple)
- `/remove` - Remove stored credentials
- `/remove_all` - Remove all stored credentials
- `/check` - Check your results immediately
- `/status` - Show your monitoring status
- `/help` - Show help message

## How it Works

1. **Startup Check**: When the bot starts, it immediately checks all stored credentials
2. **Login**: Authenticates with the patient portal
3. **Parse Results**: Finds all table rows containing lab results
4. **Check Status**: Examines each row for green indicators (ready status)
5. **PDF Download**: Searches for "Visualizar Laudo" or "Baixar" links
6. **Base64 Decoding**: Extracts PDF content from embedded base64 data in HTML responses
7. **Delivery**: Downloads PDF using authenticated session and sends directly via Telegram
8. **Auto-cleanup**: Removes credential from monitoring after successful PDF delivery
9. **Periodic Monitoring**: Continues checking every 30 minutes for remaining credentials

## Release

Releases are automated with [GoReleaser](https://goreleaser.com). It builds the Python wheel/sdist and publishes a Docker image to `ghcr.io/caarlos0/lablaudo`.

```bash
goreleaser release --snapshot --clean
````
