import os

from flask import Flask, jsonify, request
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv

from models import db, RadiologyOrder

load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def create_app():
    app = Flask(__name__)

    db_url = os.getenv("DATABASE_URL", "sqlite:///radiology.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")

    db.init_app(app)

    with app.app_context():
        db.create_all()

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "radiology"}), 200

    @app.post("/orders")
    def create_order():
        data = request.get_json() or {}
        required = ["patient_name", "modality"]
        if not all(k in data for k in required):
            return jsonify({"error": "Missing required fields", "required": required}), 400

        order = RadiologyOrder(
            patient_name=data["patient_name"],
            modality=data["modality"],
            body_part=data.get("body_part"),
        )
        db.session.add(order)
        db.session.commit()
        return jsonify({"message": "order created", "id": order.id}), 201

    @app.put("/orders/<int:order_id>/complete")
    def complete_order(order_id):
        order = RadiologyOrder.query.get(order_id)
        if not order:
            return jsonify({"error": "Order not found"}), 404

        order.status = "completed"
        order.report = (request.json or {}).get("report", order.report)
        db.session.commit()
        return jsonify({"message": "order completed"})

    @app.get("/orders")
    def list_orders():
        orders = RadiologyOrder.query.order_by(RadiologyOrder.created_at.desc()).all()
        return jsonify(
            [
                {
                    "id": o.id,
                    "patient_name": o.patient_name,
                    "modality": o.modality,
                    "body_part": o.body_part,
                    "status": o.status,
                    "report": o.report,
                    "created_at": o.created_at.isoformat(),
                }
                for o in orders
            ]
        )

    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("RADIOLOGY_PORT", 5003))
    app.run(host="0.0.0.0", port=port)
