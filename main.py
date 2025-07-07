#!/usr/bin/env python3
"""Lab results monitor - Telegram bot."""

import asyncio
from bot import main as bot_main


def main():
    """Main function - run Telegram bot."""
    asyncio.run(bot_main())


if __name__ == "__main__":
    main()
