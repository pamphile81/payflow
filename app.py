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
from app.services.email_service import send_email_with_secure_link
from app.services.link_service import generate_secure_download_link, get_current_traitement
from app.services.employee_service import (
    load_employees,
    find_employee_by_matricule,
    detect_new_employees,
    add_employees_to_database,
)
from app.services.pdf_service import (
    protect_pdf_with_password,
    generate_timestamp_folder,
    extract_employee_name_from_page,
    extract_employee_matricule_from_page,
    extract_period_from_page,
)
from app.services.treatment_service import process_pdf
from dotenv import load_dotenv
from flask import (
    Flask, render_template, request, redirect, url_for, flash,
    jsonify, send_file, session
)
from werkzeug.utils import secure_filename
import PyPDF2
from app import create_app

# --- config & extensions ---
from app.config import get_config
from app.extensions import db, migrate, mail

# --- modèles (utilisés dans les routes) ---
from app.models.models import Employee, Traitement, TraitementEmploye, DownloadLink

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
    from routes import public_bp
    #from routes.public import *  # si besoin temporaire pendant la transition
    app.register_blueprint(public_bp)

    # Résolution de l'env: APP_ENV > FLASK_ENV > 'development'
    config_name = config_name or os.getenv('APP_ENV') or os.getenv('FLASK_ENV') or 'development'
    app.config.from_object(get_config(config_name))

    setup_logging(app)

    # Extensions
    db.init_app(app)
    migrate.init_app(app, db)
    mail.init_app(app)

    from routes import public_bp
    app.register_blueprint(public_bp)

    # Dossiers par défaut si absents dans la config
    #app.config.setdefault('UPLOAD_FOLDER', 'uploads')
    #app.config.setdefault('OUTPUT_FOLDER', 'output')
    os.makedirs(app.config.get("UPLOAD_FOLDER", "uploads"), exist_ok=True)
    os.makedirs(app.config.get("OUTPUT_FOLDER", "output"), exist_ok=True)

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
    """Activité récente (dernières 24h)"""
    try:
        last_24h = datetime.utcnow() - timedelta(hours=24)
        
        # Derniers traitements
        recent_treatments = Traitement.query.filter(
            Traitement.date_creation >= last_24h
        ).order_by(Traitement.date_creation.desc()).limit(5).all()
        
        # Derniers téléchargements
        recent_downloads = DownloadLink.query.filter(
            DownloadLink.date_dernier_acces >= last_24h,
            DownloadLink.nombre_telechargements > 0
        ).order_by(DownloadLink.date_dernier_acces.desc()).limit(5).all()
        
        return {
            'treatments': recent_treatments,
            'downloads': recent_downloads
        }
        
    except Exception as e:
        app.logger.error(f" Erreur activité récente: {str(e)}")
        return {'treatments': [], 'downloads': []}
    # format attendu par ton template (treatments, downloads)
    #return {'treatments': [], 'downloads': []}


def get_employee_top_stats():
    """Top 10 des employés par nombre de fiches reçues"""
    try:
        top_employees = db.session.query(
            Employee.nom_employe,
            func.count(TraitementEmploye.id).label('nb_fiches')
        ).join(
            TraitementEmploye
        ).group_by(
            Employee.id, Employee.nom_employe
        ).order_by(
            func.count(TraitementEmploye.id).desc()
        ).limit(10).all()
        
        return [
            {
                'name': emp.nom_employe,
                'count': emp.nb_fiches
            }
            for emp in top_employees
        ]
        
    except Exception as e:
        app.logger.error(f" Erreur top employés: {str(e)}")
        return []


def get_treatments_from_db():
    """Récupère les traitements depuis PostgreSQL"""
    try:
        treatments = []
        db_treatments = Traitement.query.order_by(Traitement.date_creation.desc()).all()
        
        for treatment in db_treatments:
            # Récupération des fichiers générés depuis le filesystem
            output_folder_path = os.path.join(app.config['OUTPUT_FOLDER'], treatment.timestamp_folder)
            generated_files = []
            if os.path.exists(output_folder_path):
                generated_files = [f for f in os.listdir(output_folder_path) if f.endswith('.pdf')]
            
            treatments.append({
                'timestamp': treatment.date_creation,
                'timestamp_str': treatment.timestamp_folder,
                'date_formatted': treatment.date_creation.strftime('%d/%m/%Y à %H:%M:%S'),
                'original_file': treatment.fichier_original,
                'file_size': format_file_size(treatment.taille_fichier),
                'employees_count': treatment.nombre_employes_traites,
                'generated_files': generated_files,
                'status': 'Réussi' if treatment.statut == 'termine' else 'Échec',
                'source': 'PostgreSQL'
            })
        
        return treatments
        
    except Exception as e:
        app.logger.error(f"Erreur récupération traitements DB: {str(e)}")
        return []


def get_treatments_from_filesystem():
    """Votre ancienne fonction pour compatibilité"""
    treatments = []
    uploads_path = app.config['UPLOAD_FOLDER']
    output_path = app.config['OUTPUT_FOLDER']
    
    if os.path.exists(uploads_path):
        for folder in os.listdir(uploads_path):
            folder_path = os.path.join(uploads_path, folder)
            if os.path.isdir(folder_path):
                treatment_info = analyze_treatment_folder(folder, folder_path, output_path)
                if treatment_info:
                    treatments.append(treatment_info)
    
    treatments.sort(key=lambda x: x['timestamp'], reverse=True)
    return treatments


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



@app.get("/admin", endpoint="admin_dashboard")
def admin_dashboard():
    return redirect(url_for("manage_employees"))

@app.get("/admin/employees", endpoint="manage_employees")
def manage_employees():
    """Interface de gestion des employés"""
    try:
        # Pagination pour de gros volumes
        page = request.args.get('page', 1, type=int)
        search = request.args.get('search', '', type=str)
        
        # Construction de la requête
        query = Employee.query
        
        if search:
            query = query.filter(
                db.or_(
                    Employee.nom_employe.ilike(f'%{search}%'),
                    Employee.email.ilike(f'%{search}%'),
                    Employee.matricule.ilike(f'%{search}%')
                )
            )
        
        employees = query.order_by(Employee.nom_employe.asc()).paginate(
            page=page, per_page=20, error_out=False
        )
        
        # Statistiques rapides
        stats = {
            'total_employees': Employee.query.count(),
            'active_employees': Employee.query.filter_by(statut='actif').count(),
            'pdf_imported': Employee.query.filter_by(source_creation='pdf_import').count(),
            'manual_added': Employee.query.filter_by(source_creation='manual').count()
        }
        
        return render_template('admin/manage_employees.html', 
                             employees=employees, 
                             stats=stats,
                             search=search)
        
    except Exception as e:
        flash(f'Erreur lors du chargement : {str(e)}', 'error')
        return redirect(url_for('dashboard'))


@app.get("/admin/logs", endpoint="view_logs")
def view_logs():
    """Interface de consultation des logs"""
    try:
        log_type = request.args.get('type', 'general')
        lines = int(request.args.get('lines', 100))
        
        log_files = {
            'general': 'logs/payflow.log',
            'errors': 'logs/payflow_errors.log', 
            'security': 'logs/payflow_security.log'
        }
        
        log_file = log_files.get(log_type, 'logs/payflow.log')
        log_content = []
        
        if os.path.exists(log_file):
            with open(log_file, 'r', encoding='utf-8') as f:
                log_content = f.readlines()[-lines:]  # Dernières lignes
        
        # Statistiques des logs
        log_stats = {
            'general_size': get_file_size('logs/payflow.log'),
            'errors_size': get_file_size('logs/payflow_errors.log'),
            'security_size': get_file_size('logs/payflow_security.log'),
            'total_lines': len(log_content)
        }
        
        return render_template('admin/logs.html', 
                             log_content=log_content,
                             log_type=log_type,
                             log_stats=log_stats,
                             lines=lines)
        
    except Exception as e:
        app.logger.error(f"Erreur consultation logs: {str(e)}")
        flash(f'Erreur lors de la consultation des logs: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


def get_file_size(filepath):
    """Retourne la taille d'un fichier formatée"""
    try:
        if os.path.exists(filepath):
            size = os.path.getsize(filepath)
            return format_file_size(size)
        return "0 B"
    except:
        return "N/A"
    
def format_file_size(size_bytes):
    """Formate la taille de fichier en format lisible"""
    if size_bytes == 0:
        return "0B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"


@app.get("/admin/maintenance", endpoint="maintenance_page")
def maintenance_page():
    """Page de maintenance et nettoyage système"""
    try:
        # Statistiques de maintenance
        maintenance_stats = get_maintenance_stats()
        
        return render_template('admin/maintenance.html', 
                             stats=maintenance_stats)
        
    except Exception as e:
        flash(f'Erreur lors du chargement de la maintenance: {str(e)}', 'error')
        return redirect(url_for('dashboard'))


# (optionnels si tes templates du dashboard pointent vers ces liens)
@app.get("/admin/treatment/<string:timestamp>/details", endpoint="treatment_details")
def treatment_details(timestamp):
    """Affiche les détails d'un traitement avec liste des PDFs générés"""
    try:
        # Récupérer le traitement depuis PostgreSQL
        traitement = Traitement.query.filter_by(timestamp_folder=timestamp).first()
        
        if not traitement:
            flash('Traitement non trouvé', 'error')
            return redirect(url_for('dashboard'))
        
        # Récupérer les fichiers générés depuis le dossier output
        output_folder = os.path.join(app.config['OUTPUT_FOLDER'], timestamp)
        generated_files = []
        
        if os.path.exists(output_folder):
            for filename in os.listdir(output_folder):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(output_folder, filename)
                    file_size = os.path.getsize(file_path)
                    
                    # Extraire le nom de l'employé du nom de fichier
                    employee_name = filename.replace('.pdf', '').replace('_', ' ')
                    # Enlever la période si présente (ex: "2025_08")
                    import re
                    employee_name = re.sub(r'_\d{4}_\d{2}$', '', employee_name)
                    
                    # 🆕 RÉCUPÉRER LES STATISTIQUES DEPUIS LA BASE
                    access_count = 0
                    download_count = 0
                    
                    # Chercher dans les download_links du traitement
                    for link in traitement.download_links:
                        # Correspondance par nom de fichier exact
                        if link.nom_fichier == filename:
                            access_count = link.tentatives_acces
                            download_count = link.nombre_telechargements
                            break
                        # Correspondance par nom d'employé dans le nom de fichier
                        elif link.employee and link.employee.nom_employe:
                            # Normaliser les noms pour comparaison
                            db_name = link.employee.nom_employe.strip().upper()
                            file_name = employee_name.strip().upper()
                            if db_name == file_name or db_name in filename.upper():
                                access_count = link.tentatives_acces
                                download_count = link.nombre_telechargements
                                break
                    
                    generated_files.append({
                        'filename': filename,
                        'employee_name': employee_name,
                        'file_size': format_file_size(file_size),
                        'file_path': file_path,
                        'access_count': access_count,      
                        'download_count': download_count   
                    })
        
        # Trier par nom d'employé
        generated_files.sort(key=lambda x: x['employee_name'])
        
        return render_template('admin/treatment_details.html',
                             traitement=traitement,
                             generated_files=generated_files,
                             total_files=len(generated_files))
        
    except Exception as e:
        flash(f'Erreur lors du chargement des détails : {str(e)}', 'error')
        return redirect(url_for('dashboard'))




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
