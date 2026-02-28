from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import mysql.connector
from datetime import date

app = Flask(__name__)
app.secret_key = "hms_secret_key"
CORS(app)

# ─────────────────────────────────────────────
#  DATABASE CONNECTION
#  Tables available: student, complaint, room, roomchangerequest
# ─────────────────────────────────────────────
def get_db():
    return mysql.connector.connect(
        host="localhost",
        user="root",           # change if your MySQL username is different
        password="Merin123@",           # change if you have a MySQL password
        database="hostel_db"
    )


# ─────────────────────────────────────────────
#  SERVE HTML PAGES
# ─────────────────────────────────────────────
@app.route("/")
def home():
    return redirect(url_for("login_page"))

@app.route("/login.html")
def login_page():
    return render_template("login.html")

@app.route("/index.html")
def student_page():
    return render_template("index.html")

@app.route("/warden.html")
def warden_page():
    return render_template("warden.html")

@app.route("/admin.html")
def admin_page():
    return render_template("admin.html")


# ─────────────────────────────────────────────
#  LOGIN
#  POST /login
#  Password = phone_no in student table
# ─────────────────────────────────────────────
@app.route("/login", methods=["POST"])
def login():
    data     = request.json
    email    = data.get("email", "").strip()
    password = data.get("password", "").strip()

    db  = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute(
        "SELECT student_id AS id, name, email, phone_no, room_id FROM student WHERE email=%s AND password=%s",
        (email, password)
    )
    user = cur.fetchone()
    if user:
        user["role"] = "student"
        cur.fetchone()  # or fetchall()
        cur.close(); db.close()
        return jsonify({"success": True, "user": user})

    cur.close(); db.close()
    return jsonify({"success": False, "message": "Invalid email or password"}), 401


# ─────────────────────────────────────────────
#  COMPLAINTS  (table: complaint)
# ─────────────────────────────────────────────
@app.route("/submit_complaint", methods=["POST"])
def submit_complaint():

    data = request.json

    student_id = data.get("student_id")
    room_id = data.get("room_id")
    comp_type = data.get("comp_type", "General")
    description = data.get("description", "")   # ✅ important

    db = get_db()
    cur = db.cursor()

    cur.execute(
        "INSERT INTO complaint (student_id, room_id, comp_type, comp_date, status, description) VALUES (%s,%s,%s,%s,%s,%s)",
        (student_id, room_id, comp_type, date.today(), "Pending", description)
    )

    db.commit()

    cur.close()
    db.close()

    return jsonify({"message": "Complaint submitted successfully"})


@app.route("/complaint_status/<int:student_id>", methods=["GET"])
def complaint_status(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT comp_id, comp_type, comp_date, status, response FROM complaint WHERE student_id=%s ORDER BY comp_date DESC",
        (student_id,)
    )
    complaints = cur.fetchall()
    for c in complaints:
        if c["comp_date"]:
            c["comp_date"] = str(c["comp_date"])
    cur.close(); db.close()
    return jsonify({"complaints": complaints})


@app.route("/warden/complaints", methods=["GET"])
def warden_get_complaints():
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT c.comp_id, c.comp_type, c.comp_date, c.status, c.response,
               s.name AS student_name, c.room_id
        FROM complaint c
        JOIN student s ON c.student_id = s.student_id
        ORDER BY c.comp_date DESC
    """)
    complaints = cur.fetchall()
    for c in complaints:
        if c["comp_date"]:
            c["comp_date"] = str(c["comp_date"])
    cur.close(); db.close()
    return jsonify({"complaints": complaints})


@app.route("/warden/resolve_complaint", methods=["POST"])
def resolve_complaint():
    data     = request.json
    comp_id  = data.get("comp_id")
    response = data.get("response", "Resolved by warden")
    if not comp_id:
        return jsonify({"message": "comp_id is required"}), 400
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "UPDATE complaint SET status='Resolved', response=%s WHERE comp_id=%s",
        (response, comp_id)
    )
    db.commit()
    cur.close(); db.close()
    return jsonify({"message": "Complaint resolved"})


# ─────────────────────────────────────────────
#  ROOM CHANGE  (table: roomchangerequest)
# ─────────────────────────────────────────────

@app.route("/room_change", methods=["POST"])
def room_change():
    data        = request.json
    student_id  = data.get("student_id")
    req_room_id = data.get("req_room_id", 0)
    reason      = data.get("reason", "")
    if not student_id:
        return jsonify({"message": "Missing student_id"}), 400
    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO roomchangerequest (student_id, req_room_id, req_date, reason, status) VALUES (%s, %s, %s, %s, %s)",
        (student_id, req_room_id, date.today(), reason, "Pending")
    )
    db.commit()
    request_id = cur.lastrowid
    cur.close(); db.close()
    return jsonify({"message": "Room change request submitted", "request_id": request_id})


@app.route("/room_change_status/<int:student_id>", methods=["GET"])
def room_change_status(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "SELECT request_id, req_room_id, req_date, reason, status FROM roomchangerequest WHERE student_id=%s ORDER BY req_date DESC",
        (student_id,)
    )
    requests = cur.fetchall()
    for r in requests:
        if r["req_date"]:
            r["req_date"] = str(r["req_date"])
    cur.close(); db.close()
    return jsonify({"requests": requests})


@app.route("/warden/room_change_requests", methods=["GET"])
def warden_room_change_requests():
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT r.request_id, r.req_room_id, r.req_date, r.reason, r.status,
               s.name AS student_name, s.student_id
        FROM roomchangerequest r
        JOIN student s ON r.student_id = s.student_id
        ORDER BY r.req_date DESC
    """)
    requests = cur.fetchall()
    for r in requests:
        if r["req_date"]:
            r["req_date"] = str(r["req_date"])
    cur.close(); db.close()
    return jsonify({"requests": requests})


@app.route("/warden/approve_room_change", methods=["POST"])
def approve_room_change():
    data       = request.json
    request_id = data.get("request_id")
    action     = data.get("action")
    if not request_id or action not in ("Approved", "Rejected"):
        return jsonify({"message": "Invalid request"}), 400
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("UPDATE roomchangerequest SET status=%s WHERE request_id=%s", (action, request_id))
    if action == "Approved":
        cur.execute("SELECT student_id, req_room_id FROM roomchangerequest WHERE request_id=%s", (request_id,))
        row = cur.fetchone()
        if row:
            cur.execute("UPDATE student SET room_id=%s WHERE student_id=%s", (row["req_room_id"], row["student_id"]))
    db.commit()
    cur.close(); db.close()
    return jsonify({"message": f"Request {action.lower()} successfully"})


# ─────────────────────────────────────────────
#  STUDENT DASHBOARD
#  Only uses: complaint, roomchangerequest (tables that exist)
# ─────────────────────────────────────────────
@app.route("/student/dashboard/<int:student_id>", methods=["GET"])
def student_dashboard(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)

    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaint WHERE student_id=%s AND status != 'Resolved'",
        (student_id,)
    )
    active_complaints = cur.fetchone()["cnt"]

    cur.execute("""
        SELECT comp_date AS event_date,
               CONCAT('Complaint: ', comp_type, ' - ', status) AS event
        FROM complaint WHERE student_id = %s
        UNION ALL
        SELECT req_date AS event_date,
               CONCAT('Room Change Request - ', status) AS event
        FROM roomchangerequest WHERE student_id = %s
        ORDER BY event_date DESC LIMIT 5
    """, (student_id, student_id))
    timeline = [{"event": r["event"], "date": str(r["event_date"])} for r in cur.fetchall()]

    cur.close(); db.close()
    return jsonify({
        "fee_status": "N/A", "fee_amount": 0,
        "attendance_pct": 0, "present_days": 0, "total_days": 0,
        "active_complaints": int(active_complaints),
        "timeline": timeline
    })


# ─────────────────────────────────────────────
#  STUDENT PROFILE
#  Uses: student, room tables only
# ─────────────────────────────────────────────
@app.route("/student/profile/<int:student_id>", methods=["GET"])
def student_profile(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT s.student_id, s.name, s.email, s.phone_no,
               s.department, s.semester, s.year_of_study,
               s.guardian_name, s.address, r.room_number
        FROM student s
        LEFT JOIN room r ON s.room_id = r.room_id
        WHERE s.student_id = %s
    """, (student_id,))
    profile = cur.fetchone()
    cur.close(); db.close()
    if not profile:
        return jsonify({"message": "Student not found"}), 404
    return jsonify({"profile": profile})


# ─────────────────────────────────────────────
if __name__ == "__main__":
    app.run(debug=True, port=5000)
