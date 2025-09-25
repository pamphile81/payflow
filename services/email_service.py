# services/email_service.py
from flask import current_app
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

# On suppose que email_config.py existe déjà et expose GMAIL_CONFIG
from email_config import GMAIL_CONFIG

def _build_download_url(download_link):
    """
    Construit l'URL publique à partir de la config.
    - PUBLIC_BASE_URL: http(s)://host:port (ex: http://127.0.0.1:5000, https://payflow.mondomaine.com)
    - download_link peut être soit un objet avec .token, soit déjà un token/str.
    """
    base = current_app.config.get("PUBLIC_BASE_URL") or "http://127.0.0.1:5000"
    token = getattr(download_link, "token", str(download_link))
    return f"{base}/download/{token}"

def send_email_with_secure_link(employee_name: str, email: str, download_link) -> bool:
    """
    Envoie un email contenant le lien sécurisé.
    - employee_name: Nom employé
    - email: destinataire
    - download_link: objet DownloadLink OU simple token (str)
    """
    try:
        smtp_server = GMAIL_CONFIG['smtp_server']
        smtp_port = GMAIL_CONFIG['smtp_port']
        smtp_username = GMAIL_CONFIG['username']
        smtp_password = GMAIL_CONFIG['password']

        download_url = _build_download_url(download_link)

        # Nombre de jours d’expiration (si l’objet possède l’info, sinon fallback config)
        expiry_days = getattr(download_link, "expires_in_days",
                              current_app.config.get("DOWNLOAD_LINK_EXPIRY_DAYS", 30))

        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email
        msg['Subject'] = f"Votre fiche de paie - {employee_name}"

        body = f"""Bonjour {employee_name},

Votre fiche de paie est disponible au téléchargement sécurisé.

🔗 Lien de téléchargement : {download_url}

🔐 Pour télécharger votre fiche :
1. Cliquez sur le lien ci-dessus
2. Saisissez votre matricule d'employé
3. Téléchargez votre fiche de paie

⏰ Ce lien expire dans {expiry_days} jours
🛡️ Votre fiche est protégée par votre matricule

Cordialement,
L'équipe RH
"""
        msg.attach(MIMEText(body, 'plain'))

        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        server.sendmail(smtp_username, email, msg.as_string())
        server.quit()

        current_app.logger.info(f"[mail] Lien sécurisé envoyé à {employee_name} <{email}>")
        return True

    except Exception as e:
        current_app.logger.error(f"[mail] Erreur envoi email: {e}")
        return False
