from flask import Flask, render_template, request, redirect, url_for, flash
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
from datetime import datetime
import threading
import time
from flask import jsonify
import json
import os
from flask import Flask, render_template, request, redirect, url_for, flash, jsonify

# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False



app = Flask(__name__)
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
    print(f"\n--- Contenu de la page {page_num + 1} ---")
    for i, line in enumerate(lines[:20]):  # Affiche les 20 premières lignes
        line = line.strip()
        if line:  # Ignore les lignes vides
            print(f"Ligne {i+1}: '{line}'")
    print("--- Fin du contenu ---\n")

def allowed_file(filename):
    """Vérifie si le fichier est un PDF"""
    return '.' in filename and filename.rsplit('.', 1)[1].lower() in ALLOWED_EXTENSIONS

def load_employees():
    """Charge les données des employés depuis le CSV (nom et email seulement)"""
    employees = {}
    try:
        with open('employees.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                employees[row['nom_employe']] = {
                    'email': row['email']
                }
    except FileNotFoundError:
        flash('Fichier employees.csv non trouvé', 'error')
    return employees


@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])  # IMPORTANT: Cette ligne doit être exactement comme ça
def upload_file():
    """Traite le fichier PDF uploadé avec débogage"""
    # DÉBOGAGE - à supprimer après test
    print("=== DÉBOGAGE ===")
    print(f"request.method: {request.method}")
    print(f"request.files: {request.files}")
    print(f"'file' in request.files: {'file' in request.files}")
    if 'file' in request.files:
        print(f"Nom du fichier: {request.files['file'].filename}")
    print("===============")

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
                
                print(f"📁 Fichier sauvegardé dans : {upload_timestamp_dir}")
                print(f"📁 Fichiers de sortie iront dans : {output_timestamp_dir}")
                
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
            print(f"📄 PDF créé et protégé pour {employee_name} avec matricule {matricule} (extrait du PDF)")
            
            # APPEL CORRIGÉ : Seulement 3 paramètres, SANS le matricule
            if send_email_with_pdf(employee_name, email, output_path):
                print(f"✅ Processus complet réussi pour {employee_name}")
            else:
                print(f"❌ Erreur lors de l'envoi pour {employee_name}")
                
        elif employee_name in employees_data and not matricule:
            print(f"⚠️ Employé {employee_name} trouvé mais matricule non détecté - PDF créé sans protection")
            
        else:
            print(f"📄 PDF créé SANS protection pour {employee_name} (non trouvé dans employees.csv)")
        
        return True
        
    except Exception as e:
        print(f"Erreur lors de la création du PDF pour {employee_name}: {str(e)}")
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
    print("⚠️ Aucune période trouvée dans le PDF, utilisation de la date actuelle")
    return now.strftime('%Y_%m')


def process_pdf(filepath, output_dir):
    """Fonction principale de traitement du PDF avec extraction du matricule et de la période"""
    try:
        employees = load_employees()
        employee_data = {}  # Dictionnaire pour stocker nom, pages, matricule ET période
        
        # Ouverture du PDF
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            print(f"Analyse du PDF avec {total_pages} pages...")
            
            # Analyse de chaque page pour identifier les employés, matricules et période
            for page_num in range(total_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                
                # Extraction des informations
                employee_name = extract_employee_name_from_page(page_text)
                employee_matricule = extract_employee_matricule_from_page(page_text)
                period = extract_period_from_page(page_text)
                
                if employee_name:
                    print(f"Page {page_num + 1}: Employé trouvé - {employee_name}")
                    if employee_matricule:
                        print(f"Page {page_num + 1}: Matricule trouvé - {employee_matricule}")
                    if period:
                        print(f"Page {page_num + 1}: Période trouvée - {period}")
                    
                    # Groupement des pages par employé avec toutes les infos
                    if employee_name not in employee_data:
                        employee_data[employee_name] = {
                            'pages': [],
                            'matricule': employee_matricule,
                            'period': period
                        }
                    else:
                        # Si l'employé existe déjà, conserver les infos de la première page
                        if not employee_data[employee_name]['matricule'] and employee_matricule:
                            employee_data[employee_name]['matricule'] = employee_matricule
                        if not employee_data[employee_name]['period'] and period:
                            employee_data[employee_name]['period'] = period
                    
                    employee_data[employee_name]['pages'].append(page_num)
                else:
                    print(f"Page {page_num + 1}: Aucun employé identifié")
            
            # Création des PDF individuels avec période du bulletin
            processed_count = 0
            for employee_name, data in employee_data.items():
                if create_individual_pdf_with_period(
                    pdf_reader, 
                    employee_name, 
                    data['pages'], 
                    data['matricule'], 
                    data['period'],
                    employees, 
                    output_dir
                ):
                    processed_count += 1
                    
            return {
                'success': True,
                'count': processed_count,
                'total_employees': len(employee_data),
                'message': f'{processed_count} fiches traitées sur {len(employee_data)} employés détectés'
            }
            
    except Exception as e:
        print(f"Erreur lors du traitement: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }


def create_individual_pdf_with_period(pdf_reader, employee_name, page_numbers, matricule, period, employees_data, output_dir):
    """Crée un PDF individuel avec suffixe période extrait du PDF"""
    try:
        # Création du PDF de sortie
        pdf_writer = PyPDF2.PdfWriter()
        
        # Ajout des pages de l'employé
        for page_num in page_numbers:
            pdf_writer.add_page(pdf_reader.pages[page_num])
        
        # Nom du fichier de sortie avec période du bulletin
        safe_filename = "".join(c for c in employee_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        
        # Utilisation de la période extraite ou date actuelle si non trouvée
        if period:
            output_filename = f"{safe_filename}_{period}.pdf"
        else:
            from datetime import datetime
            now = datetime.now()
            current_period = now.strftime('%Y_%m')
            output_filename = f"{safe_filename}_{current_period}.pdf"
        
        output_path = os.path.join(output_dir, output_filename)
        
        # Sauvegarde du PDF
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)
        
        # Protection et envoi si l'employé est dans la base ET matricule trouvé
        if employee_name in employees_data and matricule:
            email = employees_data[employee_name]['email']
            
            # Protection du PDF avec le matricule extrait du PDF
            protect_pdf_with_password(output_path, matricule)
            print(f"📄 PDF créé et protégé pour {employee_name}")
            print(f"🔐 Matricule : {matricule} (extrait du PDF)")
            print(f"📅 Période : {period if period else 'date actuelle'}")
            print(f"📁 Fichier : {output_filename}")
            
            # Envoi par email SANS révéler le matricule
            if send_email_with_pdf(employee_name, email, output_path):
                print(f"✅ Processus complet réussi pour {employee_name}")
            else:
                print(f"❌ Erreur lors de l'envoi pour {employee_name}")
                
        elif employee_name in employees_data and not matricule:
            print(f"⚠️ Employé {employee_name} trouvé mais matricule non détecté")
            print(f"📁 PDF créé sans protection : {output_filename}")
            
        else:
            print(f"📄 PDF créé SANS protection pour {employee_name} (non trouvé dans employees.csv)")
            print(f"📁 Fichier : {output_filename}")
        
        return True
        
    except Exception as e:
        print(f"Erreur lors de la création du PDF pour {employee_name}: {str(e)}")
        return False



def protect_pdf_with_password(filepath, password):
    """Protège un PDF avec un mot de passe"""
    try:
        # Solution 1: Utilisation du paramètre allow_overwriting_input=True
        with pikepdf.open(filepath, allow_overwriting_input=True) as pdf:
            pdf.save(filepath, encryption=pikepdf.Encryption(user=password, owner=password))
        print(f"PDF protégé avec le mot de passe: {password}")
        
    except Exception as e:
        print(f"Erreur lors de la protection du PDF: {str(e)}")
        
        # Solution alternative si la première ne fonctionne pas
        try:
            import shutil
            temp_path = filepath + ".temp"
            
            with pikepdf.open(filepath) as pdf:
                pdf.save(temp_path, encryption=pikepdf.Encryption(user=password, owner=password))
            
            # Remplace le fichier original par le fichier temporaire
            shutil.move(temp_path, filepath)
            print(f"PDF protégé avec le mot de passe (méthode alternative): {password}")
            
        except Exception as e2:
            print(f"Erreur lors de la protection alternative du PDF: {str(e2)}")

def send_email_with_pdf(employee_name, email, pdf_path):
    """Envoie la fiche de paie par email à l'employé"""
    try:
        # Utilisation de la configuration externe
        smtp_server = GMAIL_CONFIG['smtp_server']
        smtp_port = GMAIL_CONFIG['smtp_port']
        smtp_username = GMAIL_CONFIG['username']
        smtp_password = GMAIL_CONFIG['password']
        
        # Création du message
        msg = MIMEMultipart()
        msg['From'] = smtp_username
        msg['To'] = email
        msg['Subject'] = f"Votre fiche de paie - {employee_name}"
        
        # Corps du message
        body = f"""
Bonjour {employee_name},

Veuillez trouver ci-joint votre fiche de paie.

Le fichier PDF est protégé par un mot de passe. 
Pour l'ouvrir, utilisez votre matricule d'employé.

Cordialement,
L'équipe RH 
        """
        
        msg.attach(MIMEText(body, 'plain'))
        
        # Pièce jointe
        with open(pdf_path, "rb") as attachment:
            part = MIMEBase('application', 'octet-stream')
            part.set_payload(attachment.read())
        
        encoders.encode_base64(part)
        part.add_header(
            'Content-Disposition',
            f'attachment; filename= {os.path.basename(pdf_path)}'
        )
        
        msg.attach(part)
        
        # Envoi du message
        server = smtplib.SMTP(smtp_server, smtp_port)
        server.starttls()
        server.login(smtp_username, smtp_password)
        text = msg.as_string()
        server.sendmail(smtp_username, email, text)
        server.quit()
        
        print(f"Email envoyé avec succès à {employee_name} ({email})")
        return True
        
    except Exception as e:
        print(f"Erreur lors de l'envoi de l'email à {employee_name}: {str(e)}")
        return False
@app.route('/dashboard')
def dashboard():
    """Dashboard avec historique des traitements"""
    try:
        # Collecte des dossiers de traitements
        uploads_path = app.config['UPLOAD_FOLDER']
        output_path = app.config['OUTPUT_FOLDER']
        
        treatments = []
        
        # Parcours des dossiers horodatés
        if os.path.exists(uploads_path):
            for folder in os.listdir(uploads_path):
                folder_path = os.path.join(uploads_path, folder)
                if os.path.isdir(folder_path):
                    # Information sur le traitement
                    treatment_info = analyze_treatment_folder(folder, folder_path, output_path)
                    if treatment_info:
                        treatments.append(treatment_info)
        
        # Tri par date décroissante
        treatments.sort(key=lambda x: x['timestamp'], reverse=True)
        
        # Statistiques globales
        stats = calculate_global_stats(treatments)
        
        return render_template('dashboard.html', treatments=treatments, stats=stats)
        
    except Exception as e:
        flash(f'Erreur lors du chargement du dashboard: {str(e)}', 'error')
        return redirect(url_for('index'))

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


if __name__ == '__main__':
    # Création des dossiers s'ils n'existent pas
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    app.run(debug=True)

