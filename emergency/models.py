# emergency/models.py
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class Patient(db.Model):
    __tablename__ = "patients"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(120), nullable=False)
    dob = db.Column(db.String(20), nullable=True)
    contact_info = db.Column(db.String(200), nullable=True)

    visits = db.relationship("EmergencyVisit", backref="patient", lazy=True)

    def to_dict(self):
        return {
            "id": self.id,
            "name": self.name,
            "dob": self.dob,
            "contact_info": self.contact_info,
        }


class EmergencyVisit(db.Model):
    __tablename__ = "emergency_visits"

    id = db.Column(db.Integer, primary_key=True)
    patient_id = db.Column(db.Integer, db.ForeignKey("patients.id"), nullable=False)
    symptoms = db.Column(db.String(300), nullable=False)
    triage_level = db.Column(db.String(20), nullable=False)  # "high", "medium", "low"
    created_at = db.Column(db.DateTime, default=datetime.utcnow, nullable=False)

    def to_dict(self):
        return {
            "id": self.id,
            "patient_id": self.patient_id,
            "symptoms": self.symptoms,
            "triage_level": self.triage_level,
            "created_at": self.created_at.isoformat(),
        }
