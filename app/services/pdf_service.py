
from flask import  flash
import os
import PyPDF2
from datetime import datetime
import threading
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.base import MIMEBase
from email import encoders
from email.mime.text import MIMEText
from email_config import GMAIL_CONFIG

from app.model.models import db, Employee, Traitement, TraitementEmploye
from app.services.employee_service import load_employees, add_employees_to_database, find_employee_by_matricule
from app.services.link_service import generate_secure_download_link
from app.services.treatment_service import get_current_traitement   
# Variable pour empêcher les traitements multiples
processing_lock = threading.Lock()
is_processing = False


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



def send_email_with_secure_link(employee_name, email, download_link, app):
    with app.app_context():
        """Envoie un email avec lien de téléchargement sécurisé"""
        try:
            # Accéder aux attributs IMMÉDIATEMENT
            token = download_link.token
            expires_in_days = download_link.expires_in_days

            from email_config import GMAIL_CONFIG
            
            # Configuration SMTP
            smtp_server = GMAIL_CONFIG['smtp_server']
            smtp_port = GMAIL_CONFIG['smtp_port']
            smtp_username = GMAIL_CONFIG['username']
            smtp_password = GMAIL_CONFIG['password']
            
            # URL de téléchargement
            #download_url = f"http://91.160.69.7:5000/download/{download_link.token}"
            download_url = f"http://91.160.69.7:5000/download/{token}"
            
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

    ⏰ Ce lien expire dans {expires_in_days} jours
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
            
            #app.logger.info(f"Email avec lien sécurisé envoyé à {employee_name}")
            return True
            
        except Exception as e:
            app.logger.error(f" Erreur envoi email: {str(e)}")
            return False

def create_individual_pdf_with_matricule(pdf_reader, employee_name, page_numbers, matricule, employees_data, output_dir,app):
    with app.app_context():
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
                #protect_pdf_with_password(output_path, matricule)
            # app.logger.info(f"PDF créé et protégé pour {employee_name} avec matricule {matricule} (extrait du PDF)")
                
                if send_email_with_secure_link(employee_name, email, output_path, app ):
                    app.logger.info(f"Processus complet réussi pour {employee_name}")
                else:
                    app.logger.info(f"Erreur lors de l'envoi pour {employee_name}")
                    
            elif employee_name in employees_data and not matricule:
                app.logger.info(f"Employé {employee_name} trouvé mais matricule non détecté - PDF créé sans protection")
                
            else:
                app.logger.info(f"PDF créé SANS protection pour {employee_name} ")
            
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
    #app.logger.info("Aucune période trouvée dans le PDF, utilisation de la date actuelle")
    return now.strftime('%Y_%m')


def process_pdf(filepath, output_dir, app):
    with app.app_context():
        """Fonction principale avec auto-import des employés """
        start_time = datetime.now()
        
        try:
            # 1. Chargement des employés existants
            employees = load_employees(app)
            employee_data = {}
            
            # 2. IMPORTANT : Garde le fichier ouvert pendant TOUT le traitement
            with open(filepath, 'rb') as file:
                pdf_reader = PyPDF2.PdfReader(file)
                total_pages = len(pdf_reader.pages)
                #app.logger.info(f"Analyse du PDF avec {total_pages} pages...")
                
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
                new_employees = detect_new_employees(employee_data,app)
                new_employees_count = 0
                
                if new_employees:
                    app.logger.info(f"\n Nouveaux employés détectés: {len(new_employees)}")
                    new_employees_count = add_employees_to_database(new_employees)
                    employees = load_employees(app)  # Recharger après ajout
                    
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
                
                # 5.  Création des PDF individuels PENDANT que le fichier est ouvert
                processed_count = 0
                for employee_name, data in employee_data.items():
                    if create_individual_pdf_with_period(
                        pdf_reader,  #  Le fichier est encore ouvert ici
                        employee_name,
                        data['pages'],
                        data['matricule'],
                        data['period'],
                        employees,
                        output_dir,
                        app
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
                            app.logger.error(f"Erreur enregistrement traitement pour {employee_name}: {str(e)}")
            
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
            app.logger.error(f" Erreur lors du traitement: {str(e)}")
            return {
                'success': False,
                'error': str(e)
            }

def detect_new_employees(employee_data_from_pdf , app ):
    with app.app_context():
        """Détecte les nouveaux employés par matricule (plus fiable que le nom)"""
        
        existing_matricules = set()
        try:
            employees_in_db = Employee.query.filter_by(statut='actif').all()
            existing_matricules = {emp.matricule for emp in employees_in_db if emp.matricule}
        except Exception as e:
            app.logger.error(f"Erreur lors de la vérification des matricules: {str(e)}")
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
        
        app.logger.info(f" {len(new_employees)} nouveaux employés détectés par matricule")
        return new_employees


def create_individual_pdf_with_period(pdf_reader, employee_name, page_numbers, matricule, period, employees_data, output_dir, app):
    with app.app_context():
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
            
            # NOUVEAU : Logique avec liens sécurisés
            if matricule:
                employee_record = find_employee_by_matricule(matricule,app)
                
                if employee_record:
                    # Protection avec matricule
                    #protect_pdf_with_password(output_path, matricule)
                    #app.logger.info(f" PDF créé et protégé pour {employee_name}")
                    #app.logger.info(f" Matricule: {matricule}")
                    #app.logger.info(f" Fichier: {output_filename}")
                    
                    # 🔗 NOUVEAU : Génération du lien sécurisé
                    # Récupérer le traitement actuel (vous devrez passer cette info)
                    current_traitement = get_current_traitement(output_dir,app) 
                    
                    if current_traitement:
                        download_link = generate_secure_download_link(
                            employee_record, 
                            current_traitement, 
                            output_path, 
                            matricule, app
                        )
                        
                        if download_link:
                            # 📧 Envoi email avec lien sécurisé
                            if send_email_with_secure_link(employee_name, employee_record.email, download_link, app):
                                #app.logger.info(f"Lien sécurisé envoyé à {employee_name}")
                                return True
                            else:
                                app.logger.error(f"Erreur envoi lien pour {employee_name}")
                        else:
                            app.logger.error(f"Erreur génération lien pour {employee_name}")
                    else:
                        app.logger.error(f"Traitement non trouvé pour {employee_name}")
                else:
                    app.logger.error(f"Matricule {matricule} non trouvé en base")
            
            # Fallback : PDF créé sans envoi
            #app.logger.info(f"PDF créé pour {employee_name} - pas d'envoi automatique")
            return True
            
        except Exception as e:
            app.logger.error(f"Erreur création PDF pour {employee_name}: {str(e)}")
            return False

'''def protect_pdf_with_password(filepath, password):
    """Protège un PDF avec un mot de passe"""
    try:
        # Solution 1: Utilisation du paramètre allow_overwriting_input=True
        with pikepdf.open(filepath, allow_overwriting_input=True) as pdf:
            pdf.save(filepath, encryption=pikepdf.Encryption(user=password, owner=password))
        #app.logger.info(f"PDF protégé avec le mot de passe: {password}")
        
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
            #app.logger.info(f"PDF protégé avec le mot de passe (méthode alternative): {password}")
            
        except Exception as e2:
            app.logger.error(f"Erreur lors de la protection alternative du PDF: {str(e2)}")
'''