#!/usr/bin/env python3
"""Telegram bot for lab results monitoring."""

import asyncio
import os
import re
import signal
import logging
from datetime import datetime

from telegram import Update
from telegram.constants import ParseMode
from telegram.ext import Application, CommandHandler, MessageHandler, filters, ContextTypes
from apscheduler.schedulers.asyncio import AsyncIOScheduler

from lablaudo.database import Database
from lablaudo.crawler import LabCrawler, ExamDetail


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


def _exams_to_dicts(exams: list[ExamDetail]) -> list[dict]:
    """Convert ExamDetail list to dicts for DB storage."""
    return [
        {
            "name": e.name,
            "status": e.status,
            "expected_date": e.expected_date.strftime('%d/%m/%Y %H:%M') if e.expected_date else None,
        }
        for e in exams
    ]


_READY_KEYWORDS = {"disponível", "disponivel", "pronto", "liberado", "concluído", "concluido"}


def _is_exam_ready(status: str) -> bool:
    """Check if an exam status indicates it's ready."""
    return status.strip().lower() in _READY_KEYWORDS


def _format_exams_md(exams_rows: list[tuple], now: datetime | None = None, max_shown: int = 3) -> str:
    """Format exam rows (name, status, expected_date) as MarkdownV2 summary."""
    if not exams_rows:
        return ""
    if now is None:
        now = datetime.now()

    ready: list[tuple] = []
    pending: list[tuple] = []
    overdue: list[tuple] = []

    for row in exams_rows:
        name, status, expected_date = row
        if _is_exam_ready(status):
            ready.append(row)
        else:
            is_overdue = False
            if expected_date:
                try:
                    dt = datetime.strptime(expected_date, '%d/%m/%Y %H:%M')
                    is_overdue = dt < now
                except ValueError:
                    pass
            if is_overdue:
                overdue.append(row)
            else:
                pending.append(row)

    lines: list[str] = []

    if ready:
        lines.append(f"✅ {escape_md(len(ready))} item\\(ns\\) pronto\\(s\\)")

    if pending:
        dates: list[datetime] = []
        for _, _, ed in pending:
            if ed:
                try:
                    dates.append(datetime.strptime(ed, '%d/%m/%Y %H:%M'))
                except ValueError:
                    pass
        line = f"⏳ {escape_md(len(pending))} item\\(ns\\) pendente\\(s\\)"
        if dates:
            min_d = min(dates).strftime('%d/%m/%Y')
            max_d = max(dates).strftime('%d/%m/%Y')
            if min_d == max_d:
                line += f", previsão: {escape_md(min_d)}"
            else:
                line += f", previsão entre {escape_md(min_d)} e {escape_md(max_d)}"
        lines.append(line)

    if overdue:
        dates_o: list[datetime] = []
        for _, _, ed in overdue:
            if ed:
                try:
                    dates_o.append(datetime.strptime(ed, '%d/%m/%Y %H:%M'))
                except ValueError:
                    pass
        line = f"⚠️ {escape_md(len(overdue))} item\\(ns\\) atrasado\\(s\\)"
        if dates_o:
            max_d = max(dates_o).strftime('%d/%m/%Y')
            line += f" \\(previsão era {escape_md(max_d)}\\)"
        lines.append(line)

    return "\n".join(lines)


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
            "🧪 *Monitor de Resultados de Laboratório*\n\n"
            "Eu monitoro seus resultados no lablaudo\\.com\\.br "
            "e aviso quando estiverem prontos\\!\n\n"
            "*Comandos:*\n"
            "/add \\- Adicionar credenciais\n"
            "/remove \\- Remover credenciais por usuário\n"
            "/check \\- Verificar resultados agora\n"
            "/status \\- Ver status atual\n"
            "/help \\- Mostrar esta mensagem\n\n"
            "Use /add para começar\\! Você pode adicionar múltiplas "
            "credenciais para monitorar vários resultados\\."
        )
        await update.message.reply_text(welcome_text, parse_mode=ParseMode.MARKDOWN_V2)
    
    async def help_command(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Send help message."""
        help_text = (
            "*Comandos disponíveis:*\n\n"
            "/add \\- Adicionar credenciais do portal \\(aceita múltiplas\\)\n"
            "/remove \\- Remover credenciais por usuário\n"
            "/check \\- Verificar todos os resultados agora\n"
            "/status \\- Ver status do monitoramento\n"
            "/help \\- Mostrar esta mensagem\n\n"
            "*Como funciona:*\n"
            "1\\. Use /add para salvar suas credenciais do portal\n"
            "2\\. Você pode adicionar múltiplas credenciais\n"
            "3\\. Eu verifico seus resultados a cada hora\n"
            "4\\. Você será notificado quando os resultados estiverem prontos\n"
            "5\\. Cada credencial é removida automaticamente após o envio do PDF\n\n"
            "_Privacidade: suas credenciais são armazenadas de forma segura e usadas apenas para verificar seus resultados\\._"
        )
        await update.message.reply_text(help_text, parse_mode=ParseMode.MARKDOWN_V2)
    
    async def _save_credentials(self, update: Update, username: str, password: str):
        """Validate and save credentials."""
        chat_id = update.effective_chat.id
        await update.message.reply_text(
            "🔍 Entrando e buscando detalhes dos exames\\.\\.\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
        
        crawler = LabCrawler()
        if crawler.login(username, password):
            cred_id = self.db.add_credential(chat_id, username, password)
            if cred_id:
                exams = crawler.get_exam_details()
                self.db.save_exams(cred_id, _exams_to_dicts(exams))

                creds = self.db.get_credentials(chat_id)
                count = len(creds)

                exam_rows = self.db.get_exams(cred_id)
                exams_text = _format_exams_md(exam_rows)

                msg = (
                    f"✅ Credenciais salvas\\! Você tem {escape_md(count)} credencial\\(is\\) sendo monitorada\\(s\\)\\.\n\n"
                )
                if exams_text:
                    msg += f"*Exames encontrados:*\n{exams_text}\n\n"
                msg += (
                    "Vou verificar seus resultados a cada hora e avisar quando estiverem prontos\\.\n"
                    "Use /add novamente para adicionar mais, ou /status para ver todos\\."
                )
                await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
            else:
                await update.message.reply_text(
                    "❌ Falha ao salvar credenciais\\. Tente novamente\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        else:
            await update.message.reply_text(
                "❌ Login falhou\\. Verifique suas credenciais e tente novamente\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
    
    async def add_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Add credentials. Usage: /add username password"""
        if context.args and len(context.args) == 2:
            await self._save_credentials(update, context.args[0], context.args[1])
            return
        
        await update.message.reply_text(
            "Uso: `/add usuario senha`\n\n"
            "Exemplo: `/add 12345678 ABC123DEF`",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    
    async def handle_message(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Handle text messages."""
        await update.message.reply_text(
            "Use /help para ver os comandos disponíveis\\.",
            parse_mode=ParseMode.MARKDOWN_V2,
        )
    
    async def remove_credentials(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Remove credentials by username. Usage: /remove username"""
        chat_id = update.effective_chat.id

        if not context.args or len(context.args) != 1:
            creds = self.db.get_credentials(chat_id)
            if not creds:
                await update.message.reply_text(
                    "❌ Nenhuma credencial encontrada para remover\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
                return
            msg = "Uso: `/remove usuario`\n\nSuas credenciais:\n"
            for _, username, _ in creds:
                msg += f"  `{escape_md(username)}`\n"
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
            return

        username = context.args[0]
        if self.db.remove_credential_by_username(chat_id, username):
            await update.message.reply_text(
                f"✅ Credenciais de {escape_md(username)} removidas\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                "❌ Credencial não encontrada\\.",
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
        manual: bool = False,
    ):
        """Check results for a single credential. Returns status string."""
        prefix = f"\\[{escape_md(username)}\\] " if label else ""
        try:
            crawler = LabCrawler()
            if crawler.login(username, password):
                exams = crawler.get_exam_details()
                self.db.save_exams(cred_id, _exams_to_dicts(exams))

                if crawler.check_results():
                    pdf_url = crawler.get_pdf_link()
                    if pdf_url:
                        pdf_data = crawler.download_pdf(pdf_url)
                        if pdf_data:
                            pdf_content, filename = pdf_data
                            await send_document(
                                document=pdf_content,
                                filename=filename,
                                caption=f"🎉 {prefix}*Resultados Prontos\\!*\n\nSeus resultados estão anexados\\.",
                                caption_parse_mode=ParseMode.MARKDOWN_V2,
                            )
                            self.db.remove_credential(chat_id, cred_id)
                            logger.info(f"Delivered PDF for credential {cred_id} (chat {chat_id}) and removed")
                            return "results_delivered"
                        else:
                            await send_message(
                                f"🎉 {prefix}*Resultados Prontos\\!*\n\n"
                                "Resultados disponíveis no portal, mas não consegui baixar o PDF\\.",
                                parse_mode=ParseMode.MARKDOWN_V2,
                            )
                    else:
                        await send_message(
                            f"🎉 {prefix}*Resultados Prontos\\!*\n\n"
                            "Seus resultados estão disponíveis no portal\\.",
                            parse_mode=ParseMode.MARKDOWN_V2,
                        )
                    self.db.update_credential_status(cred_id, "results_ready")
                    return "results_ready"
                else:
                    now = datetime.now()
                    overdue = [e for e in exams if e.expected_date and e.expected_date < now]
                    ready_exams = [e for e in exams if _is_exam_ready(e.status)]
                    prev_status = self.db.get_credential_status(cred_id)
                    exam_rows = self.db.get_exams(cred_id)
                    summary = _format_exams_md(exam_rows, now)

                    if manual and ready_exams:
                        pdf_url = crawler.get_pdf_link()
                        if pdf_url:
                            pdf_data = crawler.download_pdf(pdf_url)
                            if pdf_data:
                                pdf_content, filename = pdf_data
                                await send_document(
                                    document=pdf_content,
                                    filename=filename,
                                    caption=(
                                        f"📋 {prefix}*Relatório parcial*\n\n"
                                        f"{summary}"
                                    ),
                                    caption_parse_mode=ParseMode.MARKDOWN_V2,
                                )
                                new_status = "results_overdue" if overdue else "results_pending"
                                self.db.update_credential_status(cred_id, new_status)
                                return new_status

                    if overdue:
                        if manual or prev_status != "results_overdue":
                            msg = f"📋 {prefix}*Status dos exames:*\n\n{summary}\n\n"
                            msg += "Considere entrar em contato com o laboratório\\."
                            await send_message(msg, parse_mode=ParseMode.MARKDOWN_V2)
                        self.db.update_credential_status(cred_id, "results_overdue")
                        return "results_overdue"

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
                "❌ Nenhuma credencial encontrada\\. Use /add para adicionar suas credenciais\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        
        multi = len(creds) > 1
        if multi:
            await update.message.reply_text(
                f"🔍 Verificando {escape_md(len(creds))} conjunto\\(s\\) de resultados\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        else:
            await update.message.reply_text(
                "🔍 Verificando seus resultados\\.\\.\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
        
        pending_creds: list[tuple[int, str]] = []
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
                manual=True,
            )
            if status == "results_pending":
                pending_creds.append((cred_id, username))
            elif status == "login_failed":
                error_count += 1
                prefix = f"\\[{escape_md(username)}\\] " if multi else ""
                await update.message.reply_text(
                    f"❌ {prefix}Falha no login\\. Verifique as credenciais com /add",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            elif status == "error":
                error_count += 1
                prefix = f"\\[{escape_md(username)}\\] " if multi else ""
                await update.message.reply_text(
                    f"❌ {prefix}Erro ao verificar resultados\\.",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
        
        now = datetime.now()
        for cred_id, username in pending_creds:
            prefix = f"\\[{escape_md(username)}\\] " if multi else ""
            exam_rows = self.db.get_exams(cred_id)
            summary = _format_exams_md(exam_rows, now)
            msg = f"📋 {prefix}*Status dos exames:*\n\n{summary}" if summary else f"⏳ {prefix}Resultados pendentes\\."
            msg += "\n\nContinuarei monitorando\\."
            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    
    async def status(self, update: Update, context: ContextTypes.DEFAULT_TYPE):
        """Show monitoring status for this chat."""
        chat_id = update.effective_chat.id
        statuses = self.db.get_credential_statuses(chat_id)
        
        if not statuses:
            await update.message.reply_text(
                "❌ Nenhuma credencial encontrada\\. Use /add para adicionar suas credenciais\\.",
                parse_mode=ParseMode.MARKDOWN_V2,
            )
            return
        
        _STATUS_PT = {
            "results_pending": "Pendente",
            "results_ready": "Pronto",
            "results_delivered": "Entregue",
            "results_overdue": "Atrasado",
            "login_failed": "Falha no login",
        }

        now = datetime.now()
        for cred_id, username, last_check, last_status in statuses:
            status_label = _STATUS_PT.get(last_status, last_status or "Desconhecido")
            msg = f"📊 *{escape_md(username)}*\n"
            msg += f"  Status: {escape_md(status_label)}\n"
            if last_check:
                msg += f"  Última verificação: {escape_md(last_check)}\n"

            exam_rows = self.db.get_exams(cred_id)
            if exam_rows:
                msg += f"\n{_format_exams_md(exam_rows, now)}\n"

            await update.message.reply_text(msg, parse_mode=ParseMode.MARKDOWN_V2)
    
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
                    text=f"❌ \\[{escape_md(username)}\\] *Falha no Login*\n\n"
                         "Não consegui entrar nesta conta\\. Verifique as credenciais com /add",
                    parse_mode=ParseMode.MARKDOWN_V2,
                )
            elif status == "results_pending":
                logger.info(f"Credential {cred_id} (chat {chat_id}) - results still pending")
            elif status == "results_overdue":
                logger.info(f"Credential {cred_id} (chat {chat_id}) - results overdue")
        
        logger.info("Completed periodic check for all credentials")
    
    def start_scheduler(self):
        """Start the periodic scheduler."""
        self.scheduler.add_job(
            self.check_all_users,
            'interval',
            minutes=60,
            id='check_results'
        )
        self.scheduler.start()
        logger.info("Scheduler started - checking every 60 minutes")
    
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
