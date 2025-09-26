# services/email_service.py
from __future__ import annotations
import os
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.header import Header
from email.utils import formataddr
from flask import current_app
from email_config import GMAIL_CONFIG

def _base_url() -> str:
    return os.getenv("PUBLIC_BASE_URL", "http://127.0.0.1:5000").rstrip("/")

def send_email_with_secure_link(employee_name: str, email: str, download_link) -> bool:
    """
    Envoie un mail contenant l’URL sécurisée /download/<token>.
    """
    try:
        smtp_server = GMAIL_CONFIG["smtp_server"]
        smtp_port = GMAIL_CONFIG["smtp_port"]
        smtp_username = GMAIL_CONFIG["username"]
        smtp_password = GMAIL_CONFIG["password"]

        # URL de téléchargement
        download_url = f"{_base_url()}/download/{download_link.token}"

        # Sujet + en-têtes encodés en UTF-8
        subject = f"Votre fiche de paie – {employee_name}"
        msg = MIMEMultipart()
        msg["Subject"] = str(Header(subject, "utf-8"))
        # Nom d’expéditeur lisible avec accents si besoin
        msg["From"] = formataddr((str(Header("PayFlow", "utf-8")), smtp_username))
        msg["To"] = email

        # Corps en UTF-8 (avec emojis/accents)
        expiry_days = getattr(download_link, "expires_in_days", 30)
        body = f"""Bonjour {employee_name},

Votre fiche de paie est disponible au téléchargement sécurisé.

🔗 Lien de téléchargement : {download_url}

🔐 Pour télécharger votre fiche :
1. Cliquez sur le lien ci-dessus
2. Saisissez votre matricule d'employé
3. Téléchargez votre fiche

⏰ Ce lien expire dans {expiry_days} jours
🛡️ Votre fiche est protégée par votre matricule

Cordialement,
L'équipe RH
"""
        msg.attach(MIMEText(body, "plain", "utf-8"))

        # Envoi : utilisez send_message (gère mieux l’UTF-8 que sendmail+as_string)
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.ehlo()
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.send_message(msg)  # ✅ évite les problèmes d'encodage
        # Alternative sûre : server.sendmail(smtp_username, [email], msg.as_bytes())
        server.quit()

        current_app.logger.info(f"[mail] Lien envoyé à {email}")
        return True

    except Exception as e:
        current_app.logger.error(f"[mail] Erreur envoi: {e}")
        return False
