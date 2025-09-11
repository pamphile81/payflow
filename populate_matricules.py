# populate_matricules.py
from app import create_app
from models import db, Employee

def populate_missing_matricules():
    """Remplit les matricules manquants"""
    
    app = create_app('development')
    with app.app_context():
        try:
            # Trouver les employés sans matricule
            employees_without_matricule = Employee.query.filter(
                (Employee.matricule.is_(None)) | (Employee.matricule == '')
            ).all()
            
            print(f"🔍 {len(employees_without_matricule)} employés sans matricule trouvés")
            
            updated_count = 0
            for emp in employees_without_matricule:
                # Génération matricule temporaire basé sur l'ID
                temp_matricule = f"TEMP{emp.id:04d}"
                emp.matricule = temp_matricule
                updated_count += 1
                print(f"📝 {emp.nom_employe} -> {temp_matricule}")
            
            db.session.commit()
            print(f"✅ {updated_count} matricules temporaires générés")
            
            # Vérification
            total_with_matricule = Employee.query.filter(Employee.matricule.isnot(None)).count()
            print(f"📊 Total employés avec matricule: {total_with_matricule}")
            
        except Exception as e:
            print(f"❌ Erreur: {str(e)}")
            db.session.rollback()

if __name__ == '__main__':
    populate_missing_matricules()
