# services/treatment_service.py
from __future__ import annotations
import os
from datetime import datetime
from typing import Dict, List
from flask import current_app
from app.extensions import db
from app.models.models import Employee, Traitement, TraitementEmploye
from PyPDF2 import PdfReader, PdfWriter

from services.employee_service import (
    load_employees,
    detect_new_employees,
    add_employees_to_database,
    find_employee_by_matricule,
)
from services.pdf_service import (
    protect_pdf_with_password,
    extract_employee_name_from_page,
    extract_employee_matricule_from_page,
    extract_period_from_page,
)
from services.link_service import generate_secure_download_link
from services.email_service import send_email_with_secure_link


def _safe_filename(name: str) -> str:
    return "".join(c for c in name if c.isalnum() or c in (" ", "-", "_")).rstrip()

def _create_individual_pdf_with_period(
    pdf_reader: PdfReader,
    employee_name: str,
    page_numbers: List[int],
    matricule: str | None,
    period: str | None,
    output_dir: str,
    traitement: Traitement,
) -> bool:
    """Crée un PDF, protège si possible, génère un lien et envoie l'email."""
    try:
        writer = PdfWriter()
        for p in page_numbers:
            writer.add_page(pdf_reader.pages[p])

        safe = _safe_filename(employee_name)
        period_str = period or datetime.now().strftime("%Y_%m")
        out_filename = f"{safe}_{period_str}.pdf"
        out_path = os.path.join(output_dir, out_filename)

        with open(out_path, "wb") as f:
            writer.write(f)

        if matricule:
            emp = find_employee_by_matricule(matricule)
        else:
            emp = None

        if emp:
            protect_pdf_with_password(out_path, matricule or "")
            dl = generate_secure_download_link(emp, traitement, out_path, matricule or "")
            if dl:
                ok = send_email_with_secure_link(employee_name, emp.email, dl)
                if not ok:
                    current_app.logger.warning(f"[treatment] Mail non envoyé pour {employee_name}")
        else:
            current_app.logger.info(f"[treatment] PDF créé sans envoi pour {employee_name}")

        return True
    except Exception as e:
        current_app.logger.error(f"[treatment] Erreur PDF {employee_name}: {e}")
        return False


def process_pdf(filepath: str, output_dir: str) -> dict:
    """
    Pipeline complet :
    - lecture PDF
    - extraction (nom/matricule/période)
    - détection/ajout nouveaux employés
    - création Traitement
    - génération des PDFs individuels + liens + email
    """
    start = datetime.now()
    try:
        employees_map = load_employees()
        employee_data: Dict[str, dict] = {}

        with open(filepath, "rb") as f:
            reader = PdfReader(f)
            total_pages = len(reader.pages)

            # Parse pages
            for i in range(total_pages):
                page_text = reader.pages[i].extract_text()
                name = extract_employee_name_from_page(page_text)
                matricule = extract_employee_matricule_from_page(page_text)
                period = extract_period_from_page(page_text)

                if name:
                    if name not in employee_data:
                        employee_data[name] = {"pages": [], "matricule": matricule, "period": period}
                    else:
                        if not employee_data[name]["matricule"] and matricule:
                            employee_data[name]["matricule"] = matricule
                        if not employee_data[name]["period"] and period:
                            employee_data[name]["period"] = period
                    employee_data[name]["pages"].append(i)

            # Nouveaux employés
            new_emps = detect_new_employees(employee_data)
            new_count = add_employees_to_database(new_emps) if new_emps else 0
            if new_count:
                current_app.logger.info(f"[treatment] {new_count} nouveaux employés ajoutés")

            # Enregistrement Traitement
            traitement = Traitement(
                timestamp_folder=os.path.basename(output_dir),
                fichier_original=os.path.basename(filepath),
                taille_fichier=os.path.getsize(filepath),
                nombre_pages=total_pages,
                nombre_employes_detectes=len(employee_data),
                nombre_nouveaux_employes=new_count,
                statut="en_cours",
            )
            db.session.add(traitement)
            db.session.commit()

            # Génération PDFs individuels
            processed = 0
            for name, data in employee_data.items():
                if _create_individual_pdf_with_period(
                    reader,
                    name,
                    data["pages"],
                    data.get("matricule"),
                    data.get("period"),
                    output_dir,
                    traitement,
                ):
                    processed += 1
                    # Historique par employé
                    emp = Employee.query.filter_by(nom_employe=name).first()
                    if emp:
                        te = TraitementEmploye(
                            traitement_id=traitement.id,
                            employe_id=emp.id,
                            matricule_extrait=data.get("matricule"),
                            periode_extraite=data.get("period"),
                            nom_fichier_genere=f"{_safe_filename(name)}_{(data.get('period') or datetime.now().strftime('%Y_%m'))}.pdf",
                        )
                        db.session.add(te)

        # Finalisation
        duration = int((datetime.now() - start).total_seconds())
        traitement.nombre_employes_traites = processed
        traitement.duree_traitement_secondes = duration
        traitement.statut = "termine" if processed == len(employee_data) else "partiel"
        db.session.commit()

        return {
            "success": True,
            "count": processed,
            "total_employees": len(employee_data),
            "new_employees": new_count,
            "message": f"{processed} fiches traitées sur {len(employee_data)}"
                       + (f" (dont {new_count} nouveaux)" if new_count else ""),
        }

    except Exception as e:
        current_app.logger.error(f"[treatment] Erreur process_pdf: {e}")
        db.session.rollback()
        return {"success": False, "error": str(e)}
