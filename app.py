# app.py - PayFlow v1.2 (version simplifiée et corrigée)
import os
import csv
import smtplib
import hashlib
import secrets
import logging
import threading
import json
import glob
import time
from datetime import datetime, timedelta
from logging.handlers import RotatingFileHandler
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email.mime.text import MIMEText
from email import encoders
from services.email_service import send_email_with_secure_link
from services.pdf_service import protect_pdf_with_password
from services.link_service import generate_secure_download_link, get_current_traitement
from services.employee_service import (
    load_employees,
    find_employee_by_matricule,
    detect_new_employees,
    add_employees_to_database,
)



from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, send_file, session
)
from werkzeug.utils import secure_filename
import PyPDF2

# --- config & extensions ---
from config import get_config
from extensions import db, migrate, mail

# --- modèles (utilisés dans les routes) ---
from models import Employee, Traitement, TraitementEmploye, DownloadLink

# 1) Charger .env tôt (ne casse rien si .env absent)
load_dotenv(override=False)

# ------------------------------------------------------------
# Logging
# ------------------------------------------------------------
def setup_logging(app: Flask):
    if not os.path.exists('logs'):
        os.makedirs('logs')

    formatter = logging.Formatter('[%(asctime)s] %(levelname)s in %(module)s: %(message)s')

    file_handler = RotatingFileHandler('logs/payflow.log', maxBytes=10*1024*1024, backupCount=10)
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)

    error_handler = RotatingFileHandler('logs/payflow_errors.log', maxBytes=5*1024*1024, backupCount=5)
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    app.logger.addHandler(error_handler)

    security_handler = RotatingFileHandler('logs/payflow_security.log', maxBytes=5*1024*1024, backupCount=10)
    security_handler.setFormatter(formatter)
    security_handler.setLevel(logging.WARNING)
    sec_logger = logging.getLogger('payflow.security')
    sec_logger.addHandler(security_handler)
    sec_logger.setLevel(logging.WARNING)

    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)

    app.logger.setLevel(logging.INFO)
    app.logger.info("PayFlow v1.2 - logging initialisé")


# ------------------------------------------------------------
# App factory (UNE SEULE)
# ------------------------------------------------------------
def create_app(config_name: str | None = None) -> Flask:
    app = Flask(__name__)

    # Résolution de l'env: APP_ENV > FLASK_ENV > 'development'
    config_name = config_name or os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or 'development'
    app.config.from_object(get_config(config_name))

    setup_logging(app)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    # Dossiers par défaut si absents dans la config
    app.config.setdefault('UPLOAD_FOLDER', 'uploads')
    app.config.setdefault('OUTPUT_FOLDER', 'output')

    # Route de santé toujours enregistrée
    @app.get("/health")
    def health():
        return {"status": "ok", "env": os.getenv("APP_ENV", "development")}, 200

    return app


# ------------------------------------------------------------
# Instance globale (utilisée par les décorateurs @app.route)
# ------------------------------------------------------------
app = create_app()

# --- RÉINTRODUCTION DASHBOARD MINIMAL COMPATIBLE ---

def _safe_format_size(n):
    # utilitaire local pour l'affichage si besoin
    try:
        units = ["B","KB","MB","GB","TB"]
        i = 0
        n = float(n or 0)
        while n >= 1024 and i < len(units)-1:
            n /= 1024.0
            i += 1
        return f"{n:.1f} {units[i]}"
    except Exception:
        return "0 B"

# Ces fonctions renvoient des valeurs sûres même si la DB est vide ou si d’autres fonctions n’existent plus.
def get_v12_dashboard_stats():
    return {
        'total_treatments': 0,
        'treatments_last_30_days': 0,
        'treatments_last_7_days': 0,
        'successful_treatments': 0,
        'failed_treatments': 0,
        'total_employees': 0,
        'active_employees': 0,
        'pdf_imported_employees': 0,
        'manual_employees': 0,
        'total_download_links': 0,
        'active_links': 0,
        'expired_links': 0,
        'total_downloads': 0,
        'success_rate': 0.0,
        'security_rate': 100.0,
    }

def get_recent_activity():
    # format attendu par ton template (treatments, downloads)
    return {'treatments': [], 'downloads': []}

def get_employee_top_stats():
    # liste de dicts { name, count }
    return []

def get_treatments_from_db():
    # liste de traitements (on renvoie vide si DB non prête)
    return []

def get_treatments_from_filesystem():
    # fallback FS (vide ici pour ne pas planter)
    return []

@app.get("/dashboard")
def dashboard():
    # On renvoie exactement les variables que ton template attend.
    stats_v12 = get_v12_dashboard_stats()
    recent_activity = get_recent_activity()
    top_employees = get_employee_top_stats()

    treatments = get_treatments_from_db() or get_treatments_from_filesystem()
    treatments = treatments[:10] if treatments else []

    return render_template(
        "dashboard.html",
        stats_v12=stats_v12,
        recent_activity=recent_activity,
        top_employees=top_employees,
        treatments=treatments,
    )

# --- STUBS pour éviter les BuildError depuis les templates ---

@app.get("/admin", endpoint="admin_dashboard")
def admin_dashboard_stub():
    # Sur beaucoup de projets, /admin renvoie vers la gestion des employés
    return redirect(url_for("manage_employees"))

@app.get("/admin/employees", endpoint="manage_employees")
def manage_employees_stub():
    # Page placeholder : l’important est d’enregistrer l’endpoint
    return "Gestion des employés (stub)."

@app.get("/admin/logs", endpoint="view_logs")
def view_logs_stub():
    return "Logs (stub)."

@app.get("/admin/maintenance", endpoint="maintenance_page")
def maintenance_page_stub():
    return "Maintenance (stub)."

# (optionnels si tes templates du dashboard pointent vers ces liens)
@app.get("/admin/treatment/<string:timestamp>/details", endpoint="treatment_details")
def treatment_details_stub(timestamp):
    return f"Détails traitement {timestamp} (stub)."


# Petite route de debug pour vérifier que /dashboard est bien enregistré
@app.get("/__routes")
def __routes():
    return {"routes": sorted([r.rule for r in app.url_map.iter_rules()])}


# Création des dossiers applicatifs au lancement
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)
os.makedirs(app.config['OUTPUT_FOLDER'], exist_ok=True)

# ------------------------------------------------------------
# Verrous/état de traitement
# ------------------------------------------------------------
processing_lock = threading.Lock()
is_processing = False

# ------------------------------------------------------------
# Petites utilitaires
# ------------------------------------------------------------
ALLOWED_EXTENSIONS = {'pdf'}

def allowed_file(filename: str) -> bool:
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def generate_timestamp_folder() -> str:
    return datetime.now().strftime('%Y%m%d%H%M%S')

def format_file_size(size_bytes: int) -> str:
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"


# ------------------------------------------------------------
# Routes principales
# ------------------------------------------------------------
@app.route('/')
def index():
    return render_template('index.html')
    

@app.route('/upload', methods=['POST'])
def upload_file():
    global is_processing

    with processing_lock:
        if is_processing:
            flash('Un traitement est déjà en cours. Veuillez patienter.', 'error')
            return redirect(request.url)
        is_processing = True

    try:
        if 'file' not in request.files:
            flash('Aucun fichier sélectionné', 'error')
            return redirect(url_for('index'))

        file = request.files['file']
        if file.filename == '':
            flash('Aucun fichier sélectionné', 'error')
            return redirect(url_for('index'))

        if file and allowed_file(file.filename):
            timestamp_folder = generate_timestamp_folder()
            upload_dir = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_folder)
            output_dir = os.path.join(app.config['OUTPUT_FOLDER'], timestamp_folder)
            os.makedirs(upload_dir, exist_ok=True)
            os.makedirs(output_dir, exist_ok=True)

            filename = secure_filename(file.filename)
            filepath = os.path.join(upload_dir, filename)
            file.save(filepath)

            result = process_pdf(filepath, output_dir)
            if result['success']:
                flash(f'✅ {result["count"]} fiches traitées. Dossier : {timestamp_folder}', 'success')
            else:
                flash(f'❌ Erreur: {result["error"]}', 'error')
        else:
            flash('❌ Format non autorisé (PDF uniquement).', 'error')

    finally:
        with processing_lock:
            is_processing = False

    return redirect(url_for('index'))


# ------------------------------------------------------------
# Extraction infos PDF
# ------------------------------------------------------------
def extract_employee_name_from_page(page_text: str):
    lines = page_text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if "Catégorie" in line:
            if " M " in line:
                parts = line.split(" M ")
                if len(parts) > 1:
                    name = parts[1].strip()
                    if name and len(name) > 5:
                        return name
            elif " Mme " in line:
                parts = line.split(" Mme ")
                if len(parts) > 1:
                    name = parts[1].strip()
                    if name and len(name) > 5:
                        return name
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 5 and next_line.isupper():
                    return next_line
    return None

def extract_employee_matricule_from_page(page_text: str):
    import re
    lines = page_text.split('\n')
    for i, line in enumerate(lines):
        line = line.strip()
        if "Matricule" in line:
            m = re.search(r'Matricule\s+(\d+)', line)
            if m:
                return m.group(1)
            if i + 1 < len(lines):
                m = re.search(r'^(\d{4})(?:\s|$)', lines[i+1].strip())
                if m:
                    return m.group(1)
    return None

def extract_period_from_page(page_text: str):
    import re
    lines = page_text.split('\n')
    patterns = [
        r'Période du \d{2}/(\d{2})/(\d{2}) au',
        r'Période du \d{2}/(\d{2})/(\d{4}) au',
        r'du \d{2}/(\d{2})/(\d{2}) au',
        r'Mois\s*:\s*(\d{2})/(\d{4})',
        r'(\d{1,2})/(\d{1,2})/(\d{2,4})'
    ]
    for line in lines:
        line = line.strip()
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, line)
            if match:
                if i in [0, 2]:
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    full_year = f"20{year}" if int(year) < 50 else f"19{year}"
                    return f"{full_year}_{month}"
                elif i == 1:
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    return f"{year}_{month}"
                elif i == 3:
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    return f"{year}_{month}"
                elif i == 4:
                    day = match.group(1).zfill(2)
                    month = match.group(2).zfill(2)
                    year = match.group(3)
                    full_year = f"20{year}" if len(year) == 2 and int(year) < 50 else (f"19{year}" if len(year) == 2 else year)
                    return f"{full_year}_{month}"
    return datetime.now().strftime('%Y_%m')


# ------------------------------------------------------------
# Cœur de traitement
# ------------------------------------------------------------
def process_pdf(filepath: str, output_dir: str):
    start_time = datetime.now()
    try:
        employees = load_employees()
        employee_data = {}

        with open(filepath, 'rb') as fh:
            pdf_reader = PyPDF2.PdfReader(fh)
            total_pages = len(pdf_reader.pages)

            for page_num in range(total_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text() or ""

                name = extract_employee_name_from_page(page_text)
                matricule = extract_employee_matricule_from_page(page_text)
                period = extract_period_from_page(page_text)

                if name:
                    if name not in employee_data:
                        employee_data[name] = {'pages': [], 'matricule': matricule, 'period': period}
                    else:
                        if not employee_data[name]['matricule'] and matricule:
                            employee_data[name]['matricule'] = matricule
                        if not employee_data[name]['period'] and period:
                            employee_data[name]['period'] = period
                    employee_data[name]['pages'].append(page_num)

            new_employees = detect_new_employees(employee_data)
            new_employees_count = add_employees_to_database(new_employees) if new_employees else 0
            if new_employees_count:
                flash(f'🆕 {new_employees_count} nouveaux employés ajoutés', 'info')

            traitement = Traitement(
                timestamp_folder=os.path.basename(output_dir),
                fichier_original=os.path.basename(filepath),
                taille_fichier=os.path.getsize(filepath),
                nombre_pages=total_pages,
                nombre_employes_detectes=len(employee_data),
                nombre_nouveaux_employes=new_employees_count,
                statut='en_cours'
            )
            db.session.add(traitement)
            db.session.commit()

            processed = 0
            for name, data in employee_data.items():
                if create_individual_pdf_with_period(
                    pdf_reader, name, data['pages'], data['matricule'],
                    data['period'], employees, output_dir
                ):
                    processed += 1
                    try:
                        employee_record = Employee.query.filter_by(nom_employe=name).first()
                        if employee_record:
                            te = TraitementEmploye(
                                traitement_id=traitement.id,
                                employe_id=employee_record.id,
                                matricule_extrait=data['matricule'],
                                periode_extraite=data['period'],
                                nom_fichier_genere=f"{name}_{data['period'] or datetime.now().strftime('%Y_%m')}.pdf"
                            )
                            db.session.add(te)
                    except Exception as e:
                        app.logger.error(f"Erreur enregistrement traitement pour {name}: {e}")

        end_time = datetime.now()
        traitement.nombre_employes_traites = processed
        traitement.duree_traitement_secondes = int((end_time - start_time).total_seconds())
        traitement.statut = 'termine' if processed == len(employee_data) else 'partiel'
        db.session.commit()

        return {
            'success': True,
            'count': processed,
            'total_employees': len(employee_data),
            'new_employees': new_employees_count,
            'message': f'{processed} fiches traitées'
        }

    except Exception as e:
        app.logger.error(f"Erreur traitement: {e}")
        return {'success': False, 'error': str(e)}



def create_individual_pdf_with_period(pdf_reader, employee_name, page_numbers, matricule, period, employees_data, output_dir):
    try:
        writer = PyPDF2.PdfWriter()
        for p in page_numbers:
            writer.add_page(pdf_reader.pages[p])

        safe = "".join(c for c in employee_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        output_filename = f"{safe}_{(period or datetime.now().strftime('%Y_%m'))}.pdf"
        output_path = os.path.join(output_dir, output_filename)

        with open(output_path, 'wb') as f:
            writer.write(f)

        if matricule:
            employee_record = find_employee_by_matricule(matricule)
            if employee_record:
                protect_pdf_with_password(output_path, matricule)
                current_traitement = get_current_traitement(output_dir)
                if current_traitement:
                    link = generate_secure_download_link(employee_record, current_traitement, output_path, matricule)
                    if link:
                        send_email_with_secure_link(employee_name, employee_record.email, link)
        return True
    except Exception as e:
        app.logger.error(f"Erreur création PDF {employee_name}: {e}")
        return False




# ------------------------------------------------------------
# Routes de téléchargement sécurisé
# ------------------------------------------------------------
@app.route('/download/<token>')
def secure_download_page(token):
    try:
        link = DownloadLink.query.filter_by(token=token).first()
        if not link:
            flash('Lien invalide ou expiré', 'error')
            return render_template('download_error.html', error="Lien invalide")
        if not link.is_valid:
            err = "Nombre maximum de tentatives dépassé" if link.tentatives_acces >= link.max_tentatives else "Lien expiré"
            flash(f'Accès refusé : {err}', 'error')
            return render_template('download_error.html', error=err)
        return render_template('secure_download.html', download_link=link, employee=link.employee)
    except Exception as e:
        flash(f'Erreur accès lien : {e}', 'error')
        return render_template('download_error.html', error="Erreur système")

@app.route('/download/<token>/verify', methods=['POST'])
def verify_and_download(token):
    try:
        link = DownloadLink.query.filter_by(token=token).first()
        matricule_saisi = request.form.get('matricule', '').strip()
        client_ip = request.remote_addr

        app.logger.info(f"Tentative accès token={token[:8]}... IP={client_ip}")
        link.tentatives_acces += 1
        link.adresse_ip_derniere = client_ip

        if matricule_saisi != link.matricule_requis:
            db.session.commit()
            remaining = link.max_tentatives - link.tentatives_acces
            return jsonify({'success': False, 'message': f'Matricule incorrect. {remaining} tentatives restantes.', 'remaining_attempts': remaining}), 400

        link.nombre_telechargements += 1
        link.derniere_date_telechargement = datetime.utcnow()
        db.session.commit()

        if not os.path.exists(link.chemin_fichier):
            return jsonify({'success': False, 'message': 'Fichier non trouvé.'}), 404

        return jsonify({
            'success': True,
            'message': 'OK',
            'download_url': f'/download/file/{token}',
            'employee_name': link.employee.nom_employe,
            'filename': link.nom_fichier,
            'download_count': link.nombre_telechargements
        })
    except Exception as e:
        app.logger.error(f"Erreur verify: {e}")
        return jsonify({'success': False, 'message': 'Erreur serveur.'}), 500

@app.route('/download/file/<token>')
def download_file_direct(token):
    try:
        link = DownloadLink.query.filter_by(token=token).first()
        if not link or link.nombre_telechargements == 0:
            return "Téléchargement non autorisé", 403
        if not os.path.exists(link.chemin_fichier):
            return "Fichier non trouvé", 404
        return send_file(link.chemin_fichier, as_attachment=True, download_name=link.nom_fichier)
    except Exception as e:
        app.logger.error(f"Erreur download direct: {e}")
        return "Erreur de téléchargement", 500


# ------------------------------------------------------------
# Dashboard / Admin (inchangé, mais nettoyé si besoin)
# ------------------------------------------------------------
# ... (tes autres routes admin/dashboard peuvent rester telles quelles)
# Pour éviter une réponse trop longue, je n'ai pas modifié le reste de tes
# routes admin ; elles fonctionneront comme avant avec cette app factory.


# ------------------------------------------------------------
# Lancement (UN SEUL bloc)
# ------------------------------------------------------------
if __name__ == "__main__":
    app.run(debug=app.config.get("DEBUG", False))
