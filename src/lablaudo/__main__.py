"""Lab results monitor - Telegram bot."""

import asyncio

from lablaudo.bot import main as bot_main


def main():
    """Entry point for script console."""
    asyncio.run(bot_main())


if __name__ == "__main__":
    main()
