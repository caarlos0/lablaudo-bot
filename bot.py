#!/usr/bin/env python3
"""Telegram bot for lab results monitoring."""

import os
import re
import logging

from telegram import Update
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from database import Database
from crawler import LabCrawler


# Configure logging
logging.basicConfig(
    format='%(asctime)s - %(name)s - %(levelname)s - %(message)s',
    level=logging.INFO
)
logger = logging.getLogger(__name__)


class LabBot:
    """Telegram bot for monitoring lab results."""
    
    def __init__(self, token: str):
        self.token = token
        self.db = Database()
        self.scheduler = AsyncIOScheduler()
        self.application = Application.builder().token(token).build()
        self.setup_handlers()
    
    def setup_handlers(self):
        """Setup bot command handlers."""
        self.application.add_handler(CommandHandler("start", self.start))
        self.application.add_handler(CommandHandler("help", self.help_command))
        self.application.add_handler(CommandHandler("add", self.add_credentials))
        self.application.add_handler(CommandHandler("remove", self.remove_credentials))
        self.application.add_handler(CommandHandler("remove_all", self.remove_all_credentials))
        self.application.add_handler(CommandHandler("check", self.check_now))
        self.application.add_handler(CommandHandler("status", self.status))
        
        # Handle /remove_<id> commands
        self.application.add_handler(
            MessageHandler(filters.Regex(r'^/remove_\d+'), self.remove_single_credential)
        )
        
        # Handle text messages for credential input
        self.application.add_handler(
            MessageHandler(filters.TEXT & ~filters.COMMAND, self.handle_message)
        )
    
    async def start(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send welcome message."""
        welcome_text = """
🧪 **Lab Results Monitor Bot**

I can monitor your lab results at lablaudo.com.br and notify you when they're ready!

**Commands:**
/add - Add lab credentials
/remove - Remove credentials
/check - Check results now
/status - Show your current status
/help - Show this help message

Use /add to get started! You can add multiple credentials to monitor several results at once.
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = """
**Available Commands:**

/add - Add lab portal credentials (can add multiple)
/remove - Remove stored credentials
/check - Check all your results immediately
/status - Show your monitoring status
/help - Show this help message

**How it works:**
1. Use /add to store your lab portal credentials
2. You can add multiple credentials for different results
3. I'll check all your results every 30 minutes
4. You'll get notified when results are ready (green status)
5. Each credential is removed automatically after its PDF is delivered

**Privacy:** Your credentials are stored securely and only used to check your results.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def add_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the process of adding credentials."""
        await update.message.reply_text(
            "Please send your credentials in this format:\n"
            "`username password`\n\n"
            "Example: `12345678 ABC123DEF`\n\n"
            "You can add multiple credentials by sending /add again.",
            parse_mode='Markdown'
        )
        context.user_data['waiting_for_credentials'] = True
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (credentials input)."""
        if context.user_data.get('waiting_for_credentials'):
            try:
                parts = update.message.text.strip().split()
                if len(parts) != 2:
                    await update.message.reply_text(
                        "Please send your credentials in this format:\n"
                        "`username password`",
                        parse_mode='Markdown'
                    )
                    return
                
                username, password = parts
                telegram_id = update.effective_user.id
                
                await update.message.reply_text("Testing your credentials...")
                
                crawler = LabCrawler()
                if crawler.login(username, password):
                    if self.db.add_credential(telegram_id, username, password):
                        creds = self.db.get_credentials(telegram_id)
                        count = len(creds)
                        await update.message.reply_text(
                            f"✅ Credentials saved! You now have {count} credential(s) being monitored.\n"
                            "I'll check your results every 30 minutes and notify you when they're ready.\n\n"
                            "Use /add again to add more, or /status to see all."
                        )
                    else:
                        await update.message.reply_text(
                            "❌ Failed to save credentials. Please try again."
                        )
                else:
                    await update.message.reply_text(
                        "❌ Login failed. Please check your credentials and try again."
                    )
                
                context.user_data['waiting_for_credentials'] = False
                
            except Exception as e:
                logger.error(f"Error processing credentials: {e}")
                await update.message.reply_text(
                    "❌ Error processing credentials. Please try again."
                )
                context.user_data['waiting_for_credentials'] = False
        else:
            await update.message.reply_text(
                "Use /help to see available commands."
            )
    
    async def remove_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove user credentials."""
        telegram_id = update.effective_user.id
        creds = self.db.get_credentials(telegram_id)
        
        if not creds:
            await update.message.reply_text(
                "❌ No credentials found to remove."
            )
            return
        
        if len(creds) == 1:
            cred_id, username, _ = creds[0]
            if self.db.remove_credential(telegram_id, cred_id):
                await update.message.reply_text(
                    f"✅ Credentials for `{username}` removed.",
                    parse_mode='Markdown'
                )
            else:
                await update.message.reply_text("❌ Failed to remove credentials.")
            return
        
        # Multiple credentials - ask which to remove
        msg = "Which credentials do you want to remove?\n\n"
        for cred_id, username, _ in creds:
            msg += f"  /remove\\_{cred_id} — `{username}`\n"
        msg += "\n/remove\\_all — Remove all"
        await update.message.reply_text(msg, parse_mode='Markdown')
    
    async def remove_single_credential(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove a single credential by id from /remove_<id> command."""
        telegram_id = update.effective_user.id
        text = update.message.text.strip()
        match = re.search(r'/remove_(\d+)', text)
        if not match:
            await update.message.reply_text("❌ Invalid command format.")
            return
        
        cred_id = int(match.group(1))
        cred = self.db.get_credential_by_id(cred_id)
        if not cred or cred[0] != telegram_id:
            await update.message.reply_text("❌ Credential not found.")
            return
        
        _, username, _ = cred
        if self.db.remove_credential(telegram_id, cred_id):
            await update.message.reply_text(
                f"✅ Credentials for `{username}` removed.",
                parse_mode='Markdown'
            )
        else:
            await update.message.reply_text("❌ Failed to remove credentials.")
    
    async def remove_all_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove all credentials for a user."""
        telegram_id = update.effective_user.id
        if self.db.remove_all_credentials(telegram_id):
            await update.message.reply_text(
                "✅ All credentials removed. You'll no longer receive notifications."
            )
        else:
            await update.message.reply_text("❌ No credentials found to remove.")
    
    async def _check_single_credential(
        self,
        telegram_id: int,
        cred_id: int,
        username: str,
        password: str,
        send_message,
        send_document,
        label: str = "",
    ):
        """Check results for a single credential. Returns status string."""
        prefix = f"[`{username}`] " if label else ""
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
                                caption=f"🎉 {prefix}**Lab Results Ready!**\n\nYour lab results are attached.",
                                parse_mode='Markdown'
                            )
                            self.db.remove_credential(telegram_id, cred_id)
                            logger.info(f"Delivered PDF for credential {cred_id} (user {telegram_id}) and removed")
                            return "results_delivered"
                        else:
                            await send_message(
                                f"🎉 {prefix}**Lab Results Ready!**\n\n"
                                "Results available on the portal, but I couldn't download the PDF.",
                                parse_mode='Markdown'
                            )
                    else:
                        await send_message(
                            f"🎉 {prefix}**Lab Results Ready!**\n\n"
                            "Your results are available on the portal.",
                            parse_mode='Markdown'
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
            logger.error(f"Error checking credential {cred_id} for user {telegram_id}: {e}")
            return "error"
    
    async def check_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check results immediately for all user credentials."""
        telegram_id = update.effective_user.id
        creds = self.db.get_credentials(telegram_id)
        
        if not creds:
            await update.message.reply_text(
                "❌ No credentials found. Use /add to add your credentials first."
            )
            return
        
        multi = len(creds) > 1
        if multi:
            await update.message.reply_text(f"🔍 Checking {len(creds)} set(s) of results...")
        else:
            await update.message.reply_text("🔍 Checking your results...")
        
        pending_count = 0
        error_count = 0
        for cred_id, username, password in creds:
            status = await self._check_single_credential(
                telegram_id, cred_id, username, password,
                send_message=lambda text, **kw: update.message.reply_text(text, **kw),
                send_document=lambda **kw: update.message.reply_document(**kw),
                label=username if multi else "",
            )
            if status == "results_pending":
                pending_count += 1
            elif status == "login_failed":
                error_count += 1
                await update.message.reply_text(
                    f"❌ {'[`' + username + '`] ' if multi else ''}Login failed. Check credentials with /add",
                    parse_mode='Markdown'
                )
            elif status == "error":
                error_count += 1
                await update.message.reply_text(
                    f"❌ {'[`' + username + '`] ' if multi else ''}Error checking results."
                )
        
        if pending_count > 0:
            await update.message.reply_text(
                f"⏳ {pending_count} result(s) still pending. I'll keep monitoring."
            )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's monitoring status."""
        telegram_id = update.effective_user.id
        statuses = self.db.get_credential_statuses(telegram_id)
        
        if not statuses:
            await update.message.reply_text(
                "❌ No credentials found. Use /add to add your credentials first."
            )
            return
        
        status_text = "📊 Monitoring Status\n\n"
        for cred_id, username, last_check, last_status in statuses:
            status_text += f"{username}\n"
            status_text += f"  Last Check: {last_check or 'Never'}\n"
            status_text += f"  Status: {last_status or 'Unknown'}\n\n"
        status_text += "I check your results every 30 minutes automatically."
        
        await update.message.reply_text(status_text)
    
    async def check_all_users(self):
        """Periodic task to check results for all credentials."""
        logger.info("Starting periodic check for all credentials")
        all_creds = self.db.get_all_active_credentials()
        
        for cred_id, telegram_id, username, password in all_creds:
            async def send_message(text, _tid=telegram_id, **kwargs):
                await self.application.bot.send_message(chat_id=_tid, text=text, **kwargs)
            
            async def send_document(_tid=telegram_id, **kwargs):
                await self.application.bot.send_document(chat_id=_tid, **kwargs)
            
            status = await self._check_single_credential(
                telegram_id, cred_id, username, password,
                send_message=send_message,
                send_document=send_document,
                label=username,
            )
            if status == "login_failed":
                await self.application.bot.send_message(
                    chat_id=telegram_id,
                    text=f"❌ [`{username}`] **Login Failed**\n\n"
                         "I couldn't log into this account. Check credentials with /add",
                    parse_mode='Markdown'
                )
            elif status == "results_pending":
                logger.info(f"Credential {cred_id} (user {telegram_id}) - results still pending")
        
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
        
        try:
            import asyncio
            while True:
                await asyncio.sleep(1)
        except KeyboardInterrupt:
            logger.info("Received interrupt signal, shutting down...")
        finally:
            await self.application.updater.stop()
            await self.application.stop()
            await self.application.shutdown()
            self.scheduler.shutdown()


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
    asyncio.run(main())
