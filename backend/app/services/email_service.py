"""Email service for sending reports."""

import smtplib
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from typing import Optional

from app.core.config import settings


class EmailService:
    """Service for sending email notifications and reports."""

    def __init__(self) -> None:
        self.smtp_host = getattr(settings, 'SMTP_HOST', 'smtp.gmail.com')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 587)
        self.smtp_user = getattr(settings, 'SMTP_USER', '')
        self.smtp_pass = getattr(settings, 'SMTP_PASS', '')
        self.from_email = getattr(settings, 'FROM_EMAIL', 'metrocheck-reports@example.com')
        self.to_email = getattr(settings, 'REPORT_EMAIL', '')

    def _send_smtp(self, msg) -> None:
        if self.smtp_port == 465:
            with smtplib.SMTP_SSL(self.smtp_host, self.smtp_port) as server:
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)
        else:
            with smtplib.SMTP(self.smtp_host, self.smtp_port) as server:
                server.starttls()
                server.login(self.smtp_user, self.smtp_pass)
                server.send_message(msg)

    async def send_check_report(
        self,
        year: int,
        month: int,
        total_devices: int,
        errors: int,
        warnings: int,
        missing: int,
        check_run_id: int,
        report_url: Optional[str] = None,
        recipient_email: Optional[str] = None,
    ) -> bool:
        """Send email report after check completion."""
        to_emails = [e.strip() for e in (recipient_email or self.to_email).split(",") if e.strip()]
        if not to_emails or not self.smtp_user:
            print("[Email] Email not configured, skipping")
            return False

        subject = f"metroChek Отчет: Проверка протоколов {month:02d}.{year}"
        
        body = f"""<html>
<body style="font-family: Arial, sans-serif; color: #333;">
    <h2>Отчет о проверке протоколов поверки</h2>
    <p><strong>Период:</strong> {month:02d}.{year}</p>
    <p><strong>Дата проверки:</strong> {__import__('datetime').datetime.now().strftime('%d.%m.%Y %H:%M')}</p>
    <hr>
    <h3>Результаты</h3>
    <ul>
        <li>Всего поверок: <strong>{total_devices}</strong></li>
        <li style="color: #ef4444;">Ошибок: <strong>{errors}</strong></li>
        <li style="color: #f59e0b;">Предупреждений: <strong>{warnings}</strong></li>
        <li style="color: #6b7280;">Нет протоколов: <strong>{missing}</strong></li>
    </ul>
    {f'<p><a href="{report_url}" style="background: #3b82f6; color: white; padding: 10px 20px; text-decoration: none; border-radius: 5px;">Скачать полный отчет</a></p>' if report_url else ''}
    <hr>
    <p style="color: #666; font-size: 12px;">
        metroChek Automated Protocol Control System<br>
        Сервер: metroCheck-server (100.89.59.195)
    </p>
</body>
</html>"""

        try:
            msg = MIMEMultipart('alternative')
            msg['Subject'] = subject
            msg['From'] = self.from_email
            for to_email in to_emails:
                msg_copy = MIMEMultipart('alternative')
                msg_copy['Subject'] = subject
                msg_copy['From'] = self.from_email
                msg_copy['To'] = to_email
                msg_copy.attach(MIMEText(body, 'html', 'utf-8'))
                self._send_smtp(msg_copy)
            
            print(f"[Email] Report sent to {', '.join(to_emails)}")
            return True
        except Exception as e:
            print(f"[Email] Failed to send: {e}")
            return False

    async def send_alert(self, subject: str, message: str, recipient_email: Optional[str] = None) -> bool:
        """Send alert email."""
        to_emails = [e.strip() for e in (recipient_email or self.to_email).split(",") if e.strip()]
        if not to_emails:
            return False

        try:
            for to_email in to_emails:
                msg = MIMEMultipart()
                msg['Subject'] = f"[metroChek ALERT] {subject}"
                msg['From'] = self.from_email
                msg['To'] = to_email
                msg.attach(MIMEText(message, 'plain', 'utf-8'))
                self._send_smtp(msg)
            
            return True
        except Exception as e:
            print(f"[Email] Alert failed: {e}")
            return False
