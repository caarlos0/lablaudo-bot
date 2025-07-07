#!/usr/bin/env python3
"""Telegram bot for lab results monitoring."""

import os
import logging
from datetime import datetime
from typing import Optional

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
        self.application.add_handler(CommandHandler("check", self.check_now))
        self.application.add_handler(CommandHandler("status", self.status))
        
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
/add - Add your lab credentials
/remove - Remove your credentials
/check - Check results now
/status - Show your current status
/help - Show this help message

Use /add to get started!
        """
        await update.message.reply_text(welcome_text, parse_mode='Markdown')
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = """
**Available Commands:**

/add - Add your lab portal credentials
/remove - Remove your stored credentials
/check - Check your results immediately
/status - Show your monitoring status
/help - Show this help message

**How it works:**
1. Use /add to store your lab portal credentials
2. I'll check your results every 30 minutes
3. You'll get notified when all results are ready (green status)

**Privacy:** Your credentials are stored securely and only used to check your results.
        """
        await update.message.reply_text(help_text, parse_mode='Markdown')
    
    async def add_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Start the process of adding credentials."""
        await update.message.reply_text(
            "Please send your credentials in this format:\n"
            "`username password`\n\n"
            "Example: `12345678 ABC123DEF`",
            parse_mode='Markdown'
        )
        # Store state for this user
        context.user_data['waiting_for_credentials'] = True
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages (credentials input)."""
        if context.user_data.get('waiting_for_credentials'):
            try:
                parts = update.message.text.strip().split()
                if len(parts) != 2:
                    await update.message.reply_text(
                        "Please send your credentials in this format:\n"
                        "`username password`"
                    )
                    return
                
                username, password = parts
                telegram_id = update.effective_user.id
                
                # Test the credentials first
                await update.message.reply_text("Testing your credentials...")
                
                crawler = LabCrawler()
                if crawler.login(username, password):
                    # Save credentials
                    if self.db.add_user(telegram_id, username, password):
                        await update.message.reply_text(
                            "✅ Credentials saved successfully!\n"
                            "I'll check your results every 30 minutes and notify you when they're ready."
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
        
        if self.db.remove_user(telegram_id):
            await update.message.reply_text(
                "✅ Your credentials have been removed. "
                "You'll no longer receive notifications."
            )
        else:
            await update.message.reply_text(
                "❌ No credentials found to remove."
            )
    
    async def check_now(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Check results immediately for the user."""
        telegram_id = update.effective_user.id
        credentials = self.db.get_user(telegram_id)
        
        if not credentials:
            await update.message.reply_text(
                "❌ No credentials found. Use /add to add your credentials first."
            )
            return
        
        username, password = credentials
        await update.message.reply_text("🔍 Checking your results...")
        
        try:
            crawler = LabCrawler()
            if crawler.login(username, password):
                if crawler.check_results():
                    # Results are ready - try to get PDF
                    pdf_url = crawler.get_pdf_link()
                    if pdf_url:
                        pdf_data = crawler.download_pdf(pdf_url)
                        if pdf_data:
                            pdf_content, filename = pdf_data
                            
                            # Send PDF to user
                            await update.message.reply_document(
                                document=pdf_content,
                                filename=filename,
                                caption="🎉 **Lab Results Ready!**\n\nYour lab results are attached.",
                                parse_mode='Markdown'
                            )
                            
                            # Remove user from monitoring (results delivered)
                            self.db.remove_user(telegram_id)
                            await update.message.reply_text(
                                "✅ Results delivered! You've been removed from automatic monitoring. "
                                "Use /add again if you need to monitor new results."
                            )
                        else:
                            await update.message.reply_text(
                                "🎉 **Lab Results Ready!**\n\n"
                                "Your results are available on the portal, but I couldn't download the PDF. "
                                "Please check the portal directly.",
                                parse_mode='Markdown'
                            )
                    else:
                        await update.message.reply_text(
                            "🎉 **Lab Results Ready!**\n\n"
                            "Your results are available on the portal.",
                            parse_mode='Markdown'
                        )
                    
                    self.db.update_user_status(telegram_id, "results_ready")
                else:
                    await update.message.reply_text(
                        "⏳ Your results are not ready yet. "
                        "I'll continue monitoring and notify you when they're available."
                    )
                    self.db.update_user_status(telegram_id, "results_pending")
            else:
                await update.message.reply_text(
                    "❌ Failed to login. Please check your credentials with /add"
                )
                self.db.update_user_status(telegram_id, "login_failed")
        except Exception as e:
            logger.error(f"Error checking results for user {telegram_id}: {e}")
            await update.message.reply_text(
                "❌ Error checking results. Please try again later."
            )
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show user's monitoring status."""
        telegram_id = update.effective_user.id
        credentials = self.db.get_user(telegram_id)
        
        if not credentials:
            await update.message.reply_text(
                "❌ No credentials found. Use /add to add your credentials first."
            )
            return
        
        # Get user info from database
        with self.db.get_connection() as conn:
            cursor = conn.execute(
                "SELECT username, last_check, last_status FROM users WHERE telegram_id = ?",
                (telegram_id,)
            )
            result = cursor.fetchone()
        
        if result:
            username, last_check, last_status = result
            status_text = f"📊 **Monitoring Status**\n\n"
            status_text += f"**Username:** {username}\n"
            status_text += f"**Last Check:** {last_check or 'Never'}\n"
            status_text += f"**Status:** {last_status or 'Unknown'}\n\n"
            status_text += "I check your results every 30 minutes automatically."
        else:
            status_text = "❌ No status information available."
        
        await update.message.reply_text(status_text, parse_mode='Markdown')
    
    async def check_all_users(self):
        """Periodic task to check results for all users."""
        logger.info("Starting periodic check for all users")
        users = self.db.get_all_active_users()
        
        for telegram_id, username, password in users:
            try:
                crawler = LabCrawler()
                if crawler.login(username, password):
                    if crawler.check_results():
                        # Results are ready - try to get PDF
                        pdf_url = crawler.get_pdf_link()
                        if pdf_url:
                            pdf_data = crawler.download_pdf(pdf_url)
                            if pdf_data:
                                pdf_content, filename = pdf_data
                                
                                # Send PDF to user
                                await self.application.bot.send_document(
                                    chat_id=telegram_id,
                                    document=pdf_content,
                                    filename=filename,
                                    caption="🎉 **Lab Results Ready!**\n\nYour lab results are attached.",
                                    parse_mode='Markdown'
                                )
                                
                                # Remove user from monitoring (results delivered)
                                self.db.remove_user(telegram_id)
                                logger.info(f"Delivered PDF to user {telegram_id} and removed from monitoring")
                            else:
                                # PDF download failed, send text notification
                                await self.application.bot.send_message(
                                    chat_id=telegram_id,
                                    text="🎉 **Lab Results Ready!**\n\n"
                                         "Your results are available on the portal, but I couldn't download the PDF. "
                                         "Please check the portal directly.",
                                    parse_mode='Markdown'
                                )
                                logger.warning(f"PDF download failed for user {telegram_id}")
                        else:
                            # No PDF link found, send text notification
                            await self.application.bot.send_message(
                                chat_id=telegram_id,
                                text="🎉 **Lab Results Ready!**\n\n"
                                     "Your results are available on the portal.",
                                parse_mode='Markdown'
                            )
                            logger.info(f"No PDF link found for user {telegram_id}")
                        
                        self.db.update_user_status(telegram_id, "results_ready")
                        logger.info(f"Notified user {telegram_id} - results ready")
                    else:
                        self.db.update_user_status(telegram_id, "results_pending")
                        logger.info(f"User {telegram_id} - results still pending")
                else:
                    logger.warning(f"Login failed for user {telegram_id}")
                    self.db.update_user_status(telegram_id, "login_failed")
                    # Send notification about login failure
                    await self.application.bot.send_message(
                        chat_id=telegram_id,
                        text="❌ **Login Failed**\n\n"
                             "I couldn't log into your account. Please check your credentials with /add",
                        parse_mode='Markdown'
                    )
            except Exception as e:
                logger.error(f"Error checking user {telegram_id}: {e}")
        
        logger.info("Completed periodic check for all users")
    
    def start_scheduler(self):
        """Start the periodic scheduler."""
        # Check every 30 minutes
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
        
        # Start bot first
        await self.application.initialize()
        await self.application.start()
        await self.application.updater.start_polling()
        
        # Run initial check for all users (same as periodic check)
        await self.check_all_users()
        
        # Start scheduler for future checks
        self.start_scheduler()
        
        logger.info("Bot is running...")
        
        try:
            # Keep running - use a simple infinite loop instead of idle()
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