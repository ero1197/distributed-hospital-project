import os

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

from models import db, Medication, Prescription

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def create_app():
    app = Flask(__name__)

    db_url = os.getenv("DATABASE_URL", "sqlite:///pharmacy.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")

    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "pharmacy"}), 200

    @app.post("/medications")
    def add_medication():
        data = request.get_json() or {}
        name = data.get("name")
        if not name:
            return jsonify({"error": "name required"}), 400

        med = Medication(
            name=name,
            strength=data.get("strength"),
            stock=data.get("stock", 0),
        )
        db.session.add(med)
        db.session.commit()
        return jsonify({"message": "medication added", "id": med.id}), 201

    @app.get("/medications")
    def list_medications():
        meds = Medication.query.all()
        return jsonify(
            [
                {
                    "id": m.id,
                    "name": m.name,
                    "strength": m.strength,
                    "stock": m.stock,
                }
                for m in meds
            ]
        )

    @app.post("/prescriptions")
    def create_prescription():
        data = request.get_json() or {}
        required = ["patient_name", "medication_id", "quantity"]
        if not all(k in data for k in required):
            return jsonify({"error": "Missing required fields", "required": required}), 400

        med = Medication.query.get(data["medication_id"])
        if not med:
            return jsonify({"error": "Medication not found"}), 404

        rx = Prescription(
            patient_name=data["patient_name"],
            medication_id=med.id,
            quantity=data["quantity"],
        )
        db.session.add(rx)
        db.session.commit()
        return jsonify({"message": "prescription created", "id": rx.id}), 201

    @app.put("/prescriptions/<int:rx_id>/dispense")
    def dispense_prescription(rx_id):
        rx = Prescription.query.get(rx_id)
        if not rx:
            return jsonify({"error": "Prescription not found"}), 404

        med = rx.medication
        if med.stock < rx.quantity:
            return jsonify({"error": "Not enough stock"}), 400

        med.stock -= rx.quantity
        rx.status = "dispensed"
        db.session.commit()
        return jsonify({"message": "dispensed"})

    @app.get("/prescriptions")
    def list_prescriptions():
        rxs = Prescription.query.order_by(Prescription.created_at.desc()).all()
        return jsonify(
            [
                {
                    "id": r.id,
                    "patient_name": r.patient_name,
                    "medication": r.medication.name if r.medication else None,
                    "quantity": r.quantity,
                    "status": r.status,
                    "created_at": r.created_at.isoformat(),
                }
                for r in rxs
            ]
        )

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("PHARMACY_PORT", 5002))
    app.run(host="0.0.0.0", port=port)
