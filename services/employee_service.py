# services/employee_service.py
from __future__ import annotations
from flask import current_app
from typing import Dict, List, Optional
from extensions import db
from models import Employee
from datetime import datetime

def load_employees() -> Dict[str, dict]:
    """Charge les employés actifs, clé = nom (compat)."""
    employees: Dict[str, dict] = {}
    try:
        employees_list: List[Employee] = Employee.query.filter_by(statut='actif').all()
        for emp in employees_list:
            employees[emp.nom_employe] = {
                'email': emp.email,
                'id': emp.id,
                'matricule': emp.matricule,
            }
        return employees
    except Exception as e:
        current_app.logger.error(f"[employees] Erreur load_employees: {e}")
        return {}

def find_employee_by_matricule(matricule: str) -> Optional[Employee]:
    """Trouve un employé actif par matricule."""
    try:
        return Employee.query.filter_by(matricule=matricule, statut='actif').first()
    except Exception as e:
        current_app.logger.error(f"[employees] Erreur find by matricule {matricule}: {e}")
        return None

def detect_new_employees(employee_data_from_pdf: Dict[str, dict]) -> List[dict]:
    """
    Détecte les nouveaux employés par matricule.
    `employee_data_from_pdf` attendu: { 'Nom Employé': {'matricule': '1234', 'period': 'YYYY_MM', 'pages': [...] }, ...}
    """
    try:
        existing_matricules = {
            emp.matricule for emp in Employee.query.filter_by(statut='actif').all() if emp.matricule
        }
    except Exception as e:
        current_app.logger.error(f"[employees] Erreur récupération matricules existants: {e}")
        return []

    new_employees: List[dict] = []
    for employee_name, data in employee_data_from_pdf.items():
        matricule = data.get('matricule')
        if matricule and matricule not in existing_matricules:
            new_employees.append({
                'nom': employee_name,
                'matricule': matricule,
                'period': data.get('period'),
            })

    current_app.logger.info(f"[employees] {len(new_employees)} nouveaux employés détectés")
    return new_employees

def add_employees_to_database(new_employees: List[dict], source: str = 'pdf_import') -> int:
    """Ajoute les nouveaux employés (matricule obligatoire). Retourne le nombre ajoutés."""
    added_count = 0
    for emp_data in new_employees:
        try:
            matricule = emp_data.get('matricule')
            nom = emp_data.get('nom')
            if not matricule:
                current_app.logger.info(f"[employees] Ignoré (matricule manquant) : {nom}")
                continue

            # Email temporaire basé sur le matricule
            temp_email = f"employe.{matricule}@temporaire.com"

            new_employee = Employee(
                matricule=matricule,
                nom_employe=nom,
                email=temp_email,
                statut='actif',
                source_creation=source,
                date_creation=datetime.utcnow(),
                date_derniere_maj=datetime.utcnow(),
            )

            db.session.add(new_employee)
            added_count += 1

        except Exception as e:
            current_app.logger.error(f"[employees] Erreur ajout {emp_data}: {e}")

    try:
        db.session.commit()
        current_app.logger.info(f"[employees] {added_count} nouveaux employés ajoutés")
        return added_count
    except Exception as e:
        db.session.rollback()
        current_app.logger.error(f"[employees] Erreur commit: {e}")
        return 0
