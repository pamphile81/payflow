# app.py - Version v1.2 avec PostgreSQL
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify, send_file
import os
import csv
from werkzeug.utils import secure_filename
import PyPDF2
import pikepdf
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.mime.text import MIMEText
from email_config import GMAIL_CONFIG
from datetime import datetime, timedelta
import threading
import time
import json
from flask_sqlalchemy import SQLAlchemy
from flask_migrate import Migrate
import hashlib
import secrets
import logging
from logging.handlers import RotatingFileHandler
import glob

# Import des modèles et configuration
from config import config
from models import db, Employee, Traitement, TraitementEmploye, DownloadLink

# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False

def setup_logging(app):
    """Configure le système de logging pour PayFlow"""
    
    # Créer le dossier logs s'il n'existe pas
    if not os.path.exists('logs'):
        os.makedirs('logs')
    
    # Configuration du format des logs
    formatter = logging.Formatter(
        '[%(asctime)s] %(levelname)s in %(module)s: %(message)s'
    )
    
    # 1. Log général de l'application (rotation 10MB, 10 fichiers)
    file_handler = RotatingFileHandler(
        'logs/payflow.log', 
        maxBytes=10*1024*1024,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    file_handler.setLevel(logging.INFO)
    app.logger.addHandler(file_handler)
    
    # 2. Log des erreurs uniquement
    error_handler = RotatingFileHandler(
        'logs/payflow_errors.log',
        maxBytes=5*1024*1024,   # 5MB
        backupCount=5
    )
    error_handler.setFormatter(formatter)
    error_handler.setLevel(logging.ERROR)
    app.logger.addHandler(error_handler)
    
    # 3. Log des accès sécurisés (téléchargements)
    security_handler = RotatingFileHandler(
        'logs/payflow_security.log',
        maxBytes=5*1024*1024,   # 5MB  
        backupCount=10
    )
    security_handler.setFormatter(formatter)
    security_handler.setLevel(logging.WARNING)
    
    # Logger sécurité séparé
    security_logger = logging.getLogger('payflow.security')
    security_logger.addHandler(security_handler)
    security_logger.setLevel(logging.WARNING)
    
    # 4. Console pour le développement
    if app.debug:
        console_handler = logging.StreamHandler()
        console_handler.setFormatter(formatter)
        console_handler.setLevel(logging.DEBUG)
        app.logger.addHandler(console_handler)
    
    # Niveau global
    app.logger.setLevel(logging.INFO)
    
    app.logger.info(" PayFlow v1.2 - Système de logging initialisé")
    return security_logger

def create_app(config_name='default'):
    """Factory pour créer l'application Flask"""
    app = Flask(__name__)

    # Ajouter à votre create_app() ou au début de app.py
    security_logger = setup_logging(app)
    
    # Configuration
    app.config.from_object(config[config_name])
    
    # Initialisation des extensions
    db.init_app(app)
    migrate = Migrate(app, db)
    
    # Configuration des dossiers (existant)
    app.config['UPLOAD_FOLDER'] = app.config.get('UPLOAD_FOLDER', 'uploads')
    app.config['OUTPUT_FOLDER'] = app.config.get('OUTPUT_FOLDER', 'output')
    
    return app

# Création de l'application
app = create_app(os.getenv('FLASK_ENV', 'development'))

#app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # À changer en production

# Configuration des dossiers
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

def generate_timestamp_folder():
    """Génère un nom de dossier avec timestamp au format aaaammjjhhmmss"""
    now = datetime.now()
    return now.strftime('%Y%m%d%H%M%S')

def debug_page_content(page_text, page_num):
    """Fonction de débogage pour voir le contenu d'une page"""
    lines = page_text.split('\n')
    app.logger.info(f"\n--- Contenu de la page {page_num + 1} ---")
    for i, line in enumerate(lines[:20]):  # Affiche les 20 premières lignes
        line = line.strip()
        if line:  # Ignore les lignes vides
            app.logger.info(f"Ligne {i+1}: '{line}'")
    app.logger.info("--- Fin du contenu ---\n")


def allowed_file(filename):
    """Vérifie si le fichier est un PDF"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

# Chargement des employés de
def load_employees():
    """Charge les employés depuis PostgreSQL avec matricule comme clé"""
    employees = {}
    try:
        employees_list = Employee.query.filter_by(statut='actif').all()
        for emp in employees_list:
            # ✅ Clé par nom ET matricule pour compatibilité
            employees[emp.nom_employe] = {
                'email': emp.email,
                'id': emp.id,
                'matricule': emp.matricule  # Disponible pour vérifications
            }
        app.logger.info(f"📊 {len(employees)} employés chargés (identifiés par matricule)")
        return employees
    except Exception as e:
        app.logger.error(f"❌ Erreur lors du chargement des employés: {str(e)}")
        return {}


def find_employee_by_matricule(matricule):
    """Trouve un employé par son matricule (plus fiable que le nom)"""
    try:
        return Employee.query.filter_by(matricule=matricule, statut='actif').first()
    except Exception as e:
        app.logger.error(f"❌ Erreur recherche matricule {matricule}: {str(e)}")
        return None

@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])  # IMPORTANT: Cette ligne doit être exactement comme ça
def upload_file():
    """Traite le fichier PDF uploadé avec débogage"""
    # DÉBOGAGE - à supprimer après test

    if 'file' in request.files:
        app.logger.info(f"Nom du fichier chargé: {request.files['file'].filename}")
    app.logger.info("===============")

    """Traite le fichier PDF uploadé avec protection contre les soumissions multiples"""
    global is_processing
    
    # Vérification côté serveur pour empêcher les traitements multiples
    with processing_lock:
        if is_processing:
            flash('⚠️ Un traitement est déjà en cours. Veuillez patienter.', 'error')
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
            try:
                # Génération du timestamp pour l'organisation des dossiers
                timestamp_folder = generate_timestamp_folder()
                
                # Création des dossiers avec timestamp
                upload_timestamp_dir = os.path.join(app.config['UPLOAD_FOLDER'], timestamp_folder)
                output_timestamp_dir = os.path.join(app.config['OUTPUT_FOLDER'], timestamp_folder)
                
                os.makedirs(upload_timestamp_dir, exist_ok=True)
                os.makedirs(output_timestamp_dir, exist_ok=True)
                
                # Sauvegarde du fichier dans le dossier timestampé
                filename = secure_filename(file.filename)
                filepath = os.path.join(upload_timestamp_dir, filename)
                file.save(filepath)
                
                #app.logger.info(f"📁 Fichier sauvegardé dans : {upload_timestamp_dir}")
                #app.logger.info(f"📁 Fichiers de sortie iront dans : {output_timestamp_dir}")
                
                # Traitement du PDF avec les nouveaux chemins
                result = process_pdf(filepath, output_timestamp_dir)
                
                if result['success']:
                    flash(f'✅ Traitement terminé avec succès ! {result["count"]} fiches traitées. Dossier : {timestamp_folder}', 'success')
                else:
                    flash(f'❌ Erreur lors du traitement: {result["error"]}', 'error')
                
            except Exception as e:
                flash(f'❌ Erreur inattendue: {str(e)}', 'error')
                
        else:
            flash('❌ Format de fichier non autorisé. Utilisez un PDF.', 'error')
            
    finally:
        # Libérer le verrou même en cas d'erreur
        with processing_lock:
            is_processing = False
            
    return redirect(url_for('index'))

def extract_employee_name_from_page(page_text):
    """Extrait le nom de l'employé depuis le texte d'une page"""
    lines = page_text.split('\n')
    
    # Recherche du pattern "Catégorie" suivi de "M" ou "Mme" puis du nom
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Cherche la ligne contenant "Catégorie"
        if "Catégorie" in line:
            # Le nom peut être sur la même ligne ou sur les lignes suivantes
            
            # Cas 1 : Le nom est sur la même ligne après "M" ou "Mme"
            if " M " in line:
                # Extrait tout ce qui suit "M "
                parts = line.split(" M ")
                if len(parts) > 1:
                    name = parts[1].strip()
                    if name and len(name) > 5:  # Vérifie qu'il y a bien un nom
                        return name
            
            elif " Mme " in line:
                # Extrait tout ce qui suit "Mme "
                parts = line.split(" Mme ")
                if len(parts) > 1:
                    name = parts[1].strip()
                    if name and len(name) > 5:  # Vérifie qu'il y a bien un nom
                        return name
            
            # Cas 2 : Le nom est sur la ligne suivante
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                if next_line and len(next_line) > 5 and next_line.isupper():
                    return next_line
    
    return None

def extract_employee_matricule_from_page(page_text):
    """Extrait le matricule de l'employé depuis le texte d'une page"""
    lines = page_text.split('\n')
    
    # Recherche du pattern "Matricule" suivi du numéro
    for i, line in enumerate(lines):
        line = line.strip()
        
        # Cherche la ligne contenant "Matricule"
        if "Matricule" in line:
            # Le matricule peut être sur la même ligne ou sur les lignes suivantes
            
            # Cas 1 : Le matricule est sur la même ligne après "Matricule"
            # Exemple : "Matricule 2204      Ancienneté 2an(s) et 8mois"
            import re
            matricule_match = re.search(r'Matricule\s+(\d+)', line)
            if matricule_match:
                return matricule_match.group(1)
            
            # Cas 2 : Le matricule pourrait être sur la ligne suivante
            if i + 1 < len(lines):
                next_line = lines[i + 1].strip()
                # Recherche d'un nombre de 4 chiffres (format matricule courant)
                matricule_match = re.search(r'^(\d{4})(?:\s|$)', next_line)
                if matricule_match:
                    return matricule_match.group(1)
    
    return None

def create_individual_pdf_with_matricule(pdf_reader, employee_name, page_numbers, matricule, employees_data, output_dir):
    """Crée un PDF individuel pour un employé avec protection par matricule extrait du PDF"""
    try:
        # Création du PDF de sortie
        pdf_writer = PyPDF2.PdfWriter()
        
        # Ajout des pages de l'employé
        for page_num in page_numbers:
            pdf_writer.add_page(pdf_reader.pages[page_num])
        
        # Nom du fichier de sortie dans le dossier timestampé
        safe_filename = "".join(c for c in employee_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        output_filename = f"{safe_filename}.pdf"
        output_path = os.path.join(output_dir, output_filename)
        
        # Sauvegarde du PDF
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)
        
        # Protection et envoi si l'employé est dans la base ET matricule trouvé
        if employee_name in employees_data and matricule:
            email = employees_data[employee_name]['email']
            
            # Protection du PDF avec le matricule extrait du PDF
            protect_pdf_with_password(output_path, matricule)
            app.logger.info(f"📄 PDF créé et protégé pour {employee_name} avec matricule {matricule} (extrait du PDF)")
            
            # APPEL CORRIGÉ : Seulement 3 paramètres, SANS le matricule
            if send_email_with_secure_link(employee_name, email, output_path):
                app.logger.info(f"✅ Processus complet réussi pour {employee_name}")
            else:
                app.logger.info(f"❌ Erreur lors de l'envoi pour {employee_name}")
                
        elif employee_name in employees_data and not matricule:
            app.logger.info(f"⚠️ Employé {employee_name} trouvé mais matricule non détecté - PDF créé sans protection")
            
        else:
            app.logger.info(f"📄 PDF créé SANS protection pour {employee_name} (non trouvé dans employees.csv)")
        
        return True
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la création du PDF pour {employee_name}: {str(e)}")
        return False

def extract_period_from_page(page_text):
    """Extrait la période du bulletin (année_mois) depuis le texte d'une page"""
    lines = page_text.split('\n')
    
    import re
    
    # Patterns de recherche pour différents formats de date
    patterns = [
        # Format: "Période du 01/08/25 au 31/08/25"
        r'Période du \d{2}/(\d{2})/(\d{2}) au',
        # Format: "Période du 01/08/2025 au 31/08/2025"
        r'Période du \d{2}/(\d{2})/(\d{4}) au',
        # Format: "du 01/08/25 au 31/08/25"
        r'du \d{2}/(\d{2})/(\d{2}) au',
        # Format: "Mois: 08/2025" ou "Mois : 08/2025"
        r'Mois\s*:\s*(\d{2})/(\d{4})',
        # Format général date: "31/08/25" ou "01/08/2025"
        r'(\d{1,2})/(\d{1,2})/(\d{2,4})'
    ]
    
    for line in lines:
        line = line.strip()
        
        # Test de chaque pattern
        for i, pattern in enumerate(patterns):
            match = re.search(pattern, line)
            if match:
                if i in [0, 2]:  # Patterns avec jours/mois/année à 2 chiffres
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    # Convertir année 2 chiffres en 4 chiffres
                    full_year = f"20{year}" if int(year) < 50 else f"19{year}"
                    return f"{full_year}_{month}"
                    
                elif i == 1:  # Pattern avec année à 4 chiffres
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    return f"{year}_{month}"
                    
                elif i == 3:  # Pattern "Mois: MM/YYYY"
                    month = match.group(1).zfill(2)
                    year = match.group(2)
                    return f"{year}_{month}"
                    
                elif i == 4:  # Pattern date générale
                    day = match.group(1).zfill(2)
                    month = match.group(2).zfill(2)
                    year = match.group(3)
                    # Convertir année si nécessaire
                    if len(year) == 2:
                        full_year = f"20{year}" if int(year) < 50 else f"19{year}"
                    else:
                        full_year = year
                    return f"{full_year}_{month}"
    
    # Si aucune date trouvée, utiliser la date actuelle
    from datetime import datetime
    now = datetime.now()
    app.logger.info("⚠️ Aucune période trouvée dans le PDF, utilisation de la date actuelle")
    return now.strftime('%Y_%m')


def process_pdf(filepath, output_dir):
    """Fonction principale avec auto-import des employés - CORRIGÉE"""
    start_time = datetime.now()
    
    try:
        # 1. Chargement des employés existants
        employees = load_employees()
        employee_data = {}
        
        # 2. IMPORTANT : Garde le fichier ouvert pendant TOUT le traitement
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            app.logger.info(f"📄 Analyse du PDF avec {total_pages} pages...")
            
            # Analyse de chaque page
            for page_num in range(total_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                
                employee_name = extract_employee_name_from_page(page_text)
                employee_matricule = extract_employee_matricule_from_page(page_text)
                period = extract_period_from_page(page_text)
                
                if employee_name:
                    app.logger.info(f"Page {page_num + 1}: Employé trouvé - {employee_name}")
                    if employee_matricule:
                        app.logger.info(f"Page {page_num + 1}: Matricule trouvé - {employee_matricule}")
                    if period:
                        app.logger.info(f"Page {page_num + 1}: Période trouvée - {period}")
                    
                    if employee_name not in employee_data:
                        employee_data[employee_name] = {
                            'pages': [],
                            'matricule': employee_matricule,
                            'period': period
                        }
                    else:
                        if not employee_data[employee_name]['matricule'] and employee_matricule:
                            employee_data[employee_name]['matricule'] = employee_matricule
                        if not employee_data[employee_name]['period'] and period:
                            employee_data[employee_name]['period'] = period
                    
                    employee_data[employee_name]['pages'].append(page_num)
            
            # 3. Détection des nouveaux employés
            new_employees = detect_new_employees(employee_data)
            new_employees_count = 0
            
            if new_employees:
                app.logger.info(f"\n🆕 Nouveaux employés détectés: {len(new_employees)}")
                new_employees_count = add_employees_to_database(new_employees)
                employees = load_employees()  # Recharger après ajout
                
                if new_employees_count > 0:
                    flash(f'🆕 {new_employees_count} nouveaux employés détectés et ajoutés !', 'info')
            
            # 4. Enregistrement du traitement
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
            
            # 5. ✅ Création des PDF individuels PENDANT que le fichier est ouvert
            processed_count = 0
            for employee_name, data in employee_data.items():
                if create_individual_pdf_with_period(
                    pdf_reader,  # ✅ Le fichier est encore ouvert ici
                    employee_name,
                    data['pages'],
                    data['matricule'],
                    data['period'],
                    employees,
                    output_dir
                ):
                    processed_count += 1
                    
                    # Enregistrement du traitement par employé
                    try:
                        employee_record = Employee.query.filter_by(nom_employe=employee_name).first()
                        if employee_record:
                            traitement_employe = TraitementEmploye(
                                traitement_id=traitement.id,
                                employe_id=employee_record.id,
                                matricule_extrait=data['matricule'],
                                periode_extraite=data['period'],
                                nom_fichier_genere=f"{employee_name}_{data['period'] or datetime.now().strftime('%Y_%m')}.pdf"
                            )
                            db.session.add(traitement_employe)
                    except Exception as e:
                        app.logger.error(f"⚠️ Erreur enregistrement traitement pour {employee_name}: {str(e)}")
        
        # 6. Finalisation (le fichier est maintenant fermé)
        end_time = datetime.now()
        processing_duration = (end_time - start_time).total_seconds()
        
        traitement.nombre_employes_traites = processed_count
        traitement.duree_traitement_secondes = int(processing_duration)
        traitement.statut = 'termine' if processed_count == len(employee_data) else 'partiel'
        
        db.session.commit()
        
        return {
            'success': True,
            'count': processed_count,
            'total_employees': len(employee_data),
            'new_employees': new_employees_count,
            'message': f'{processed_count} fiches traitées sur {len(employee_data)} employés détectés' +
                      (f' (dont {new_employees_count} nouveaux)' if new_employees_count > 0 else '')
        }
        
    except Exception as e:
        app.logger.error(f"❌ Erreur lors du traitement: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def detect_new_employees(employee_data_from_pdf):
    """Détecte les nouveaux employés par matricule (plus fiable que le nom)"""
    
    existing_matricules = set()
    try:
        employees_in_db = Employee.query.filter_by(statut='actif').all()
        existing_matricules = {emp.matricule for emp in employees_in_db if emp.matricule}
    except Exception as e:
        app.logger.info(f"❌ Erreur lors de la vérification des matricules: {str(e)}")
        return []
    
    new_employees = []
    for employee_name, data in employee_data_from_pdf.items():
        matricule = data.get('matricule')
        if matricule and matricule not in existing_matricules:
            new_employees.append({
                'nom': employee_name,
                'matricule': matricule,
                'period': data.get('period')
            })
    
    app.logger.info(f"🆕 {len(new_employees)} nouveaux employés détectés par matricule")
    return new_employees


def add_employees_to_database(new_employees, source='pdf_import'):
    """Ajoute les nouveaux employés avec matricule obligatoire"""
    
    added_count = 0
    for emp_data in new_employees:
        try:
            if not emp_data.get('matricule'):
                app.logger.info(f"⚠️ Employé {emp_data['nom']} ignoré - matricule manquant")
                continue
                
            # Email temporaire basé sur le matricule (plus fiable)
            temp_email = f"employe.{emp_data['matricule']}@temporaire.com"
            
            new_employee = Employee(
                matricule=emp_data['matricule'],
                nom_employe=emp_data['nom'],
                email=temp_email,
                statut='actif',
                source_creation=source
            )
            
            db.session.add(new_employee)
            added_count += 1
            app.logger.info(f"✅ Employé ajouté: {emp_data['nom']} (Matricule: {emp_data['matricule']})")
            
        except Exception as e:
            app.logger.error(f"❌ Erreur lors de l'ajout de {emp_data['nom']}: {str(e)}")
    
    try:
        db.session.commit()
        app.logger.info(f"💾 {added_count} nouveaux employés sauvegardés avec leur matricule")
        return added_count
    except Exception as e:
        db.session.rollback()
        app.logger.error(f"❌ Erreur lors de la sauvegarde: {str(e)}")
        return 0

def create_individual_pdf_with_period(pdf_reader, employee_name, page_numbers, matricule, period, employees_data, output_dir):
    """Version avec liens sécurisés au lieu d'emails directs"""
    
    try:
        # Création du PDF (inchangé)
        pdf_writer = PyPDF2.PdfWriter()
        for page_num in page_numbers:
            pdf_writer.add_page(pdf_reader.pages[page_num])
        
        # Nom de fichier avec période
        safe_filename = "".join(c for c in employee_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        if period:
            output_filename = f"{safe_filename}_{period}.pdf"
        else:
            current_period = datetime.now().strftime('%Y_%m')
            output_filename = f"{safe_filename}_{current_period}.pdf"
        
        output_path = os.path.join(output_dir, output_filename)
        
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)
        
        # 🆕 NOUVEAU : Logique avec liens sécurisés
        if matricule:
            employee_record = find_employee_by_matricule(matricule)
            
            if employee_record:
                # Protection avec matricule
                protect_pdf_with_password(output_path, matricule)
                app.logger.info(f"📄 PDF créé et protégé pour {employee_name}")
                app.logger.info(f"🔐 Matricule: {matricule}")
                app.logger.info(f"📁 Fichier: {output_filename}")
                
                # 🔗 NOUVEAU : Génération du lien sécurisé
                # Récupérer le traitement actuel (vous devrez passer cette info)
                current_traitement = get_current_traitement(output_dir)  # À implémenter
                
                if current_traitement:
                    download_link = generate_secure_download_link(
                        employee_record, 
                        current_traitement, 
                        output_path, 
                        matricule
                    )
                    
                    if download_link:
                        # 📧 Envoi email avec lien sécurisé
                        if send_email_with_secure_link(employee_name, employee_record.email, download_link):
                            app.logger.info(f"✅ Lien sécurisé envoyé à {employee_name}")
                            return True
                        else:
                            app.logger.error(f"❌ Erreur envoi lien pour {employee_name}")
                    else:
                        app.logger.error(f"❌ Erreur génération lien pour {employee_name}")
                else:
                    app.logger.error(f"❌ Traitement non trouvé pour {employee_name}")
            else:
                app.logger.error(f"⚠️ Matricule {matricule} non trouvé en base")
        
        # Fallback : PDF créé sans envoi
        app.logger.info(f"📄 PDF créé pour {employee_name} - pas d'envoi automatique")
        return True
        
    except Exception as e:
        app.logger.error(f"❌ Erreur création PDF pour {employee_name}: {str(e)}")
        return False

def get_current_traitement(output_dir):
    """Récupère le traitement actuel basé sur le dossier de sortie"""
    try:
        timestamp_folder = os.path.basename(output_dir)
        return Traitement.query.filter_by(timestamp_folder=timestamp_folder).first()
    except Exception as e:
        app.logger.error(f"❌ Erreur récupération traitement: {str(e)}")
        return None




def protect_pdf_with_password(filepath, password):
    """Protège un PDF avec un mot de passe"""
    try:
        # Solution 1: Utilisation du paramètre allow_overwriting_input=True
        with pikepdf.open(filepath, allow_overwriting_input=True) as pdf:
            pdf.save(filepath, encryption=pikepdf.Encryption(user=password, owner=password))
        app.logger.info(f"PDF protégé avec le mot de passe: {password}")
        
    except Exception as e:
        app.logger.error(f"Erreur lors de la protection du PDF: {str(e)}")
        
        # Solution alternative si la première ne fonctionne pas
        try:
            import shutil
            temp_path = filepath + ".temp"
            
            with pikepdf.open(filepath) as pdf:
                pdf.save(temp_path, encryption=pikepdf.Encryption(user=password, owner=password))
            
            # Remplace le fichier original par le fichier temporaire
            shutil.move(temp_path, filepath)
            app.logger.info(f"PDF protégé avec le mot de passe (méthode alternative): {password}")
            
        except Exception as e2:
            app.logger.error(f"Erreur lors de la protection alternative du PDF: {str(e2)}")

def generate_secure_download_link(employee_record, traitement, file_path, matricule):
    """Génère un lien de téléchargement sécurisé"""
    try:
        # Créer l'enregistrement du lien
        download_link = DownloadLink(
            employe_id=employee_record.id,
            traitement_id=traitement.id,
            nom_fichier=os.path.basename(file_path),
            chemin_fichier=file_path,
            matricule_requis=matricule,
            max_tentatives=10,  # Configurable
            date_expiration=datetime.utcnow() + timedelta(days=30)  # 30 jours
        )
        
        db.session.add(download_link)
        db.session.commit()
        
        app.logger.info(f"🔗 Lien sécurisé généré: {download_link.token[:8]}...")
        return download_link
        
    except Exception as e:
        app.logger.error(f"❌ Erreur génération lien: {str(e)}")
        db.session.rollback()
        return None

def send_email_with_secure_link(employee_name, email, download_link):
    """Envoie un email avec lien de téléchargement sécurisé"""
    try:
        from email_config import GMAIL_CONFIG
        
        # Configuration SMTP
        smtp_server = GMAIL_CONFIG['smtp_server']
        smtp_port = GMAIL_CONFIG['smtp_port']
        smtp_username = GMAIL_CONFIG['username']
        smtp_password = GMAIL_CONFIG['password']
        
        # URL de téléchargement
        download_url = f"https://91.160.69.7:5000/download/{download_link.token}"
        
        # Création du message
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email
        msg['Subject'] = f"Votre fiche de paie - {employee_name}"
        
        # Corps du message avec lien sécurisé
        body = f"""
Bonjour {employee_name},

Votre fiche de paie est disponible au téléchargement sécurisé.

🔗 Lien de téléchargement : {download_url}

🔐 Pour télécharger votre fiche :
1. Cliquez sur le lien ci-dessus
2. Saisissez votre matricule d'employé
3. Téléchargez votre fiche de paie

⏰ Ce lien expire dans {download_link.expires_in_days} jours
🛡️ Votre fiche est protégée par votre matricule

Pour toute question, contactez les ressources humaines.

Cordialement,
L'équipe RH
"""
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Envoi du message
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        text = msg.as_string()
        server.sendmail(smtp_username, email, text)
        server.quit()
        
        app.logger.info(f"📧 Email avec lien sécurisé envoyé à {employee_name}")
        return True
        
    except Exception as e:
        app.logger.error(f"❌ Erreur envoi email: {str(e)}")
        return False

    
@app.route('/download/<token>')
def secure_download_page(token):
    """Page de téléchargement sécurisé"""
    try:
        download_link = DownloadLink.query.filter_by(token=token).first()
        
        if not download_link:
            flash('Lien de téléchargement invalide ou expiré', 'error')
            return render_template('download_error.html', error="Lien invalide")
        
        if not download_link.is_valid:
            if download_link.tentatives_acces >= download_link.max_tentatives:
                error_msg = "Nombre maximum de tentatives dépassé"
            else:
                error_msg = "Lien expiré"
            
            flash(f'Accès refusé : {error_msg}', 'error')
            return render_template('download_error.html', error=error_msg)
        
        return render_template('secure_download.html', 
                             download_link=download_link,
                             employee=download_link.employee)
        
    except Exception as e:
        flash(f'Erreur lors de l\'accès au lien : {str(e)}', 'error')
        return render_template('download_error.html', error="Erreur système")

@app.route('/download/<token>/verify', methods=['POST'])
def verify_and_download(token):
    """Vérification du matricule et téléchargement"""
    try:
        download_link = DownloadLink.query.filter_by(token=token).first()
        
        if not download_link or not download_link.is_valid:
            flash('Lien invalide ou expiré', 'error')
            return redirect(url_for('secure_download_page', token=token))
        
        # Récupération du matricule saisi
        matricule_saisi = request.form.get('matricule', '').strip()
        
        # Incrémenter les tentatives
        download_link.tentatives_acces += 1
        download_link.date_dernier_acces = datetime.utcnow()
        download_link.adresse_ip_derniere = request.remote_addr
        
        # Vérification du matricule
        if matricule_saisi != download_link.matricule_requis:
            db.session.commit()
            remaining = download_link.max_tentatives - download_link.tentatives_acces
            flash(f'Matricule incorrect. {remaining} tentatives restantes.', 'error')
            return redirect(url_for('secure_download_page', token=token))
        
        # Matricule correct - autoriser le téléchargement
        download_link.nombre_telechargements += 1
        if not download_link.date_premier_acces:
            download_link.date_premier_acces = datetime.utcnow()
        
        db.session.commit()
        
        # Vérifier que le fichier existe
        if not os.path.exists(download_link.chemin_fichier):
            flash('Fichier non trouvé sur le serveur', 'error')
            return redirect(url_for('secure_download_page', token=token))
        
        app.logger.info(f"✅ Téléchargement autorisé: {download_link.employee.nom_employe}")
        
        return send_file(
            download_link.chemin_fichier,
            as_attachment=True,
            download_name=download_link.nom_fichier
        )
        
    except Exception as e:
        flash(f'Erreur lors du téléchargement : {str(e)}', 'error')
        return redirect(url_for('secure_download_page', token=token))


@app.route('/dashboard')
def dashboard():
    """Dashboard simplifié v1.2 - Sans graphiques"""
    try:
        # Statistiques v1.2 essentielles
        stats_v12 = get_v12_dashboard_stats()
        
        # Activité récente
        recent_activity = get_recent_activity()
        
        # Top employés (sans graphique)
        top_employees = get_employee_top_stats()
        
        # Derniers traitements (PostgreSQL prioritaire)
        treatments = get_treatments_from_db()
        if not treatments:
            treatments = get_treatments_from_filesystem()
            for treatment in treatments:
                treatment['source'] = 'Filesystem'
        
        # Limiter à 10 pour performance
        treatments = treatments[:10]
        
        return render_template('dashboard.html', 
                             stats_v12=stats_v12,
                             recent_activity=recent_activity,
                             top_employees=top_employees,
                             treatments=treatments)
        
    except Exception as e:
        flash(f'Erreur dashboard: {str(e)}', 'error')
        return redirect(url_for('index'))


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


def analyze_treatment_folder(folder_name, upload_path, output_path):
    """Analyse un dossier de traitement pour extraire les statistiques"""
    try:
        from datetime import datetime
        
        # Parse du timestamp
        timestamp_str = folder_name
        try:
            timestamp = datetime.strptime(timestamp_str, '%Y%m%d%H%M%S')
        except ValueError:
            return None
        
        # Fichier original
        original_files = [f for f in os.listdir(upload_path) if f.endswith('.pdf')]
        original_file = original_files[0] if original_files else 'Inconnu'
        
        # Dossier de sortie correspondant
        output_folder_path = os.path.join(output_path, folder_name)
        
        # Comptage des PDFs générés
        generated_files = []
        if os.path.exists(output_folder_path):
            generated_files = [f for f in os.listdir(output_folder_path) if f.endswith('.pdf')]
        
        # Calcul de la taille du fichier original
        original_file_path = os.path.join(upload_path, original_file)
        file_size = 0
        if os.path.exists(original_file_path):
            file_size = os.path.getsize(original_file_path)
        
        return {
            'timestamp': timestamp,
            'timestamp_str': timestamp_str,
            'date_formatted': timestamp.strftime('%d/%m/%Y à %H:%M:%S'),
            'original_file': original_file,
            'file_size': format_file_size(file_size),
            'employees_count': len(generated_files),
            'generated_files': generated_files,
            'status': 'Réussi' if generated_files else 'Échec'
        }
        
    except Exception as e:
        return None

def calculate_global_stats(treatments):
    """Calcule les statistiques globales"""
    if not treatments:
        return {
            'total_treatments': 0,
            'total_employees': 0,
            'total_files_generated': 0,
            'success_rate': 0,
            'last_treatment': None
        }
    
    successful_treatments = [t for t in treatments if t['status'] == 'Réussi']
    
    return {
        'total_treatments': len(treatments),
        'total_employees': sum(t['employees_count'] for t in treatments),
        'total_files_generated': sum(t['employees_count'] for t in successful_treatments),
        'success_rate': round(len(successful_treatments) / len(treatments) * 100, 1) if treatments else 0,
        'last_treatment': treatments[0]['date_formatted'] if treatments else None
    }

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

from flask import send_file

@app.route('/download/<timestamp>/<filename>')
def download_file(timestamp, filename):
    """Permet de télécharger un fichier PDF généré"""
    try:
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], timestamp, filename)
        
        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            flash('Fichier non trouvé', 'error')
            return redirect(url_for('dashboard'))
            
    except Exception as e:
        flash(f'Erreur lors du téléchargement: {str(e)}', 'error')
        return redirect(url_for('dashboard'))

@app.route('/cleanup')
def cleanup_files():
    """Nettoie les fichiers de plus de 30 jours"""
    try:
        from datetime import datetime, timedelta
        
        cutoff_date = datetime.now() - timedelta(days=30)
        deleted_folders = 0
        
        # Nettoyage des uploads
        if os.path.exists(app.config['UPLOAD_FOLDER']):
            for folder in os.listdir(app.config['UPLOAD_FOLDER']):
                try:
                    folder_date = datetime.strptime(folder, '%Y%m%d%H%M%S')
                    if folder_date < cutoff_date:
                        import shutil
                        shutil.rmtree(os.path.join(app.config['UPLOAD_FOLDER'], folder))
                        deleted_folders += 1
                except ValueError:
                    continue  # Ignore les dossiers qui ne correspondent pas au format
        
        # Nettoyage des outputs
        if os.path.exists(app.config['OUTPUT_FOLDER']):
            for folder in os.listdir(app.config['OUTPUT_FOLDER']):
                try:
                    folder_date = datetime.strptime(folder, '%Y%m%d%H%M%S')
                    if folder_date < cutoff_date:
                        import shutil
                        shutil.rmtree(os.path.join(app.config['OUTPUT_FOLDER'], folder))
                except ValueError:
                    continue
        
        flash(f'Nettoyage terminé ! {deleted_folders} dossier(s) supprimé(s) (+ de 30 jours)', 'success')
        return redirect(url_for('dashboard'))
        
    except Exception as e:
        flash(f'Erreur lors du nettoyage: {str(e)}', 'error')
        return redirect(url_for('dashboard'))
    
# Nouvelles fonctions pour dashboard PostgreSQL
def calculate_stats_from_db():
    """Calcule les statistiques depuis PostgreSQL"""
    try:
        total_treatments = Traitement.query.count()
        if total_treatments == 0:
            return {
                'total_treatments': 0,
                'total_employees': 0,
                'total_files_generated': 0,
                'success_rate': 0,
                'last_treatment': None
            }
        
        successful_treatments = Traitement.query.filter_by(statut='termine').all()
        total_employees = sum(t.nombre_employes_traites for t in Traitement.query.all())
        total_files = sum(t.nombre_employes_traites for t in successful_treatments)
        
        last_treatment = Traitement.query.order_by(Traitement.date_creation.desc()).first()
        
        return {
            'total_treatments': total_treatments,
            'total_employees': total_employees,
            'total_files_generated': total_files,
            'success_rate': round(len(successful_treatments) / total_treatments * 100, 1) if total_treatments > 0 else 0,
            'last_treatment': last_treatment.date_creation.strftime('%d/%m/%Y à %H:%M:%S') if last_treatment else None
        }
        
    except Exception as e:
        app.logger.error(f"❌ Erreur calcul stats DB: {str(e)}")
        return {
            'total_treatments': 0,
            'total_employees': 0,
            'total_files_generated': 0,
            'success_rate': 0,
            'last_treatment': None
        }

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
        app.logger.error(f"❌ Erreur récupération traitements DB: {str(e)}")
        return []


# Routes pour la gestion des employés
@app.route('/admin')
def admin_dashboard():
    """Dashboard administrateur"""
    return redirect(url_for('manage_employees'))

@app.route('/admin/employees')
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

@app.route('/admin/employees/add', methods=['GET', 'POST'])
def add_employee():
    """Ajouter un nouvel employé"""
    if request.method == 'POST':
        try:
            nom_employe = request.form.get('nom_employe', '').strip()
            email = request.form.get('email', '').strip()
            matricule = request.form.get('matricule', '').strip()
            
            # Validations
            if not nom_employe or not email:
                flash('Nom et email sont obligatoires', 'error')
                return render_template('admin/add_employee.html')
            
            # Vérifier unicité email
            if Employee.query.filter_by(email=email).first():
                flash('Un employé avec cet email existe déjà', 'error')
                return render_template('admin/add_employee.html')
            
            # Vérifier unicité matricule si fourni
            if matricule and Employee.query.filter_by(matricule=matricule).first():
                flash('Un employé avec ce matricule existe déjà', 'error')
                return render_template('admin/add_employee.html')
            
            # Création de l'employé
            new_employee = Employee(
                nom_employe=nom_employe,
                email=email,
                matricule=matricule if matricule else None,
                statut='actif',
                source_creation='manual'
            )
            
            db.session.add(new_employee)
            db.session.commit()
            
            flash(f'Employé {nom_employe} ajouté avec succès', 'success')
            return redirect(url_for('manage_employees'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erreur lors de l\'ajout : {str(e)}', 'error')
    
    return render_template('admin/add_employee.html')

@app.route('/admin/employees/<int:employee_id>/edit', methods=['GET', 'POST'])
def edit_employee(employee_id):
    """Modifier un employé existant avec restrictions selon la source"""
    employee = Employee.query.get_or_404(employee_id)
    
    if request.method == 'POST':
        try:
            # 🔒 Restrictions selon la source de création
            is_pdf_imported = employee.source_creation == 'pdf_import'
            
            if is_pdf_imported:
                # ✅ Employé PDF : Email + Statut modifiables seulement
                email = request.form.get('email', '').strip()
                statut = request.form.get('statut', 'actif')
                
                if not email:
                    flash('Email obligatoire', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Vérifier unicité email (sauf pour l'employé actuel)
                existing_email = Employee.query.filter(
                    Employee.email == email,
                    Employee.id != employee_id
                ).first()
                if existing_email:
                    flash('Un autre employé utilise déjà cet email', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Mise à jour email + statut seulement
                employee.email = email
                employee.statut = statut
                employee.date_derniere_maj = datetime.utcnow()
                
                db.session.commit()
                flash(f'Email et statut mis à jour pour {employee.nom_employe} (importé PDF)', 'success')
                
            else:
                # ✅ Employé manuel : Toutes modifications autorisées
                nom_employe = request.form.get('nom_employe', '').strip()
                email = request.form.get('email', '').strip()
                matricule = request.form.get('matricule', '').strip()
                statut = request.form.get('statut', 'actif')
                
                # Validations complètes
                if not nom_employe or not email:
                    flash('Nom et email sont obligatoires', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Vérifier unicité email
                existing_email = Employee.query.filter(
                    Employee.email == email,
                    Employee.id != employee_id
                ).first()
                if existing_email:
                    flash('Un autre employé utilise déjà cet email', 'error')
                    return render_template('admin/edit_employee.html', employee=employee)
                
                # Vérifier unicité matricule
                if matricule:
                    existing_matricule = Employee.query.filter(
                        Employee.matricule == matricule,
                        Employee.id != employee_id
                    ).first()
                    if existing_matricule:
                        flash('Un autre employé utilise déjà ce matricule', 'error')
                        return render_template('admin/edit_employee.html', employee=employee)
                
                # Mise à jour complète
                employee.nom_employe = nom_employe
                employee.email = email
                employee.matricule = matricule if matricule else None
                employee.statut = statut
                employee.date_derniere_maj = datetime.utcnow()
                
                db.session.commit()
                flash(f'Employé {nom_employe} modifié avec succès', 'success')
            
            return redirect(url_for('manage_employees'))
            
        except Exception as e:
            db.session.rollback()
            flash(f'Erreur lors de la modification : {str(e)}', 'error')
    
    return render_template('admin/edit_employee.html', employee=employee)

@app.route('/admin/employees/<int:employee_id>/delete', methods=['POST'])
def delete_employee(employee_id):
    """Supprimer un employé (soft delete)"""
    try:
        employee = Employee.query.get_or_404(employee_id)
        
        # Soft delete - changement de statut
        employee.statut = 'supprime'
        employee.date_derniere_maj = datetime.utcnow()
        
        db.session.commit()
        
        flash(f'Employé {employee.nom_employe} supprimé', 'success')
        
    except Exception as e:
        db.session.rollback()
        flash(f'Erreur lors de la suppression : {str(e)}', 'error')
    
    return redirect(url_for('manage_employees'))


@app.route('/admin/employees/export')
def export_employees():
    """Exporter la liste des employés en CSV"""
    try:
        import io
        import csv
        
        # Créer le CSV en mémoire
        output = io.StringIO()
        writer = csv.writer(output)
        
        # En-têtes
        writer.writerow(['Matricule', 'Nom', 'Email', 'Statut', 'Source', 'Date création'])
        
        # Données
        employees = Employee.query.order_by(Employee.nom_employe.asc()).all()
        for emp in employees:
            writer.writerow([
                emp.matricule or '',
                emp.nom_employe,
                emp.email,
                emp.statut,
                emp.source_creation,
                emp.date_creation.strftime('%d/%m/%Y %H:%M')
            ])
        
        # Préparation du téléchargement
        output.seek(0)
        
        from flask import make_response
        response = make_response(output.getvalue())
        response.headers['Content-Type'] = 'text/csv'
        response.headers['Content-Disposition'] = f'attachment; filename=employes_payflow_{datetime.now().strftime("%Y%m%d")}.csv'
        
        return response
        
    except Exception as e:
        flash(f'Erreur lors de l\'export : {str(e)}', 'error')
        return redirect(url_for('manage_employees'))

# Nouvelles fonctions pour dashboard enrichi v1.2
from sqlalchemy import func, and_, or_
from datetime import datetime, timedelta

def get_v12_dashboard_stats():
    """Statistiques complètes pour dashboard v1.2"""
    try:
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        last_7_days = now - timedelta(days=7)
        
        # Statistiques générales
        stats = {
            # Traitements
            'total_treatments': Traitement.query.count(),
            'treatments_last_30_days': Traitement.query.filter(Traitement.date_creation >= last_30_days).count(),
            'treatments_last_7_days': Traitement.query.filter(Traitement.date_creation >= last_7_days).count(),
            'successful_treatments': Traitement.query.filter_by(statut='termine').count(),
            'failed_treatments': Traitement.query.filter_by(statut='echec').count(),
            
            # Employés
            'total_employees': Employee.query.count(),
            'active_employees': Employee.query.filter_by(statut='actif').count(),
            'pdf_imported_employees': Employee.query.filter_by(source_creation='pdf_import').count(),
            'manual_employees': Employee.query.filter_by(source_creation='manual').count(),
            
            # Liens de téléchargement
            'total_download_links': DownloadLink.query.count(),
            'active_links': DownloadLink.query.filter_by(statut='actif').count(),
            'expired_links': DownloadLink.query.filter(DownloadLink.date_expiration < now).count(),
            'total_downloads': db.session.query(func.sum(DownloadLink.nombre_telechargements)).scalar() or 0,
            
            # Sécurité
            'blocked_attempts': DownloadLink.query.filter(DownloadLink.tentatives_acces >= DownloadLink.max_tentatives).count(),
            'links_with_attempts': DownloadLink.query.filter(DownloadLink.tentatives_acces > 0).count(),
        }
        
        # Calculs dérivés
        stats['success_rate'] = round(
            (stats['successful_treatments'] / stats['total_treatments'] * 100) if stats['total_treatments'] > 0 else 0, 1
        )
        
        stats['security_rate'] = round(
            ((stats['active_links'] - stats['blocked_attempts']) / stats['active_links'] * 100) if stats['active_links'] > 0 else 100, 1
        )
        
        return stats
        
    except Exception as e:
        app.logger.error(f"❌ Erreur calcul stats v1.2: {str(e)}")
        return {}

def get_treatment_activity_chart():
    """Données pour graphique d'activité des traitements (30 derniers jours)"""
    try:
        now = datetime.utcnow()
        last_30_days = now - timedelta(days=30)
        
        # Traitements par jour
        daily_treatments = db.session.query(
            func.date(Traitement.date_creation).label('date'),
            func.count(Traitement.id).label('count')
        ).filter(
            Traitement.date_creation >= last_30_days
        ).group_by(
            func.date(Traitement.date_creation)
        ).order_by('date').all()
        
        # Formatage pour Chart.js
        labels = []
        data = []
        
        for treatment in daily_treatments:
            labels.append(treatment.date.strftime('%d/%m'))
            data.append(treatment.count)
        
        return {
            'labels': labels,
            'data': data
        }
        
    except Exception as e:
        app.logger.error(f"❌ Erreur graphique activité: {str(e)}")
        return {'labels': [], 'data': []}

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
        app.logger.error(f"❌ Erreur top employés: {str(e)}")
        return []

def get_download_security_stats():
    """Statistiques de sécurité des téléchargements"""
    try:
        # Répartition des tentatives d'accès
        security_data = db.session.query(
            DownloadLink.tentatives_acces.label('attempts'),
            func.count(DownloadLink.id).label('count')
        ).group_by(
            DownloadLink.tentatives_acces
        ).order_by('attempts').all()
        
        return [
            {
                'attempts': data.attempts,
                'count': data.count,
                'status': 'success' if data.attempts == 0 else ('warning' if data.attempts < 5 else 'danger')
            }
            for data in security_data
        ]
        
    except Exception as e:
        app.logger.error(f"❌ Erreur stats sécurité: {str(e)}")
        return []

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
        app.logger.error(f"❌ Erreur activité récente: {str(e)}")
        return {'treatments': [], 'downloads': []}

# Routes de maintenance système
@app.route('/admin/maintenance')
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

@app.route('/admin/maintenance/cleanup', methods=['POST'])
def execute_cleanup():
    """Exécute le nettoyage système"""
    try:
        cleanup_type = request.form.get('cleanup_type', 'all')
        confirm = request.form.get('confirm', '') == 'true'
        
        if not confirm:
            flash('Veuillez confirmer l\'opération de nettoyage', 'error')
            return redirect(url_for('maintenance_page'))
        
        results = perform_system_cleanup(cleanup_type)
        
        if results['success']:
            flash(f'Nettoyage réussi: {results["message"]}', 'success')
        else:
            flash(f'Erreur nettoyage: {results["error"]}', 'error')
            
    except Exception as e:
        flash(f'Erreur lors du nettoyage: {str(e)}', 'error')
    
    return redirect(url_for('maintenance_page'))

@app.route('/admin/maintenance/backup', methods=['POST'])
def create_backup():
    """Crée une sauvegarde de la base de données"""
    try:
        backup_result = create_database_backup()
        
        if backup_result['success']:
            flash(f'Sauvegarde créée: {backup_result["filename"]}', 'success')
        else:
            flash(f'Erreur sauvegarde: {backup_result["error"]}', 'error')
            
    except Exception as e:
        flash(f'Erreur lors de la sauvegarde: {str(e)}', 'error')
    
    return redirect(url_for('maintenance_page'))

@app.route('/admin/maintenance/optimize', methods=['POST'])
def optimize_database():
    """Optimise la base de données"""
    try:
        optimize_result = perform_database_optimization()
        
        if optimize_result['success']:
            flash(f'Optimisation réussie: {optimize_result["message"]}', 'success')
        else:
            flash(f'Erreur optimisation: {optimize_result["error"]}', 'error')
            
    except Exception as e:
        flash(f'Erreur lors de l\'optimisation: {str(e)}', 'error')
    
    return redirect(url_for('maintenance_page'))

# Fonctions de maintenance
def get_maintenance_stats():
    """Collecte les statistiques de maintenance"""
    try:
        now = datetime.utcnow()
        
        # Liens expirés
        expired_links = DownloadLink.query.filter(
            DownloadLink.date_expiration < now
        ).count()
        
        # Fichiers anciens (plus de 30 jours)
        old_files_info = analyze_old_files()
        
        # Taille des dossiers
        uploads_size = get_folder_size('uploads')
        output_size = get_folder_size('output')
        
        # Statistiques base de données
        db_stats = get_database_stats()
        
        return {
            'expired_links': expired_links,
            'old_files_count': old_files_info['count'],
            'old_files_size': old_files_info['size'],
            'uploads_size': uploads_size,
            'output_size': output_size,
            'total_size': uploads_size + output_size,
            'db_stats': db_stats,
            'last_cleanup': get_last_cleanup_date(),
            'system_health': calculate_system_health()
        }
        
    except Exception as e:
        app.logger.error(f"❌ Erreur stats maintenance: {str(e)}")
        return {}

def analyze_old_files():
    """Analyse les fichiers anciens"""
    try:
        now = datetime.utcnow()
        cutoff_date = now - timedelta(days=30)
        
        old_count = 0
        total_size = 0
        
        for folder in ['uploads', 'output']:
            if os.path.exists(folder):
                for subfolder in os.listdir(folder):
                    subfolder_path = os.path.join(folder, subfolder)
                    if os.path.isdir(subfolder_path):
                        try:
                            # Parse la date du dossier (format: YYYYMMDDHHMMSS)
                            if len(subfolder) == 14 and subfolder.isdigit():
                                folder_date = datetime.strptime(subfolder, '%Y%m%d%H%M%S')
                                if folder_date < cutoff_date:
                                    old_count += 1
                                    total_size += get_folder_size(subfolder_path)
                        except ValueError:
                            continue
        
        return {
            'count': old_count,
            'size': total_size
        }
        
    except Exception as e:
        app.logger.error(f"❌ Erreur analyse fichiers anciens: {str(e)}")
        return {'count': 0, 'size': 0}

def get_folder_size(folder_path):
    """Calcule la taille d'un dossier en bytes"""
    try:
        total_size = 0
        if os.path.exists(folder_path):
            for dirpath, dirnames, filenames in os.walk(folder_path):
                for filename in filenames:
                    file_path = os.path.join(dirpath, filename)
                    if os.path.exists(file_path):
                        total_size += os.path.getsize(file_path)
        return total_size
    except Exception:
        return 0

def format_file_size(size_bytes):
    """Formate la taille en format lisible"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB", "TB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"

def perform_system_cleanup(cleanup_type='all'):
    """Effectue le nettoyage système"""
    try:
        results = {
            'expired_links_removed': 0,
            'old_files_removed': 0,
            'space_freed': 0
        }
        
        if cleanup_type in ['all', 'links']:
            # Nettoyer les liens expirés
            expired_links = DownloadLink.query.filter(
                DownloadLink.date_expiration < datetime.utcnow()
            ).all()
            
            for link in expired_links:
                db.session.delete(link)
                results['expired_links_removed'] += 1
            
            db.session.commit()
        
        if cleanup_type in ['all', 'files']:
            # Nettoyer les fichiers anciens
            cutoff_date = datetime.utcnow() - timedelta(days=30)
            
            for folder in ['uploads', 'output']:
                if os.path.exists(folder):
                    for subfolder in os.listdir(folder):
                        subfolder_path = os.path.join(folder, subfolder)
                        if os.path.isdir(subfolder_path):
                            try:
                                if len(subfolder) == 14 and subfolder.isdigit():
                                    folder_date = datetime.strptime(subfolder, '%Y%m%d%H%M%S')
                                    if folder_date < cutoff_date:
                                        folder_size = get_folder_size(subfolder_path)
                                        import shutil
                                        shutil.rmtree(subfolder_path)
                                        results['old_files_removed'] += 1
                                        results['space_freed'] += folder_size
                            except (ValueError, OSError):
                                continue
        
        # Enregistrer la date de nettoyage
        save_cleanup_date()
        
        message = f"{results['expired_links_removed']} liens expirés, {results['old_files_removed']} dossiers anciens supprimés, {format_file_size(results['space_freed'])} d'espace libéré"
        
        return {
            'success': True,
            'message': message,
            'details': results
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def get_database_stats():
    """Statistiques de la base de données"""
    try:
        return {
            'employees_count': Employee.query.count(),
            'treatments_count': Traitement.query.count(),
            'treatment_employees_count': TraitementEmploye.query.count(),
            'download_links_count': DownloadLink.query.count()
        }
    except Exception:
        return {}

def calculate_system_health():
    """Calcule l'état de santé du système"""
    try:
        # Critères de santé
        health_score = 100
        issues = []
        
        # Vérifier les liens expirés
        expired_links = DownloadLink.query.filter(
            DownloadLink.date_expiration < datetime.utcnow()
        ).count()
        
        if expired_links > 50:
            health_score -= 20
            issues.append(f"{expired_links} liens expirés")
        elif expired_links > 10:
            health_score -= 10
            issues.append(f"{expired_links} liens expirés")
        
        # Vérifier l'espace disque
        total_size = get_folder_size('uploads') + get_folder_size('output')
        if total_size > 1024 * 1024 * 1024:  # > 1GB
            health_score -= 15
            issues.append("Espace disque élevé")
        
        # Vérifier les tentatives bloquées
        blocked_attempts = DownloadLink.query.filter(
            DownloadLink.tentatives_acces >= DownloadLink.max_tentatives
        ).count()
        
        if blocked_attempts > 5:
            health_score -= 10
            issues.append(f"{blocked_attempts} accès bloqués")
        
        return {
            'score': max(0, health_score),
            'status': 'excellent' if health_score >= 90 else ('good' if health_score >= 70 else ('warning' if health_score >= 50 else 'critical')),
            'issues': issues
        }
        
    except Exception:
        return {'score': 0, 'status': 'unknown', 'issues': ['Erreur de calcul']}

def get_last_cleanup_date():
    """Récupère la date du dernier nettoyage"""
    try:
        cleanup_file = 'last_cleanup.txt'
        if os.path.exists(cleanup_file):
            with open(cleanup_file, 'r') as f:
                date_str = f.read().strip()
                return datetime.fromisoformat(date_str)
    except Exception:
        pass
    return None

def save_cleanup_date():
    """Sauvegarde la date du nettoyage"""
    try:
        with open('last_cleanup.txt', 'w') as f:
            f.write(datetime.utcnow().isoformat())
    except Exception:
        pass

def create_database_backup():
    """Crée une sauvegarde de la base PostgreSQL"""
    try:
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"payflow_backup_{timestamp}.sql"
        
        # Commande pg_dump
        import subprocess
        cmd = [
            'pg_dump',
            '-h', 'localhost',
            '-U', 'payflow_user',
            '-d', 'payflow_db',
            '-f', filename
        ]
        
        result = subprocess.run(cmd, capture_output=True, text=True)
        
        if result.returncode == 0:
            return {
                'success': True,
                'filename': filename
            }
        else:
            return {
                'success': False,
                'error': result.stderr or 'Erreur pg_dump'
            }
            
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

def perform_database_optimization():
    """Optimise la base de données"""
    try:
        # Commandes d'optimisation PostgreSQL
        db.session.execute('VACUUM ANALYZE;')
        db.session.commit()
        
        return {
            'success': True,
            'message': 'Base de données optimisée (VACUUM ANALYZE effectué)'
        }
        
    except Exception as e:
        return {
            'success': False,
            'error': str(e)
        }

# Routes pour détails des traitements
@app.route('/admin/treatment/<timestamp>/details')
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
                    
                    generated_files.append({
                        'filename': filename,
                        'employee_name': employee_name,
                        'file_size': format_file_size(file_size),
                        'file_path': file_path
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

@app.route('/admin/treatment/<timestamp>/download/<filename>')
def download_generated_pdf(timestamp, filename):
    """Télécharge un PDF généré spécifique"""
    try:
        # Vérifier que le traitement existe
        traitement = Traitement.query.filter_by(timestamp_folder=timestamp).first()
        if not traitement:
            flash('Traitement non trouvé', 'error')
            return redirect(url_for('dashboard'))
        
        # Construire le chemin du fichier
        file_path = os.path.join(app.config['OUTPUT_FOLDER'], timestamp, filename)
        
        if not os.path.exists(file_path):
            flash('Fichier non trouvé', 'error')
            return redirect(url_for('treatment_details', timestamp=timestamp))
        
        # Téléchargement sécurisé
        return send_file(file_path, as_attachment=True, download_name=filename)
        
    except Exception as e:
        flash(f'Erreur lors du téléchargement : {str(e)}', 'error')
        return redirect(url_for('treatment_details', timestamp=timestamp))

@app.route('/admin/treatment/<timestamp>/download-all')
def download_all_generated_pdfs(timestamp):
    """Télécharge tous les PDFs générés d'un traitement en ZIP"""
    try:
        import zipfile
        import io
        
        # Vérifier que le traitement existe
        traitement = Traitement.query.filter_by(timestamp_folder=timestamp).first()
        if not traitement:
            flash('Traitement non trouvé', 'error')
            return redirect(url_for('dashboard'))
        
        # Dossier des fichiers générés
        output_folder = os.path.join(app.config['OUTPUT_FOLDER'], timestamp)
        if not os.path.exists(output_folder):
            flash('Dossier de fichiers non trouvé', 'error')
            return redirect(url_for('treatment_details', timestamp=timestamp))
        
        # Créer le ZIP en mémoire
        zip_buffer = io.BytesIO()
        
        with zipfile.ZipFile(zip_buffer, 'w', zipfile.ZIP_DEFLATED) as zip_file:
            # Ajouter tous les PDFs au ZIP
            pdf_count = 0
            for filename in os.listdir(output_folder):
                if filename.endswith('.pdf'):
                    file_path = os.path.join(output_folder, filename)
                    zip_file.write(file_path, filename)
                    pdf_count += 1
        
        if pdf_count == 0:
            flash('Aucun PDF trouvé dans ce traitement', 'error')
            return redirect(url_for('treatment_details', timestamp=timestamp))
        
        zip_buffer.seek(0)
        
        # Nom du fichier ZIP
        zip_filename = f"payflow_fiches_{timestamp}_{pdf_count}files.zip"
        
        return send_file(
            zip_buffer,
            mimetype='application/zip',
            as_attachment=True,
            download_name=zip_filename
        )
        
    except Exception as e:
        flash(f'Erreur lors de la création du ZIP : {str(e)}', 'error')
        return redirect(url_for('treatment_details', timestamp=timestamp))

def format_file_size(size_bytes):
    """Formate la taille de fichier en format lisible"""
    if size_bytes == 0:
        return "0 B"
    size_names = ["B", "KB", "MB", "GB"]
    i = 0
    while size_bytes >= 1024 and i < len(size_names) - 1:
        size_bytes /= 1024.0
        i += 1
    return f"{size_bytes:.1f} {size_names[i]}"


@app.route('/admin/logs')
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
        app.logger.error(f"❌ Erreur consultation logs: {str(e)}")
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

# Démarrage de l'application
if __name__ == '__main__':
    # Création des dossiers
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)

    # Certificats mkcert
    cert_file = '192.168.1.55+2.pem'
    key_file = '192.168.1.55+2-key.pem'

    print("🔒 PayFlow v1.2 - HTTPS sécurisé")
    print("🌐 Accès : https://192.168.1.55:5000")

    app.run(
        host='0.0.0.0',
        port=5000,
        debug=False,
        threaded=True,
        ssl_context=(cert_file, key_file)
    )



