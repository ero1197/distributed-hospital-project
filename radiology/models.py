from flask_sqlalchemy import SQLAlchemy
from datetime import datetime

db = SQLAlchemy()


class RadiologyOrder(db.Model):
    __tablename__ = "radiology_orders"

    id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    patient_name = db.Column(db.String(120), nullable=False)
    modality = db.Column(db.String(50), nullable=False)  # X-ray, CT, MRI
    body_part = db.Column(db.String(100))
    status = db.Column(db.String(20), default="ordered")  # ordered, completed
    report = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
