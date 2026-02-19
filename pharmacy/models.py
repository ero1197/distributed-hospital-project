from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Medication(db.Model):
    __tablename__ = "medications"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    name = db.Column(db.String(120), nullable=False)
    strength = db.Column(db.String(50))
    stock = db.Column(db.Integer, default=0)


class Prescription(db.Model):
    __tablename__ = "prescriptions"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_name = db.Column(db.String(120), nullable=False)  # simple for demo
    medication_id = db.Column(db.Integer, db.ForeignKey("medications.id"), nullable=False)
    quantity = db.Column(db.Integer, nullable=False)
    status = db.Column(db.String(20), default="new")  # new, dispensed
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

    medication = db.relationship("Medication", backref="prescriptions")
