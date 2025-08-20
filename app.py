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

app = Flask(__name__)
app.secret_key = 'your-secret-key-change-this'  # À changer en production

# Configuration des dossiers
UPLOAD_FOLDER = 'uploads'
OUTPUT_FOLDER = 'output'
ALLOWED_EXTENSIONS = {'pdf'}

app.config['UPLOAD_FOLDER'] = UPLOAD_FOLDER
app.config['OUTPUT_FOLDER'] = OUTPUT_FOLDER

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
    """Charge les données des employés depuis le CSV"""
    employees = {}
    try:
        with open('employees.csv', 'r', encoding='utf-8') as file:
            reader = csv.DictReader(file)
            for row in reader:
                employees[row['nom_employe']] = {
                    'email': row['email'],
                    'mot_de_passe': row['mot_de_passe']
                }
    except FileNotFoundError:
        flash('Fichier employees.csv non trouvé', 'error')
    return employees

@app.route('/')
def index():
    """Page d'accueil avec formulaire d'upload"""
    return render_template('index.html')

@app.route('/upload', methods=['POST'])
def upload_file():
    """Traite le fichier PDF uploadé"""
    if 'file' not in request.files:
        flash('Aucun fichier sélectionné', 'error')
        return redirect(request.url)
    
    file = request.files['file']
    if file.filename == '':
        flash('Aucun fichier sélectionné', 'error')
        return redirect(request.url)
    
    if file and allowed_file(file.filename):
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config['UPLOAD_FOLDER'], filename)
        file.save(filepath)
        
        # Traitement du PDF
        result = process_pdf(filepath)
        
        if result['success']:
            flash(f'Traitement réussi ! {result["count"]} fiches traitées.', 'success')
        else:
            flash(f'Erreur lors du traitement: {result["error"]}', 'error')
        
        return redirect(url_for('index'))
    else:
        flash('Format de fichier non autorisé. Utilisez un PDF.', 'error')
        return redirect(request.url)

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



def process_pdf(filepath):
    """Fonction principale de traitement du PDF"""
    try:
        employees = load_employees()
        employee_pages = {}  # Dictionnaire pour grouper les pages par employé
        
        # Ouverture du PDF
        with open(filepath, 'rb') as file:
            pdf_reader = PyPDF2.PdfReader(file)
            total_pages = len(pdf_reader.pages)
            
            print(f"Analyse du PDF avec {total_pages} pages...")
            
            # Analyse de chaque page pour identifier les employés
            for page_num in range(total_pages):
                page = pdf_reader.pages[page_num]
                page_text = page.extract_text()
                
                # Extraction du nom de l'employé
                employee_name = extract_employee_name_from_page(page_text)
                
                if employee_name:
                    print(f"Page {page_num + 1}: Employé trouvé - {employee_name}")
                    
                    # Groupement des pages par employé
                    if employee_name not in employee_pages:
                        employee_pages[employee_name] = []
                    employee_pages[employee_name].append(page_num)
                else:
                    print(f"Page {page_num + 1}: Aucun employé identifié")


            
            # Création des PDF individuels
            processed_count = 0
            for employee_name, pages in employee_pages.items():
                if create_individual_pdf(pdf_reader, employee_name, pages, employees):
                    processed_count += 1
                    
            return {
                'success': True,
                'count': processed_count,
                'total_employees': len(employee_pages),
                'message': f'{processed_count} fiches traitées sur {len(employee_pages)} employés détectés'
            }
            
    except Exception as e:
        print(f"Erreur lors du traitement: {str(e)}")
        return {
            'success': False,
            'error': str(e)
        }

def create_individual_pdf(pdf_reader, employee_name, page_numbers, employees_data):
    """Crée un PDF individuel pour un employé"""
    try:
        # Création du PDF de sortie
        pdf_writer = PyPDF2.PdfWriter()
        
        # Ajout des pages de l'employé
        for page_num in page_numbers:
            pdf_writer.add_page(pdf_reader.pages[page_num])
        
        # Nom du fichier de sortie
        safe_filename = "".join(c for c in employee_name if c.isalnum() or c in (' ', '-', '_')).rstrip()
        output_filename = f"{safe_filename}.pdf"
        output_path = os.path.join(app.config['OUTPUT_FOLDER'], output_filename)
        
        # Sauvegarde du PDF
        with open(output_path, 'wb') as output_file:
            pdf_writer.write(output_file)
        
        # Protection par mot de passe et envoi d'email si l'employé est dans la base
        if employee_name in employees_data:
            password = employees_data[employee_name]['mot_de_passe']
            email = employees_data[employee_name]['email']
            
            # Protection du PDF
            protect_pdf_with_password(output_path, password)
            print(f"PDF créé et protégé pour {employee_name}")
            
            # Envoi par email
            if send_email_with_pdf(employee_name, email, output_path, password):
                print(f"Processus complet réussi pour {employee_name}")
            else:
                print(f"Erreur lors de l'envoi pour {employee_name}")
        else:
            print(f"PDF créé SANS protection pour {employee_name} (non trouvé dans employees.csv)")
        
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

def send_email_with_pdf(employee_name, email, pdf_path, password):
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

Le fichier est protégé par mot de passe : {password}

Cordialement,
L'équipe PayFlow
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


if __name__ == '__main__':
    # Création des dossiers s'ils n'existent pas
    os.makedirs(UPLOAD_FOLDER, exist_ok=True)
    os.makedirs(OUTPUT_FOLDER, exist_ok=True)
    
    app.run(debug=True)

