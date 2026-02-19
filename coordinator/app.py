import os
from datetime import datetime

from flask import (
    Flask,
    jsonify,
    request,
    render_template,
    redirect,
    url_for,
    flash,
)
from flask_sqlalchemy import SQLAlchemy
from dotenv import load_dotenv
import requests
from flask_login import (
    LoginManager,
    login_user,
    logout_user,
    login_required,
    current_user,
)

# 👇 THIS must come from models.py, not flask_login
from models import db, User, PatientIndex, Appointment


# Load .env for coordinator
load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), ".env"))


def create_app():
    app = Flask(__name__)

    db_url = os.getenv("DATABASE_URL", "sqlite:///coordinator.db")
    app.config["SQLALCHEMY_DATABASE_URI"] = db_url
    app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
    app.config["SECRET_KEY"] = os.getenv("SECRET_KEY", "dev-key")

    db.init_app(app)

    login_manager = LoginManager()
    login_manager.login_view = "login"
    login_manager.init_app(app)

    EMERGENCY_URL = os.getenv("EMERGENCY_URL", "http://127.0.0.1:5001")
    PHARMACY_URL = os.getenv("PHARMACY_URL", "http://127.0.0.1:5002")
    RADIOLOGY_URL = os.getenv("RADIOLOGY_URL", "http://127.0.0.1:5003")


    @login_manager.user_loader
    def load_user(user_id):
        return User.query.get(int(user_id))

    # Flask 3: create tables and seed admin user in app context
    with app.app_context():
        db.create_all()
        # Seed a default admin if none exists (demo only)
        if User.query.count() == 0:
            admin = User(username="admin", role="admin")
            admin.set_password("admin123")  # demo password
            db.session.add(admin)
            db.session.commit()
            print("Seeded default admin user -> username: admin / password: admin123")

    # -------- JSON APIs (unchanged core) --------

    @app.get("/health")
    def health():
        return jsonify({"status": "ok", "service": "coordinator"}), 200

    @app.post("/sync/patient")
    def sync_patient():
        data = request.get_json() or {}
        required = ["local_patient_id", "department", "name"]

        if not all(k in data for k in required):
            return jsonify({"error": "Missing required fields", "required": required}), 400

        local_id = data["local_patient_id"]
        dept = data["department"]

        patient = PatientIndex.query.filter_by(
            local_patient_id=local_id, department=dept
        ).first()

        if patient is None:
            patient = PatientIndex(
                local_patient_id=local_id,
                department=dept,
                name=data["name"],
                dob=data.get("dob"),
                contact_info=data.get("contact_info"),
                last_updated=datetime.utcnow(),
            )
            db.session.add(patient)
        else:
            patient.name = data["name"]
            patient.dob = data.get("dob")
            patient.contact_info = data.get("contact_info")
            patient.last_updated = datetime.utcnow()

        db.session.commit()
        return jsonify({"message": "patient synced", "patient": patient.to_dict()}), 201

    @app.get("/api/patients")
    def list_patients_api():
        patients = PatientIndex.query.order_by(PatientIndex.last_updated.desc()).all()
        return jsonify([p.to_dict() for p in patients]), 200

    @app.get("/api/patients/<int:global_id>")
    def get_patient_api(global_id):
        patient = PatientIndex.query.get(global_id)
        if patient is None:
            return jsonify({"error": "Patient not found"}), 404
        return jsonify(patient.to_dict()), 200

    # -------- Auth routes --------

    @app.route("/login", methods=["GET", "POST"])
    def login():
        if request.method == "POST":
            username = request.form.get("username")
            password = request.form.get("password")

            user = User.query.filter_by(username=username).first()
            if user and user.check_password(password):
                login_user(user)
                return redirect(url_for("dashboard"))
            else:
                flash("Invalid username or password", "error")

        return render_template("login.html")

    @app.get("/logout")
    @login_required
    def logout():
        logout_user()
        return redirect(url_for("login"))

    # -------- HTML UI routes --------

    @app.get("/")
    @login_required
    def dashboard():
        patients = PatientIndex.query.order_by(PatientIndex.last_updated.desc()).all()
        return render_template("dashboard.html", patients=patients)

    @app.route("/patients/new", methods=["GET", "POST"])
    @login_required
    def new_patient():
        error = None
        if request.method == "POST":
            name = request.form.get("name")
            dob = request.form.get("dob") or None
            contact_info = request.form.get("contact_info") or None

            if not name:
                error = "Name is required."
            else:
                payload = {
                    "name": name,
                    "dob": dob,
                    "contact_info": contact_info,
                }
                try:
                    resp = requests.post(
                        f"{EMERGENCY_URL}/patients", json=payload, timeout=5
                    )
                    if resp.status_code not in (200, 201):
                        error = f"Emergency service error: {resp.status_code}"
                    else:
                        return redirect(url_for("dashboard"))
                except Exception as e:
                    error = f"Could not reach Emergency service: {e}"

        return render_template("new_patient.html", error=error)

    @app.get("/patients/<int:global_id>/detail")
    @login_required
    def patient_detail(global_id):
        patient = PatientIndex.query.get(global_id)
        if patient is None:
            return redirect(url_for("dashboard"))

        # Emergency visits
        visits = []
        if patient.department == "emergency":
            try:
                resp = requests.get(
                    f"{EMERGENCY_URL}/patients/{patient.local_patient_id}/visits",
                    timeout=5,
                )
                if resp.status_code == 200:
                    visits = resp.json()
            except Exception as e:
                print("Error fetching visits from Emergency:", e)

        # Appointments for this patient
        appointments = Appointment.query.filter_by(
            patient_global_id=patient.global_id
        ).order_by(Appointment.start_time.asc()).all()

        return render_template(
            "patient_detail.html",
            patient=patient,
            visits=visits,
            visit_error=None,
            appointments=appointments,
        )

    @app.post("/patients/<int:global_id>/emergency-visit")
    @login_required
    def add_emergency_visit(global_id):
        patient = PatientIndex.query.get(global_id)
        if patient is None:
            return redirect(url_for("dashboard"))

        symptoms = request.form.get("symptoms")
        triage_level = request.form.get("triage_level")

        visit_error = None

        if not symptoms or not triage_level:
            visit_error = "Symptoms and triage level are required."
        elif patient.department != "emergency":
            visit_error = "Emergency visits supported only for Emergency patients in this demo."
        else:
            payload = {
                "patient_id": patient.local_patient_id,
                "symptoms": symptoms,
                "triage_level": triage_level,
            }
            try:
                resp = requests.post(f"{EMERGENCY_URL}/visits", json=payload, timeout=5)
                if resp.status_code not in (200, 201):
                    visit_error = f"Emergency service error: {resp.status_code}"
            except Exception as e:
                visit_error = f"Could not reach Emergency service: {e}"

        # Refresh visits + appointments
        visits = []
        if patient.department == "emergency":
            try:
                resp = requests.get(
                    f"{EMERGENCY_URL}/patients/{patient.local_patient_id}/visits",
                    timeout=5,
                )
                if resp.status_code == 200:
                    visits = resp.json()
            except Exception as e:
                print("Error fetching visits from Emergency:", e)

        appointments = Appointment.query.filter_by(
            patient_global_id=patient.global_id
        ).order_by(Appointment.start_time.asc()).all()

        return render_template(
            "patient_detail.html",
            patient=patient,
            visits=visits,
            visit_error=visit_error,
            appointments=appointments,
        )

    @app.post("/patients/<int:global_id>/appointment")
    @login_required
    def add_appointment(global_id):
        """
        Handle appointment booking for a patient.
        """
        patient = PatientIndex.query.get(global_id)
        if patient is None:
            return redirect(url_for("dashboard"))

        department = request.form.get("department") or patient.department
        start_time_str = request.form.get("start_time")
        notes = request.form.get("notes") or None

        appt_error = None

        if not start_time_str:
            appt_error = "Appointment date & time is required."
        else:
            try:
                # HTML datetime-local: 'YYYY-MM-DDTHH:MM'
                start_time = datetime.fromisoformat(start_time_str)
                appt = Appointment(
                    patient_global_id=patient.global_id,
                    department=department,
                    start_time=start_time,
                    status="scheduled",
                    notes=notes,
                )
                db.session.add(appt)
                db.session.commit()
            except Exception as e:
                db.session.rollback()
                appt_error = f"Could not create appointment: {e}"

        # Refresh visits + appointments for page render
        visits = []
        if patient.department == "emergency":
            try:
                resp = requests.get(
                    f"{EMERGENCY_URL}/patients/{patient.local_patient_id}/visits",
                    timeout=5,
                )
                if resp.status_code == 200:
                    visits = resp.json()
            except Exception as e:
                print("Error fetching visits from Emergency:", e)

        appointments = Appointment.query.filter_by(
            patient_global_id=patient.global_id
        ).order_by(Appointment.start_time.asc()).all()

        return render_template(
            "patient_detail.html",
            patient=patient,
            visits=visits,
            visit_error=None,
            appointments=appointments,
            appt_error=appt_error,
        )

            # ---------- Pharmacy UI ----------

    @app.route("/pharmacy", methods=["GET"])
    @login_required
    def pharmacy_view():
        medications = []
        prescriptions = []
        med_error = None
        rx_error = None

        try:
            resp = requests.get(f"{PHARMACY_URL}/medications", timeout=5)
            if resp.status_code == 200:
                medications = resp.json()
        except Exception as e:
            med_error = f"Could not load medications: {e}"

        try:
            resp = requests.get(f"{PHARMACY_URL}/prescriptions", timeout=5)
            if resp.status_code == 200:
                prescriptions = resp.json()
        except Exception as e:
            rx_error = f"Could not load prescriptions: {e}"

        return render_template(
            "pharmacy.html",
            medications=medications,
            prescriptions=prescriptions,
            med_error=med_error,
            rx_error=rx_error,
        )

    @app.post("/pharmacy/medications")
    @login_required
    def pharmacy_add_medication():
        name = request.form.get("name")
        strength = request.form.get("strength") or None
        stock = request.form.get("stock") or "0"

        payload = {
            "name": name,
            "strength": strength,
            "stock": int(stock) if stock else 0,
        }

        try:
            resp = requests.post(f"{PHARMACY_URL}/medications", json=payload, timeout=5)
            if resp.status_code not in (200, 201):
                # store error in querystring? simplest: flash & redirect
                # but to keep it simple, we just ignore and reload.
                print("Pharmacy error (add medication):", resp.status_code, resp.text)
        except Exception as e:
            print("Pharmacy connection error (add medication):", e)

        return redirect(url_for("pharmacy_view"))

    @app.post("/pharmacy/prescriptions")
    @login_required
    def pharmacy_add_prescription():
        patient_name = request.form.get("patient_name")
        medication_id = request.form.get("medication_id")
        quantity = request.form.get("quantity") or "1"

        payload = {
            "patient_name": patient_name,
            "medication_id": int(medication_id),
            "quantity": int(quantity),
        }

        try:
            resp = requests.post(f"{PHARMACY_URL}/prescriptions", json=payload, timeout=5)
            if resp.status_code not in (200, 201):
                print("Pharmacy error (add prescription):", resp.status_code, resp.text)
        except Exception as e:
            print("Pharmacy connection error (add prescription):", e)

        return redirect(url_for("pharmacy_view"))

            # ---------- Radiology UI ----------

    @app.route("/radiology", methods=["GET"])
    @login_required
    def radiology_view():
        orders = []
        order_error = None
        complete_error = None

        try:
            resp = requests.get(f"{RADIOLOGY_URL}/orders", timeout=5)
            if resp.status_code == 200:
                orders = resp.json()
        except Exception as e:
            order_error = f"Could not load orders: {e}"

        return render_template(
            "radiology.html",
            orders=orders,
            order_error=order_error,
            complete_error=complete_error,
        )

    @app.post("/radiology/orders")
    @login_required
    def radiology_add_order():
        patient_name = request.form.get("patient_name")
        modality = request.form.get("modality")
        body_part = request.form.get("body_part") or None

        payload = {
            "patient_name": patient_name,
            "modality": modality,
            "body_part": body_part,
        }

        try:
            resp = requests.post(f"{RADIOLOGY_URL}/orders", json=payload, timeout=5)
            if resp.status_code not in (200, 201):
                print("Radiology error (create order):", resp.status_code, resp.text)
        except Exception as e:
            print("Radiology connection error (create order):", e)

        return redirect(url_for("radiology_view"))

    @app.post("/radiology/complete")
    @login_required
    def radiology_complete_order():
        order_id = request.form.get("order_id")
        report = request.form.get("report") or None

        payload = {"report": report} if report else {}

        try:
            resp = requests.put(
                f"{RADIOLOGY_URL}/orders/{order_id}/complete",
                json=payload,
                timeout=5,
            )
            if resp.status_code not in (200, 201):
                print("Radiology error (complete order):", resp.status_code, resp.text)
        except Exception as e:
            print("Radiology connection error (complete order):", e)

        return redirect(url_for("radiology_view"))


    return app


if __name__ == "__main__":
    app = create_app()
    port = int(os.getenv("COORDINATOR_PORT", 5050))
    app.run(host="0.0.0.0", port=port)
