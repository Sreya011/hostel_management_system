from flask import Flask, request, jsonify, render_template, redirect, url_for
from flask_cors import CORS
import mysql.connector
from datetime import date
import os

app = Flask(__name__)
app.secret_key = "hms_secret_key"
CORS(app)


# =============================================================================
#  DATABASE CONNECTION
# =============================================================================

def get_db():
    return mysql.connector.connect(
        host=os.environ.get("DB_HOST", "localhost"),
        user=os.environ.get("DB_USER", "root"),
        password=os.environ.get("DB_PASSWORD", "Merin123@"),
        database=os.environ.get("DB_NAME", "hostel_db")
    )


# =============================================================================
#  PRIORITY SCORE CALCULATOR
# =============================================================================

def calculate_priority(distance, annual_income, sgpa, year):
    distance_score = min(distance / 10, 50)
    income_score   = max(0, 50 - annual_income / 20000)
    sgpa_score     = round(sgpa * max(0, year - 1) * 0.5, 2)
    return round(distance_score + income_score + sgpa_score, 2)


# =============================================================================
#  AUTO-MIGRATION
#  Runs on every startup. Creates all required tables and columns safely.
# =============================================================================

def add_column_if_missing(cursor, table, column, column_def):
    cursor.execute("""
        SELECT COUNT(*) AS cnt FROM INFORMATION_SCHEMA.COLUMNS
        WHERE TABLE_SCHEMA = DATABASE() AND TABLE_NAME = %s AND COLUMN_NAME = %s
    """, (table, column))
    if cursor.fetchone()["cnt"] == 0:
        cursor.execute(f"ALTER TABLE `{table}` ADD COLUMN `{column}` {column_def}")
        print(f"[Migration] Added {table}.{column}")


def run_migrations():
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        # ── Core tables ───────────────────────────────────────────────────────

        # hostel table (needed for hostel_name in profile)
        cursor.execute("""CREATE TABLE IF NOT EXISTS hostel (
            hostel_id   INT AUTO_INCREMENT PRIMARY KEY,
            hostel_name VARCHAR(100) NOT NULL,
            location    VARCHAR(255)
        )""")

        # room table
        cursor.execute("""CREATE TABLE IF NOT EXISTS room (
            room_id        INT AUTO_INCREMENT PRIMARY KEY,
            hostel_id      INT,
            room_number    VARCHAR(20) NOT NULL,
            capacity       INT DEFAULT 2,
            available_beds INT DEFAULT 2,
            FOREIGN KEY (hostel_id) REFERENCES hostel(hostel_id)
        )""")

        # student table
        cursor.execute("""CREATE TABLE IF NOT EXISTS student (
            student_id    INT AUTO_INCREMENT PRIMARY KEY,
            name          VARCHAR(100) NOT NULL,
            email         VARCHAR(255) UNIQUE NOT NULL,
            password      VARCHAR(255) NOT NULL,
            phone_no      VARCHAR(20),
            room_id       INT,
            department    VARCHAR(100),
            semester      INT,
            year_of_study INT,
            guardian_name VARCHAR(100),
            address       TEXT,
            FOREIGN KEY (room_id) REFERENCES room(room_id)
        )""")

        # complaint table
        cursor.execute("""CREATE TABLE IF NOT EXISTS complaint (
            comp_id     INT AUTO_INCREMENT PRIMARY KEY,
            student_id  INT NOT NULL,
            room_id     INT,
            comp_type   VARCHAR(100) NOT NULL,
            description TEXT,
            comp_date   DATE NOT NULL,
            status      ENUM('Pending','In Progress','Resolved') DEFAULT 'Pending',
            response    TEXT,
            FOREIGN KEY (student_id) REFERENCES student(student_id)
        )""")

        # roomchangerequest table
        cursor.execute("""CREATE TABLE IF NOT EXISTS roomchangerequest (
            request_id  INT AUTO_INCREMENT PRIMARY KEY,
            student_id  INT NOT NULL,
            req_room_id INT DEFAULT NULL,
            req_date    DATE NOT NULL,
            reason      TEXT,
            status      ENUM('Pending','Approved','Rejected') DEFAULT 'Pending',
            FOREIGN KEY (student_id) REFERENCES student(student_id)
        )""")

        # applications table (for admission)
        cursor.execute("""CREATE TABLE IF NOT EXISTS applications (
            id                 INT AUTO_INCREMENT PRIMARY KEY,
            name               VARCHAR(100) NOT NULL,
            email              VARCHAR(255) UNIQUE NOT NULL,
            year               INT NOT NULL,
            distance_from_home INT NOT NULL,
            annual_income      DECIMAL(12,2) NOT NULL DEFAULT 0,
            sgpa               DECIMAL(4,2)  NOT NULL DEFAULT 0.00,
            guardian_name      VARCHAR(255)  NOT NULL DEFAULT '',
            emergency_contact  VARCHAR(20)   NOT NULL DEFAULT '',
            priority_score     DECIMAL(6,2)  NOT NULL DEFAULT 0,
            status             ENUM('Pending','Approved','Waiting','Rejected') DEFAULT 'Pending',
            applied_on         TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        # rooms table (used by allocation engine — separate from room table above)
        cursor.execute("""CREATE TABLE IF NOT EXISTS rooms (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            room_number    VARCHAR(20) NOT NULL,
            hostel_name    VARCHAR(100),
            capacity       INT DEFAULT 2,
            available_beds INT DEFAULT 2
        )""")

        # allocations table
        cursor.execute("""CREATE TABLE IF NOT EXISTS allocations (
            id             INT AUTO_INCREMENT PRIMARY KEY,
            application_id INT NOT NULL,
            room_id        INT NOT NULL,
            allocated_on   TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(id),
            FOREIGN KEY (room_id)        REFERENCES rooms(id)
        )""")

        # fee_transactions table
        cursor.execute("""CREATE TABLE IF NOT EXISTS fee_transactions (
            id            INT AUTO_INCREMENT PRIMARY KEY,
            student_id    INT NOT NULL,
            description   VARCHAR(255) NOT NULL,
            amount        DECIMAL(10,2) NOT NULL,
            status        ENUM('Paid','Pending') DEFAULT 'Pending',
            due_date      DATE,
            paid_date     DATE,
            created_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (student_id) REFERENCES student(student_id)
        )""")

        # attendance table
        cursor.execute("""CREATE TABLE IF NOT EXISTS attendance (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT NOT NULL,
            date       DATE NOT NULL,
            status     ENUM('Present','Absent','Late') NOT NULL,
            UNIQUE KEY unique_attendance (student_id, date),
            FOREIGN KEY (student_id) REFERENCES student(student_id)
        )""")

        # notifications table
        cursor.execute("""CREATE TABLE IF NOT EXISTS notifications (
            id         INT AUTO_INCREMENT PRIMARY KEY,
            student_id INT,
            title      VARCHAR(255) NOT NULL,
            message    TEXT NOT NULL,
            is_read    TINYINT(1) DEFAULT 0,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )""")

        db.commit()

        # ── Safe column additions (in case tables existed before) ─────────────
        add_column_if_missing(cursor, "applications", "annual_income",     "DECIMAL(12,2) NOT NULL DEFAULT 0")
        add_column_if_missing(cursor, "applications", "sgpa",              "DECIMAL(4,2) NOT NULL DEFAULT 0.00")
        add_column_if_missing(cursor, "applications", "guardian_name",     "VARCHAR(255) NOT NULL DEFAULT ''")
        add_column_if_missing(cursor, "applications", "emergency_contact", "VARCHAR(20) NOT NULL DEFAULT ''")

        # Fix priority_score type if it was INT
        cursor.execute("""
            SELECT DATA_TYPE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'applications' AND COLUMN_NAME = 'priority_score'
        """)
        row = cursor.fetchone()
        if row and row["DATA_TYPE"] == "int":
            cursor.execute("ALTER TABLE applications MODIFY COLUMN priority_score DECIMAL(6,2)")

        # roomchangerequest: make req_room_id nullable (fix the room_id=0 bug)
        cursor.execute("""
            SELECT IS_NULLABLE FROM INFORMATION_SCHEMA.COLUMNS
            WHERE TABLE_SCHEMA = DATABASE()
              AND TABLE_NAME = 'roomchangerequest' AND COLUMN_NAME = 'req_room_id'
        """)
        col = cursor.fetchone()
        if col and col["IS_NULLABLE"] == "NO":
            cursor.execute("ALTER TABLE roomchangerequest MODIFY COLUMN req_room_id INT DEFAULT NULL")

        db.commit()
        print("[HMS] All migrations complete.")

    except Exception as e:
        print(f"[Migration WARNING] {e} — continuing anyway.")
        try:
            db.rollback()
        except Exception:
            pass
    finally:
        cursor.close()
        db.close()

run_migrations()


# =============================================================================
#  SERVE HTML PAGES
# =============================================================================

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


# =============================================================================
#  LOGIN
#  FIX: Now returns year_of_study so the admission form priority score
#       calculation uses the correct year instead of always defaulting to 3.
# =============================================================================

@app.route("/login", methods=["POST"])
def login():
    data     = request.json
    email    = data.get("email", "").strip()
    password = data.get("password", "").strip()

    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT student_id AS id, name, email, phone_no, room_id,
               year_of_study AS year, department
        FROM student
        WHERE email = %s AND password = %s
    """, (email, password))
    user = cur.fetchone()
    cur.close()
    db.close()

    if user:
        user["role"] = "student"
        return jsonify({"success": True, "user": user})
    return jsonify({"success": False, "message": "Invalid email or password"}), 401


# =============================================================================
#  ADMISSION APPLICATION
#  POST /apply
# =============================================================================

@app.route("/apply", methods=["POST"])
def apply_hostel():
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        data = request.json
        required = ["name", "email", "year", "distance", "annual_income"]
        for field in required:
            if field not in data or data[field] is None or str(data[field]).strip() == "":
                return jsonify({"error": f"Missing required field: {field}"}), 400

        name              = str(data["name"]).strip()
        email             = str(data["email"]).strip().lower()
        year              = int(data["year"])
        distance          = int(data["distance"])
        annual_income     = float(data["annual_income"])
        sgpa_raw          = data.get("sgpa", 0)
        sgpa              = float(sgpa_raw) if sgpa_raw not in (None, "", "null") else 0.0
        guardian_name     = str(data.get("guardian_name", "")).strip()
        emergency_contact = str(data.get("emergency_contact", "")).strip()

        if not (1 <= year <= 6):
            return jsonify({"error": "Year must be between 1 and 6"}), 400
        if distance < 0:
            return jsonify({"error": "Distance cannot be negative"}), 400
        if annual_income < 0:
            return jsonify({"error": "Annual income cannot be negative"}), 400
        if not (0.0 <= sgpa <= 10.0):
            return jsonify({"error": "SGPA must be between 0.0 and 10.0"}), 400

        cursor.execute("SELECT id FROM applications WHERE email = %s", (email,))
        if cursor.fetchone():
            return jsonify({"message": "Application already submitted for this email"}), 400

        priority_score = calculate_priority(distance, annual_income, sgpa, year)
        cursor.execute("""
            INSERT INTO applications
                (name, email, year, distance_from_home, annual_income, sgpa,
                 guardian_name, emergency_contact, priority_score, status)
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,'Pending')
        """, (name, email, year, distance, annual_income, sgpa,
              guardian_name, emergency_contact, priority_score))
        db.commit()

        return jsonify({
            "message": "Application Submitted Successfully",
            "priority_score": priority_score
        })

    except (ValueError, TypeError):
        return jsonify({"error": "Invalid data types provided"}), 400
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


# =============================================================================
#  MY APPLICATION STATUS
#  GET /my-application?email=...
# =============================================================================

@app.route("/my-application", methods=["GET"])
def my_application():
    email = request.args.get("email", "").strip().lower()
    if not email:
        return jsonify({"error": "Email is required"}), 400

    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        cursor.execute("""
            SELECT a.id, a.name, a.email, a.year, a.distance_from_home,
                   a.annual_income, a.sgpa, a.priority_score, a.status,
                   r.room_number
            FROM applications a
            LEFT JOIN allocations al ON a.id = al.application_id
            LEFT JOIN rooms r        ON al.room_id = r.id
            WHERE a.email = %s
        """, (email,))
        result = cursor.fetchone()
        if not result:
            return jsonify({"error": "No application found"}), 404
        return jsonify(result)
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


# =============================================================================
#  ALLOCATION ENGINE
#  POST /allocate  (triggered by admin/warden)
# =============================================================================

@app.route("/allocate", methods=["POST"])
def allocate_rooms():
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        db.start_transaction()
        cursor.execute("""
            SELECT * FROM applications
            WHERE status = 'Pending' AND year >= 2 AND distance_from_home > 20
            ORDER BY priority_score DESC
        """)
        students  = cursor.fetchall()
        allocated = 0
        waitlisted = 0

        for student in students:
            cursor.execute("""
                SELECT * FROM rooms
                WHERE available_beds > 0
                ORDER BY room_number ASC
                LIMIT 1
            """)
            room = cursor.fetchone()
            if room:
                cursor.execute(
                    "INSERT INTO allocations (application_id, room_id) VALUES (%s,%s)",
                    (student["id"], room["id"])
                )
                cursor.execute(
                    "UPDATE rooms SET available_beds = available_beds - 1 WHERE id = %s",
                    (room["id"],)
                )
                cursor.execute(
                    "UPDATE applications SET status = 'Approved' WHERE id = %s",
                    (student["id"],)
                )
                allocated += 1
            else:
                cursor.execute(
                    "UPDATE applications SET status = 'Waiting' WHERE id = %s",
                    (student["id"],)
                )
                waitlisted += 1

        db.commit()
        return jsonify({
            "message":    "Allocation Complete",
            "allocated":  allocated,
            "waitlisted": waitlisted
        })
    except Exception as e:
        db.rollback()
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


# =============================================================================
#  COMPLAINTS
# =============================================================================

@app.route("/submit_complaint", methods=["POST"])
def submit_complaint():
    data        = request.json
    student_id  = data.get("student_id")
    room_id     = data.get("room_id") or None   # convert 0/empty to NULL
    comp_type   = data.get("comp_type", "General")
    description = data.get("description", "")

    db  = get_db()
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
    cur.close()
    db.close()
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
    cur.close()
    db.close()
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
    cur.close()
    db.close()
    return jsonify({"message": "Complaint resolved"})


# =============================================================================
#  ROOM CHANGE
#  FIX: req_room_id is stored as NULL instead of 0 to avoid
#       corrupting student.room_id when a request is approved.
# =============================================================================

@app.route("/room_change", methods=["POST"])
def room_change():
    data        = request.json
    student_id  = data.get("student_id")
    reason      = data.get("reason", "")
    # req_room_id from the frontend is always 0 (no specific room chosen)
    # store NULL so warden can assign the correct room on approval
    req_room_id = data.get("req_room_id") or None

    if not student_id:
        return jsonify({"message": "Missing student_id"}), 400

    db  = get_db()
    cur = db.cursor()
    cur.execute(
        "INSERT INTO roomchangerequest (student_id, req_room_id, req_date, reason, status) VALUES (%s,%s,%s,%s,%s)",
        (student_id, req_room_id, date.today(), reason, "Pending")
    )
    db.commit()
    request_id = cur.lastrowid
    cur.close()
    db.close()
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
    cur.close()
    db.close()
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
    cur.close()
    db.close()
    return jsonify({"requests": requests})


@app.route("/warden/approve_room_change", methods=["POST"])
def approve_room_change():
    data       = request.json
    request_id = data.get("request_id")
    action     = data.get("action")
    # Warden must now supply the actual new_room_id when approving
    new_room_id = data.get("new_room_id")

    if not request_id or action not in ("Approved", "Rejected"):
        return jsonify({"message": "Invalid request"}), 400

    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute(
        "UPDATE roomchangerequest SET status=%s WHERE request_id=%s",
        (action, request_id)
    )
    if action == "Approved" and new_room_id:
        cur.execute(
            "SELECT student_id FROM roomchangerequest WHERE request_id=%s",
            (request_id,)
        )
        row = cur.fetchone()
        if row:
            cur.execute(
                "UPDATE student SET room_id=%s WHERE student_id=%s",
                (new_room_id, row["student_id"])
            )
            cur.execute(
                "UPDATE roomchangerequest SET req_room_id=%s WHERE request_id=%s",
                (new_room_id, request_id)
            )
    db.commit()
    cur.close()
    db.close()
    return jsonify({"message": f"Request {action.lower()} successfully"})


# =============================================================================
#  STUDENT DASHBOARD
#  FIX: Now queries fee_transactions and attendance tables for real data.
# =============================================================================

@app.route("/student/dashboard/<int:student_id>", methods=["GET"])
def student_dashboard(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)

    # Active complaints count
    cur.execute(
        "SELECT COUNT(*) AS cnt FROM complaint WHERE student_id=%s AND status != 'Resolved'",
        (student_id,)
    )
    active_complaints = cur.fetchone()["cnt"]

    # Fee status — sum of pending fees
    cur.execute("""
        SELECT COALESCE(SUM(amount), 0) AS total_due
        FROM fee_transactions
        WHERE student_id = %s AND status = 'Pending'
    """, (student_id,))
    fee_row   = cur.fetchone()
    total_due = float(fee_row["total_due"])
    fee_status = "Overdue" if total_due > 0 else "Paid"

    # Attendance — current month
    cur.execute("""
        SELECT
            COUNT(*) AS total_days,
            SUM(CASE WHEN status = 'Present' THEN 1 ELSE 0 END) AS present_days
        FROM attendance
        WHERE student_id = %s
          AND MONTH(date) = MONTH(CURDATE())
          AND YEAR(date)  = YEAR(CURDATE())
    """, (student_id,))
    att = cur.fetchone()
    total_days   = int(att["total_days"])   if att["total_days"]   else 0
    present_days = int(att["present_days"]) if att["present_days"] else 0
    attendance_pct = round((present_days / total_days * 100), 1) if total_days > 0 else 0

    # Timeline — last 5 events across complaints + room changes
    cur.execute("""
        SELECT comp_date AS event_date,
               CONCAT('Complaint: ', comp_type, ' — ', status) AS event
        FROM complaint WHERE student_id = %s
        UNION ALL
        SELECT req_date AS event_date,
               CONCAT('Room Change Request — ', status) AS event
        FROM roomchangerequest WHERE student_id = %s
        ORDER BY event_date DESC LIMIT 5
    """, (student_id, student_id))
    timeline = [{"event": r["event"], "date": str(r["event_date"])} for r in cur.fetchall()]

    cur.close()
    db.close()

    return jsonify({
        "fee_status":        fee_status,
        "fee_amount":        total_due,
        "attendance_pct":    attendance_pct,
        "present_days":      present_days,
        "total_days":        total_days,
        "active_complaints": int(active_complaints),
        "timeline":          timeline
    })


# =============================================================================
#  STUDENT PROFILE
#  FIX: Now also returns hostel_name so the profile page stat shows correctly.
# =============================================================================

@app.route("/student/profile/<int:student_id>", methods=["GET"])
def student_profile(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT s.student_id, s.name, s.email, s.phone_no,
               s.department, s.semester, s.year_of_study,
               s.guardian_name, s.address,
               r.room_number,
               h.hostel_name
        FROM student s
        LEFT JOIN room   r ON s.room_id   = r.room_id
        LEFT JOIN hostel h ON r.hostel_id = h.hostel_id
        WHERE s.student_id = %s
    """, (student_id,))
    profile = cur.fetchone()
    cur.close()
    db.close()
    if not profile:
        return jsonify({"message": "Student not found"}), 404
    return jsonify({"profile": profile})


# =============================================================================
#  FEE TRANSACTIONS  (student-facing)
#  GET /student/fees/<student_id>
# =============================================================================

@app.route("/student/fees/<int:student_id>", methods=["GET"])
def student_fees(student_id):
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT id, description, amount, status, due_date, paid_date
        FROM fee_transactions
        WHERE student_id = %s
        ORDER BY created_at DESC
    """, (student_id,))
    transactions = cur.fetchall()
    for t in transactions:
        if t["due_date"]:  t["due_date"]  = str(t["due_date"])
        if t["paid_date"]: t["paid_date"] = str(t["paid_date"])
    cur.close()
    db.close()
    return jsonify({"transactions": transactions})


# =============================================================================
#  ATTENDANCE  (student-facing)
#  GET /student/attendance/<student_id>?month=1&year=2026
# =============================================================================

@app.route("/student/attendance/<int:student_id>", methods=["GET"])
def student_attendance(student_id):
    month = request.args.get("month", date.today().month)
    year  = request.args.get("year",  date.today().year)
    db  = get_db()
    cur = db.cursor(dictionary=True)
    cur.execute("""
        SELECT date, status FROM attendance
        WHERE student_id = %s
          AND MONTH(date) = %s AND YEAR(date) = %s
        ORDER BY date ASC
    """, (student_id, month, year))
    records = cur.fetchall()
    for r in records:
        r["date"] = str(r["date"])

    # Summary counts
    cur.execute("""
        SELECT
            COUNT(*) AS total_days,
            SUM(CASE WHEN status='Present' THEN 1 ELSE 0 END) AS present_days,
            SUM(CASE WHEN status='Absent'  THEN 1 ELSE 0 END) AS absent_days,
            SUM(CASE WHEN status='Late'    THEN 1 ELSE 0 END) AS late_days
        FROM attendance
        WHERE student_id = %s
          AND MONTH(date) = %s AND YEAR(date) = %s
    """, (student_id, month, year))
    summary = cur.fetchone()
    total   = int(summary["total_days"])   if summary["total_days"]   else 0
    present = int(summary["present_days"]) if summary["present_days"] else 0
    absent  = int(summary["absent_days"])  if summary["absent_days"]  else 0
    late    = int(summary["late_days"])    if summary["late_days"]    else 0
    pct     = round(present / total * 100, 1) if total > 0 else 0

    cur.close()
    db.close()
    return jsonify({
        "records":      records,
        "total_days":   total,
        "present_days": present,
        "absent_days":  absent,
        "late_days":    late,
        "attendance_pct": pct
    })


# =============================================================================
#  ADMIN ROUTES
# =============================================================================

@app.route("/admin/applications", methods=["GET"])
def admin_view_applications():
    db     = get_db()
    cursor = db.cursor(dictionary=True)
    try:
        status_filter = request.args.get("status")
        query = """
            SELECT a.id, a.name, a.email, a.year, a.distance_from_home,
                   a.annual_income, a.sgpa, a.priority_score, a.status,
                   r.room_number
            FROM applications a
            LEFT JOIN allocations al ON a.id = al.application_id
            LEFT JOIN rooms r        ON al.room_id = r.id
            {where}
            ORDER BY a.priority_score DESC
        """
        if status_filter:
            cursor.execute(query.format(where="WHERE a.status = %s"), (status_filter,))
        else:
            cursor.execute(query.format(where=""))
        return jsonify(cursor.fetchall())
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        cursor.close()
        db.close()


# =============================================================================
if __name__ == "__main__":
    app.run(debug=True, port=5000)