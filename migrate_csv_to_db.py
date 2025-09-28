# migrate_csv_to_db.py
from app import create_app
from app.model.models import db, Employee
import csv
import os

def migrate_csv_to_postgresql():
    """Migre les employés du CSV vers PostgreSQL"""
    
    app = create_app('development')
    with app.app_context():
        try:
            if not os.path.exists('employees.csv'):
                print("❌ Fichier employees.csv non trouvé")
                return
            
            # Lecture du CSV existant
            employees_added = 0
            with open('employees.csv', 'r', encoding='utf-8') as file:
                reader = csv.DictReader(file)
                
                for row in reader:
                    # Vérifier si l'employé existe déjà
                    existing = Employee.query.filter_by(nom_employe=row['nom_employe']).first()
                    
                    if not existing:
                        employee = Employee(
                            nom_employe=row['nom_employe'],
                            email=row['email'],
                            statut='actif',
                            source_creation='manual'
                        )
                        db.session.add(employee)
                        employees_added += 1
                        print(f"✅ Ajouté: {row['nom_employe']}")
                    else:
                        print(f"⚠️ Existe déjà: {row['nom_employe']}")
            
            db.session.commit()
            print(f"\n🎉 Migration terminée: {employees_added} employés ajoutés en base PostgreSQL")
            
        except Exception as e:
            print(f"❌ Erreur lors de la migration: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    migrate_csv_to_postgresql()
