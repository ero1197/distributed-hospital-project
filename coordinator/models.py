from datetime import datetime

from flask_sqlalchemy import SQLAlchemy
from flask_login import UserMixin
from werkzeug.security import generate_password_hash, check_password_hash

db = SQLAlchemy()


class User(UserMixin, db.Model):
    """
    Simple user model for authentication.
    username: login name
    password_hash: hashed with PBKDF2 (works on macOS)
    role: 'admin', 'staff', etc.
    """
    __tablename__ = "users"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    password_hash = db.Column(db.String(255), nullable=False)
    role = db.Column(db.String(20), default="admin")

    def set_password(self, password: str):
        # IMPORTANT: use PBKDF2 instead of scrypt so it works on macOS
        self.password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    def check_password(self, password: str) -> bool:
        return check_password_hash(self.password_hash, password)


class PatientIndex(db.Model):
    __tablename__ = "patient_index"

    global_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    local_patient_id = db.Column(db.Integer, nullable=False)
    department = db.Column(db.String(50), nullable=False)
    name = db.Column(db.String(120), nullable=False)

    dob = db.Column(db.String(20))
    contact_info = db.Column(db.String(200))

    last_updated = db.Column(db.DateTime, default=datetime.utcnow)

    def to_dict(self):
        return {
            "global_id": self.global_id,
            "local_patient_id": self.local_patient_id,
            "department": self.department,
            "name": self.name,
            "dob": self.dob,
            "contact_info": self.contact_info,
            "last_updated": self.last_updated.isoformat()
            if self.last_updated
            else None,
        }


class Appointment(db.Model):
    __tablename__ = "appointments"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_global_id = db.Column(
        db.Integer, db.ForeignKey("patient_index.global_id"), nullable=False
    )
    department = db.Column(db.String(50), nullable=False)
    start_time = db.Column(db.DateTime, nullable=False)
    status = db.Column(db.String(20), default="scheduled")  # scheduled, completed, cancelled
    notes = db.Column(db.String(300))

    patient = db.relationship("PatientIndex", backref="appointments")

    def to_dict(self):
        return {
            "id": self.id,
            "patient_global_id": self.patient_global_id,
            "department": self.department,
            "start_time": self.start_time.isoformat(),
            "status": self.status,
            "notes": self.notes,
        }
