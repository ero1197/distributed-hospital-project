# emergency/app.py
import os

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests

from models import db, Patient, EmergencyVisit

# Load .env for this service
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def create_app():
    app = Flask(__name__)

    db_url = os.getenv("DATABASE_URL", "sqlite:///emergency.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")

    db.init_app(app)

    COORDINATOR_URL = os.getenv("COORDINATOR_URL", "http://127.0.0.1:5000")
    DEPARTMENT_NAME = os.getenv("DEPARTMENT_NAME", "emergency")

    with app.app_context():
        db.create_all()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "emergency"}), 200

    @app.post("/patients")
    def create_patient():
        """
        Expected JSON:
        {
          "name": "John Doe",
          "dob": "1999-01-01",
          "contact_info": "555-1234"
        }
        """
        data = request.get_json() or {}
        name = data.get("name")

        if not name:
            return jsonify({"error": "name is required"}), 400

        patient = Patient(
            name=name,
            dob=data.get("dob"),
            contact_info=data.get("contact_info"),
        )
        db.session.add(patient)
        db.session.commit()

        # Sync with coordinator (best effort)
        payload = {
            "local_patient_id": patient.id,
            "department": DEPARTMENT_NAME,
            "name": patient.name,
            "dob": patient.dob,
            "contact_info": patient.contact_info,
        }
        try:
            resp = requests.post(f"{COORDINATOR_URL}/sync/patient", json=payload, timeout=3)
            if resp.status_code not in (200, 201):
                print("Coordinator sync error:", resp.status_code, resp.text)
        except Exception as e:
            print("Could not reach coordinator:", e)

        return jsonify({"message": "patient created", "patient": patient.to_dict()}), 201

    @app.get("/patients/<int:patient_id>")
    def get_patient(patient_id):
        patient = Patient.query.get(patient_id)
        if patient is None:
            return jsonify({"error": "Patient not found"}), 404
        return jsonify(patient.to_dict()), 200

    @app.post("/visits")
    def create_visit():
        """
        Expected JSON:
        {
          "patient_id": 1,
          "symptoms": "Chest pain and shortness of breath",
          "triage_level": "high"
        }
        """
        data = request.get_json() or {}
        required = ["patient_id", "symptoms", "triage_level"]
        if not all(k in data for k in required):
            return jsonify({"error": "Missing required fields", "required": required}), 400

        patient = Patient.query.get(data["patient_id"])
        if patient is None:
            return jsonify({"error": "Patient not found"}), 404

        visit = EmergencyVisit(
            patient_id=patient.id,
            symptoms=data["symptoms"],
            triage_level=data["triage_level"],
        )
        db.session.add(visit)
        db.session.commit()

        return jsonify({"message": "visit created", "visit": visit.to_dict()}), 201

    @app.get("/patients/<int:patient_id>/visits")
    def list_visits(patient_id):
        patient = Patient.query.get(patient_id)
        if patient is None:
            return jsonify({"error": "Patient not found"}), 404

        visits = EmergencyVisit.query.filter_by(patient_id=patient_id).order_by(
            EmergencyVisit.created_at.desc()
        )
        return jsonify([v.to_dict() for v in visits]), 200

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("EMERGENCY_PORT", 5001))
    app.run(host="0.0.0.0", port=port)
