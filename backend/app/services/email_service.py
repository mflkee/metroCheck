"""Email service for sending reports."""

import os
import smtplib
import zipfile
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from typing import Optional

from app.core.config import settings


class EmailService:
    """Service for sending email notifications and reports."""

    def __init__(self) -> None:
        self.smtp_host = getattr(settings, 'SMTP_HOST', 'mail.mkair-it.ru')
        self.smtp_port = getattr(settings, 'SMTP_PORT', 465)
        self.smtp_user = getattr(settings, 'SMTP_USER', 'robot@mkair-it.ru')
        self.smtp_pass = getattr(settings, 'SMTP_PASS', '')
        self.from_email = getattr(settings, 'FROM_EMAIL', 'no-reply@mkair-it.ru')
        self.from_name = getattr(settings, 'FROM_NAME', 'metroCheck Robot')
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
        report_path: Optional[str] = None,
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
    <p>Отчет во вложении (ZIP архив).</p>
    <hr>
    <p style="color: #666; font-size: 12px;">
        metroChek Automated Protocol Control System<br>
        Сервер: metroCheck-server (100.89.59.195)
    </p>
</body>
</html>"""

        # Create ZIP attachment if report exists
        zip_path = None
        if report_path and os.path.exists(report_path):
            zip_path = report_path.replace('.xlsx', '.zip')
            try:
                with zipfile.ZipFile(zip_path, 'w', zipfile.ZIP_DEFLATED) as zf:
                    zf.write(report_path, os.path.basename(report_path))
            except Exception as e:
                print(f"[Email] Failed to create ZIP: {e}")
                zip_path = None

        try:
            for to_email in to_emails:
                msg = MIMEMultipart()
                msg['Subject'] = subject
                msg['From'] = f"{self.from_name} <{self.from_email}>"
                msg['To'] = to_email
                msg.attach(MIMEText(body, 'html', 'utf-8'))
                
                # Attach ZIP file
                if zip_path and os.path.exists(zip_path):
                    with open(zip_path, 'rb') as f:
                        attachment = MIMEBase('application', 'zip')
                        attachment.set_payload(f.read())
                        encoders.encode_base64(attachment)
                        attachment.add_header(
                            'Content-Disposition',
                            f'attachment; filename="{os.path.basename(zip_path)}"'
                        )
                        msg.attach(attachment)
                
                self._send_smtp(msg)
            
            # Cleanup temp ZIP
            if zip_path and os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except Exception:
                    pass
            
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
                msg['From'] = f"{self.from_name} <{self.from_email}>"
                msg['To'] = to_email
                msg.attach(MIMEText(message, 'plain', 'utf-8'))
                self._send_smtp(msg)
            
            return True
        except Exception as e:
            print(f"[Email] Alert failed: {e}")
            return False

    async def send_token_expired_alert(
        self,
        recipients: list[str],
        *,
        year: int,
        month: int,
        total_protocols: int,
        processed_protocols: int,
        queue_months: list[tuple[int, int]],
    ) -> bool:
        """Send alert when ARSHIN LK token expires and check cannot continue."""
        if not recipients:
            print("[Email] No recipients configured, skipping token alert")
            return False

        if not self.smtp_pass:
            print("[Email] SMTP not configured, skipping token alert")
            return False

        month_name = self._month_name(month)
        queue_text = "\n".join(
            f"  - {self._month_name(m):02d}.{y}" for y, m in queue_months
        ) if queue_months else "  (очередь пуста)"

        subject = f"Требуется обновление токена АРШИН — проверка остановлена на {month_name}.{year}"
        body = f"""Здравствуйте.

Проверка протоколов в metroChek остановлена из-за истечения срока действия токена личного кабинета ФГИС "Аршин".

Текущий статус:
  - Проверка остановлена на: {month_name} {year} года
  - Протоколов обработано: {processed_protocols} из {total_protocols}

В очереди на проверку следующие месяцы:
{queue_text}

Для продолжения работы необходимо обновить токен АРШИН:
  1. Зайти в личный кабинет ФГИС "Аршин" через браузер
  2. Расширение Chrome автоматически передаст токен агенту
  3. После синхронизации проверка продолжится автоматически

--
metroCheck Robot
"""

        return await self.send_alert(subject, body, recipient_email=",".join(recipients))

    @staticmethod
    def _month_name(month: int) -> str:
        names = {
            1: "Январь", 2: "Февраль", 3: "Март", 4: "Апрель",
            5: "Май", 6: "Июнь", 7: "Июль", 8: "Август",
            9: "Сентябрь", 10: "Октябрь", 11: "Ноябрь", 12: "Декабрь",
        }
        return names.get(month, str(month))
