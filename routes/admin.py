from flask import render_template, request, redirect, url_for, flash
from . import admin_bp
# importe services et models utilisés par tes routes admin

@admin_bp.get("/")
def admin_dashboard():
    return redirect(url_for("admin.manage_employees"))

@admin_bp.get("/employees")
def manage_employees():
    # colle ta logique actuelle de gestion employés
    ...
