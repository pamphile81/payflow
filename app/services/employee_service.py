from app.model.models import db, Employee

# Chargement des employés de
def load_employees(app):
    with app.app_context():
        """Charge les employés depuis PostgreSQL avec matricule comme clé"""
        employees = {}
        try:
            employees_list = Employee.query.filter_by(statut='actif').all()
            for emp in employees_list:
                # Clé par nom ET matricule pour compatibilité
                employees[emp.nom_employe] = {
                    'email': emp.email,
                    'id': emp.id,
                    'matricule': emp.matricule  
                }
            #app.logger.info(f"{len(employees)} employés chargés (identifiés par matricule)")
            return employees
        except Exception as e:
            app.logger.error(f"Erreur lors du chargement des employés: {str(e)}")
            return {}
    

def find_employee_by_matricule(matricule,app):
    with app.app_context(): 
        """Trouve un employé par son matricule (plus fiable que le nom)"""
        try:
            return Employee.query.filter_by(matricule=matricule, statut='actif').first()
        except Exception as e:
            app.logger.error(f"Erreur recherche matricule {matricule}: {str(e)}")
            return None
    

def add_employees_to_database(new_employees, app, source='pdf_import'):
    """Ajoute les nouveaux employés avec matricule obligatoire"""
    with app.app_context(): 
        added_count = 0
        for emp_data in new_employees:
            try:
                if not emp_data.get('matricule'):
                    app.logger.info(f"Employé {emp_data['nom']} ignoré - matricule manquant")
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
                #app.logger.info(f"Employé ajouté: {emp_data['nom']} (Matricule: {emp_data['matricule']})")
                
            except Exception as e:
                app.logger.error(f"Erreur lors de l'ajout de {emp_data['nom']}: {str(e)}")
        
        try:
            db.session.commit()
            #app.logger.info(f" {added_count} nouveaux employés sauvegardés avec leur matricule")
            return added_count
        except Exception as e:
            db.session.rollback()
            app.logger.error(f"Erreur lors de la sauvegarde: {str(e)}")
            return 0
