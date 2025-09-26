# routes/public.py
from __future__ import annotations

import os
import threading
from datetime import datetime
from typing import Dict, Any

from flask import (
    current_app,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    jsonify,
    send_file,
    session,
)
from werkzeug.utils import secure_filename

from ....routes import public_bp
from app.extensions import db
from app.models.models import Employee, Traitement, TraitementEmploye, DownloadLink

# Services (logique métier déjà extraite)
from services.employee_service import (
    load_employees,
    find_employee_by_matricule,
)
from services.pdf_service import process_pdf  # réalise tout le pipeline (PDF -> liens -> emails)
from services.link_service import (
    get_link_by_token,
    link_is_valid,
    register_access_attempt,
)

# ------------------------------
# Helpers module public
# ------------------------------

ALLOWED_EXTENSIONS = {"pdf"}
_processing_lock = threading.Lock()
_is_processing = False


def _allowed_file(filename: str) -> bool:
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS


def _generate_timestamp_folder() -> str:
    return datetime.now().strftime("%Y%m%d%H%M%S")


# ------------------------------
# Routes “publiques”
# ------------------------------

@public_bp.get("/")
def index():
    """Page d’accueil avec formulaire d’upload."""
    return render_template("index.html")


@public_bp.post("/upload")
def upload_file():
    """
    Traite le PDF uploadé :
      - crée un dossier timestampé dans uploads/ & output/
      - appelle services.pdf_service.process_pdf()
      - gère les flash messages
    Protection contre double-soumission via verrou (_processing_lock).
    """
    global _is_processing

    with _processing_lock:
        if _is_processing:
            flash("Un traitement est déjà en cours. Veuillez patienter.", "error")
            return redirect(url_for("public.index"))
        _is_processing = True

    try:
        if "file" not in request.files:
            flash("Aucun fichier sélectionné", "error")
            return redirect(url_for("public.index"))

        file = request.files["file"]
        if file.filename == "":
            flash("Aucun fichier sélectionné", "error")
            return redirect(url_for("public.index"))

        if not _allowed_file(file.filename):
            flash("❌ Format non autorisé (PDF uniquement).", "error")
            return redirect(url_for("public.index"))

        # Prépare les dossiers timestampés
        ts = _generate_timestamp_folder()
        uploads_root = current_app.config.get("UPLOAD_FOLDER", "uploads")
        output_root = current_app.config.get("OUTPUT_FOLDER", "output")

        upload_ts_dir = os.path.join(uploads_root, ts)
        output_ts_dir = os.path.join(output_root, ts)
        os.makedirs(upload_ts_dir, exist_ok=True)
        os.makedirs(output_ts_dir, exist_ok=True)

        # Sauvegarde le PDF source
        filename = secure_filename(file.filename)
        src_path = os.path.join(upload_ts_dir, filename)
        file.save(src_path)

        # Lance le pipeline métier (extraction, split, protection, liens, emails)
        # Le service se charge d’enregistrer le Traitement/TraitementEmploye/DownloadLink en base.
        result: Dict[str, Any] = process_pdf(
            src_path=src_path,
            output_dir=output_ts_dir,
            timestamp_folder=ts,       # utile pour relier au Traitement
        )

        if result.get("success"):
            count = result.get("count", 0)
            new_count = result.get("new_employees", 0)
            msg = f"✅ Traitement OK : {count} fiches."
            if new_count:
                msg += f" 🆕 {new_count} nouveaux employés ajoutés."
            flash(msg, "success")
        else:
            flash(f"❌ Erreur traitement : {result.get('error','inconnue')}", "error")

        return redirect(url_for("public.index"))

    except Exception as e:
        current_app.logger.exception("[public] Erreur upload_file")
        flash(f"❌ Erreur inattendue : {e}", "error")
        return redirect(url_for("public.index"))

    finally:
        with _processing_lock:
            _is_processing = False


@public_bp.get("/download/<string:token>")
def secure_download_page(token: str):
    """
    Page affichant le formulaire de vérification (matricule) pour un lien sécurisé.
    """
    # Récupère le lien (service) ou fallback sur le modèle
    dl: DownloadLink | None = get_link_by_token(token)
    if not dl:
        flash("Lien de téléchargement invalide ou expiré", "error")
        return render_template("download_error.html", error="Lien invalide")

    # Vérifie validité (service) – prend en compte expiration, statut, tentatives, etc.
    if not link_is_valid(dl):
        error_msg = (
            "Nombre maximum de tentatives dépassé"
            if dl.tentatives_acces >= dl.max_tentatives
            else "Lien expiré"
        )
        flash(f"Accès refusé : {error_msg}", "error")
        return render_template("download_error.html", error=error_msg)

    # OK → on affiche la page qui poste vers /download/<token>/verify
    return render_template(
        "secure_download.html",
        download_link=dl,
        employee=dl.employee  # relation SQLA
    )


@public_bp.post("/download/<string:token>/verify")
def verify_and_download(token: str):
    """
    Vérifie le matricule et, en cas de succès, renvoie JSON avec l’URL directe.
    Gestion côté JS (secure_download.html).
    """
    try:
        dl: DownloadLink | None = get_link_by_token(token)
        if not dl:
            return jsonify({"success": False, "message": "Lien invalide."}), 400

        client_ip = request.remote_addr or "unknown"
        matricule_saisi = (request.form.get("matricule") or "").strip()

        # Enregistre la tentative (service)
        register_access_attempt(dl, client_ip)

        # Lien encore valide ?
        if not link_is_valid(dl):
            remaining = max(0, dl.max_tentatives - dl.tentatives_acces)
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Lien expiré ou bloqué. Tentatives restantes : {remaining}.",
                        "remaining_attempts": remaining,
                    }
                ),
                400,
            )

        # Vérifie le matricule
        if matricule_saisi != (dl.matricule_requis or ""):
            db.session.commit()  # la tentative est comptée
            remaining = max(0, dl.max_tentatives - dl.tentatives_acces)
            current_app.logger.warning("[download] Matricule incorrect (token=%s)", token[:8])
            return (
                jsonify(
                    {
                        "success": False,
                        "message": f"Matricule incorrect. {remaining} tentatives restantes.",
                        "remaining_attempts": remaining,
                    }
                ),
                400,
            )

        # Succès : on incrémente les compteurs & date, et on répond avec l’URL de téléchargement direct
        dl.nombre_telechargements = (dl.nombre_telechargements or 0) + 1
        dl.derniere_date_telechargement = datetime.utcnow()
        db.session.commit()

        if not os.path.exists(dl.chemin_fichier):
            return jsonify({"success": False, "message": "Fichier introuvable."}), 404

        return jsonify(
            {
                "success": True,
                "message": "Téléchargement autorisé.",
                "download_url": url_for("public.download_file_direct", token=token),
                "employee_name": dl.employee.nom_employe if dl.employee else "",
                "filename": dl.nom_fichier,
                "download_count": dl.nombre_telechargements,
            }
        )

    except Exception as e:
        current_app.logger.exception("[download] Erreur verify_and_download")
        return jsonify({"success": False, "message": f"Erreur serveur: {e}"}), 500


@public_bp.get("/download/file/<string:token>")
def download_file_direct(token: str):
    """Téléchargement direct du fichier (après vérification réussie)."""
    try:
        dl: DownloadLink | None = get_link_by_token(token)
        if not dl or (dl.nombre_telechargements or 0) == 0:
            return "Téléchargement non autorisé", 403

        if not os.path.exists(dl.chemin_fichier):
            return "Fichier non trouvé", 404

        return send_file(
            dl.chemin_fichier,
            as_attachment=True,
            download_name=dl.nom_fichier,
        )
    except Exception:
        current_app.logger.exception("[download] Erreur download_file_direct")
        return "Erreur de téléchargement", 500


# ⚠️ Pour éviter le conflit d’URL avec /download/<token>,
# on expose le téléchargement “par traitement” sous /files/<timestamp>/<filename>.
@public_bp.get("/files/<string:timestamp>/<path:filename>")
def download_file_by_timestamp(timestamp: str, filename: str):
    """
    Télécharge un PDF généré à partir de son dossier timestamp et nom de fichier.
    Utile pour un lien simple (ex: page de détails d’un traitement).
    """
    try:
        base_output = current_app.config.get("OUTPUT_FOLDER", "output")
        file_path = os.path.join(base_output, timestamp, filename)

        if os.path.exists(file_path):
            return send_file(file_path, as_attachment=True, download_name=filename)
        else:
            flash("Fichier non trouvé", "error")
            return redirect(url_for("public.index"))
    except Exception as e:
        current_app.logger.exception("[public] Erreur download_file_by_timestamp")
        flash(f"Erreur lors du téléchargement: {e}", "error")
        return redirect(url_for("public.index"))


# (Optionnel) Page de succès si tu veux un flux “HTML” après le JSON
@public_bp.get("/download/success")
def download_success():
    """
    Page d’information “succès” (si tu veux l’utiliser).
    Le flux standard passe par JSON -> téléchargement direct.
    """
    token = request.args.get("token", "")
    employee_name = request.args.get("employee_name", "Employé")
    filename = request.args.get("filename", "votre fiche de paie")

    if not token:
        return redirect(url_for("public.index"))

    dl = get_link_by_token(token)
    if not dl or (dl.nombre_telechargements or 0) == 0:
        return redirect(url_for("public.index"))

    return render_template(
        "download_success.html",
        employee_name=employee_name,
        filename=filename,
        download_count=dl.nombre_telechargements,
        company_name="PayFlow",
    )
