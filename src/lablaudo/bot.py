#!/usr/bin/env python3
"""Telegram bot for lab results monitoring."""

import asyncio
import os
import re
import signal
import logging

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lablaudo.database import Database
from lablaudo.crawler import LabCrawler


# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)

_MD2_ESCAPE_RE = re.compile(r'([_*\[\]()~`>#+\-=|{}.!])')


def escape_md(text: str) -> str:
    """Escape special characters for Telegram MarkdownV2."""
    return _MD2_ESCAPE_RE.sub(r'\\\1', str(text))


def _resolve_db_path() -> str:
    """Resolve the database path from DATA_DIR env var."""
    data_dir = os.environ.get("DATA_DIR", ".")
    os.makedirs(data_dir, exist_ok=True)
    return os.path.join(data_dir, "lablaudo.db")


class LabBot:
    """Telegram bot for monitoring lab results."""
    
    def __init__(self, token: str):
        self.token = token
        self.db = Database(_resolve_db_path())
        self.scheduler = AsyncIOScheduler()
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command handlers."""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("add", self.add_credentials))
        self.application.add_handler(CommandHandler("remove", self.remove_credentials))
        self.application.add_handler(CommandHandler("check", self.check_now))
        self.application.add_handler(CommandHandler("status", self.status))
        
        # Handle text messages for credential input
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message."""
        welcome_text = (
            "🧪 *Lab Results Monitor Bot*\n\n"
            "I can monitor your lab results at lablaudo\\.com\\.br "
            "and notify you when they're ready\\!\n\n"
            "*Commands:*\n"
            "/add \\- Add lab credentials\n"
            "/remove \\- Remove credentials by username\n"
            "/check \\- Check results now\n"
            "/status \\- Show current status\n"
            "/help \\- Show this help message\n\n"
            "Use /add to get started\\! You can add multiple "
            "credentials to monitor several results at once\\."
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = (
            "*Available Commands:*\n\n"
            "/add \\- Add lab portal credentials \\(can add multiple\\)\n"
            "/remove \\- Remove credentials by username\n"
            "/check \\- Check all your results immediately\n"
            "/status \\- Show your monitoring status\n"
            "/help \\- Show this help message\n\n"
            "*How it works:*\n"
            "1\\. Use /add to store your lab portal credentials\n"
            "2\\. You can add multiple credentials for different results\n"
            "3\\. I'll check all your results every 30 minutes\n"
            "4\\. You'll get notified when results are ready \\(green status\\)\n"
            "5\\. Each credential is removed automatically after its PDF is delivered\n\n"
            "_Privacy: Your credentials are stored securely and only used to check your results\\._"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)
    
    async def _save_credentials(self, update: Update, username: str, password: str):
        """Validate and save credentials."""
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            "Testing your credentials\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        
        crawler = LabCrawler()
        if crawler.login(username, password):
            if self.db.add_credential(chat_id, username, password):
                creds = self.db.get_credentials(chat_id)
                count = len(creds)
                await update.message.reply_text(
                    f"✅ Credentials saved\\! You now have {escape_md(count)} credential\\(s\\) being monitored\\.\n"
                    "I'll check your results every 30 minutes and notify you when they're ready\\.\n\n"
                    "Use /add again to add more, or /status to see all\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            else:
                await update.message.reply_text(
                    "❌ Failed to save credentials\\. Please try again\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        else:
            await update.message.reply_text(
                "❌ Login failed\\. Please check your credentials and try again\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    
    async def add_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add credentials. Usage: /add username password"""
        if context.args and len(context.args) == 2:
            await self._save_credentials(update, context.args[0], context.args[1])
            return
        
        await update.message.reply_text(
            "Usage: `/add username password`\n\n"
            "Example: `/add 12345678 ABC123DEF`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        await update.message.reply_text(
            "Use /help to see available commands\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    
    async def remove_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove credentials by username. Usage: /remove username"""
        chat_id = update.effective_chat.id

        if not context.args or len(context.args) != 1:
            creds = self.db.get_credentials(chat_id)
            if not creds:
                await update.message.reply_text(
                    "❌ No credentials found to remove\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
            msg = "Usage: `/remove username`\n\nYour credentials:\n"
            for _, username, _ in creds:
                msg += f"  `{escape_md(username)}`\n"
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
            return

        username = context.args[0]
        if self.db.remove_credential_by_username(chat_id, username):
            await update.message.reply_text(
                f"✅ Credentials for {escape_md(username)} removed\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                "❌ Credential not found\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    
    async def _check_single_credential(
        self,
        chat_id: int,
        cred_id: int,
        username: str,
        password: str,
        send_message,
        send_document,
        label: str = "",
    ):
        """Check results for a single credential. Returns status string."""
        prefix = f"\\[{escape_md(username)}\\] " if label else ""
        try:
            crawler = LabCrawler()
            if crawler.login(username, password):
                if crawler.check_results():
                    pdf_url = crawler.get_pdf_link()
                    if pdf_url:
                        pdf_data = crawler.download_pdf(pdf_url)
                        if pdf_data:
                            pdf_content, filename = pdf_data
                            await send_document(
                                document=pdf_content,
                                filename=filename,
                                caption=f"🎉 {prefix}*Lab Results Ready\\!*\n\nYour lab results are attached\\.",
                                caption_parse_mode=ParseMode.MARKDOWN_V2,
                            )
                            self.db.remove_credential(chat_id, cred_id)
                            logger.info(f"Delivered PDF for credential {cred_id} (chat {chat_id}) and removed")
                            return "results_delivered"
                        else:
                            await send_message(
                                f"🎉 {prefix}*Lab Results Ready\\!*\n\n"
                                "Results available on the portal, but I couldn't download the PDF\\.",
                                parse_mode=ParseMode.MARKDOWN_V2,
                            )
                    else:
                        await send_message(
                            f"🎉 {prefix}*Lab Results Ready\\!*\n\n"
                            "Your results are available on the portal\\.",
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    self.db.update_credential_status(cred_id, "results_ready")
                    return "results_ready"
                else:
                    self.db.update_credential_status(cred_id, "results_pending")
                    return "results_pending"
            else:
                self.db.update_credential_status(cred_id, "login_failed")
                return "login_failed"
        except Exception as e:
            logger.error(f"Error checking credential {cred_id} for chat {chat_id}: {e}")
            return "error"
    
    async def check_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check results immediately for all credentials in this chat."""
        chat_id = update.effective_chat.id
        creds = self.db.get_credentials(chat_id)
        
        if not creds:
            await update.message.reply_text(
                "❌ No credentials found\\. Use /add to add your credentials first\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        
        multi = len(creds) > 1
        if multi:
            await update.message.reply_text(
                f"🔍 Checking {escape_md(len(creds))} set\\(s\\) of results\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                "🔍 Checking your results\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        
        pending_count = 0
        error_count = 0
        for cred_id, username, password in creds:
            status = await self._check_single_credential(
                chat_id, cred_id, username, password,
                send_message=lambda text, **kw: update.message.reply_text(text, **kw),
                send_document=lambda **kw: update.message.reply_document(
                    **{k: v for k, v in kw.items() if k != 'caption_parse_mode'},
                    **({"parse_mode": kw["caption_parse_mode"]} if "caption_parse_mode" in kw else {}),
                ),
                label=username if multi else "",
            )
            if status == "results_pending":
                pending_count += 1
            elif status == "login_failed":
                error_count += 1
                prefix = f"\\[{escape_md(username)}\\] " if multi else ""
                await update.message.reply_text(
                    f"❌ {prefix}Login failed\\. Check credentials with /add",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            elif status == "error":
                error_count += 1
                prefix = f"\\[{escape_md(username)}\\] " if multi else ""
                await update.message.reply_text(
                    f"❌ {prefix}Error checking results\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        
        if pending_count > 0:
            await update.message.reply_text(
                f"⏳ {escape_md(pending_count)} result\\(s\\) still pending\\. I'll keep monitoring\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show monitoring status for this chat."""
        chat_id = update.effective_chat.id
        statuses = self.db.get_credential_statuses(chat_id)
        
        if not statuses:
            await update.message.reply_text(
                "❌ No credentials found\\. Use /add to add your credentials first\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        
        status_text = "📊 *Monitoring Status*\n\n"
        for cred_id, username, last_check, last_status in statuses:
            status_text += f"*{escape_md(username)}*\n"
            status_text += f"  Last Check: {escape_md(last_check or 'Never')}\n"
            status_text += f"  Status: {escape_md(last_status or 'Unknown')}\n\n"
        status_text += "I check your results every 30 minutes automatically\\."
        
        await update.message.reply_text(status_text, parse_mode=ParseMode.MARKDOWN_V2)
    
    async def check_all_users(self):
        """Periodic task to check results for all credentials."""
        logger.info("Starting periodic check for all credentials")
        all_creds = self.db.get_all_active_credentials()
        
        for cred_id, chat_id, username, password in all_creds:
            async def send_message(text, _cid=chat_id, **kwargs):
                await self.application.bot.send_message(chat_id=_cid, text=text, **kwargs)
            
            async def send_document(_cid=chat_id, **kwargs):
                caption_pm = kwargs.pop('caption_parse_mode', None)
                if caption_pm:
                    kwargs['parse_mode'] = caption_pm
                await self.application.bot.send_document(chat_id=_cid, **kwargs)
            
            status = await self._check_single_credential(
                chat_id, cred_id, username, password,
                send_message=send_message,
                send_document=send_document,
                label=username,
            )
            if status == "login_failed":
                await self.application.bot.send_message(
                    chat_id=chat_id,
                    text=f"❌ \\[{escape_md(username)}\\] *Login Failed*\n\n"
                         "I couldn't log into this account\\. Check credentials with /add",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            elif status == "results_pending":
                logger.info(f"Credential {cred_id} (chat {chat_id}) - results still pending")
        
        logger.info("Completed periodic check for all credentials")
    
    def start_scheduler(self):
        """Start the periodic scheduler."""
        self.scheduler.add_job(
            self.check_all_users,
            'interval',
            minutes=30,
            id='check_results'
        )
        self.scheduler.start()
        logger.info("Scheduler started - checking every 30 minutes")
    
    async def run(self):
        """Start the bot."""
        logger.info("Starting Lab Results Monitor Bot")
        
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Run initial check for all credentials
        await self.check_all_users()
        
        # Start scheduler for future checks
        self.start_scheduler()
        
        logger.info("Bot is running...")
        
        stop_event = asyncio.Event()
        loop = asyncio.get_running_loop()
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, stop_event.set)

        try:
            await stop_event.wait()
        except asyncio.CancelledError:
            pass
        
        logger.info("Shutting down...")
        await self.application.updater.stop()
        await self.application.stop()
        await self.application.shutdown()
        self.scheduler.shutdown()
        logger.info("Shutdown complete.")


async def main():
    """Main function to run the bot."""
    token = os.getenv('TELEGRAM_BOT_TOKEN')
    
    if not token:
        print("Error: TELEGRAM_BOT_TOKEN environment variable must be set")
        print("Get a token from @BotFather on Telegram")
        return
    
    bot = LabBot(token)
    await bot.run()


if __name__ == "__main__":
    import asyncio
    try:
        asyncio.run(main())
    except KeyboardInterrupt:
        pass
