from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager,
    create_access_token,
    jwt_required,
    get_jwt_identity
)
from config import Config
from db import get_db_connection

# -------------------------
# CREATE APP
# -------------------------
app = Flask(__name__)
app.config.from_object(Config)

CORS(app)
bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# =====================================================
# 🔐 REGISTER
# =====================================================
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    name = data.get('name')
    email = data.get('email')
    password = data.get('password')
    role = data.get('role', 'student')

    if not name or not email or not password:
        return jsonify({"error": "All fields required"}), 400

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    try:
        conn = get_db_connection()
        cursor = conn.cursor()

        cursor.execute(
            "INSERT INTO users (name, email, password, role) VALUES (%s, %s, %s, %s)",
            (name, email, hashed_password, role)
        )

        conn.commit()
        cursor.close()
        conn.close()

        return jsonify({"message": "User registered successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400


# =====================================================
# 🔐 LOGIN
# =====================================================
@app.route('/login', methods=['POST'])
def login():
    data = request.get_json()

    email = data.get('email')
    password = data.get('password')

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, password, role FROM users WHERE email=%s",
        (email,)
    )
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 401

    if not bcrypt.check_password_hash(user['password'], password):
        return jsonify({"error": "Invalid password"}), 401

    access_token = create_access_token(identity={
        "id": user['id'],
        "role": user['role']
    })

    return jsonify({
        "message": "Login successful",
        "token": access_token,
        "role": user['role']
    })


# =====================================================
# 🎓 STUDENT ROUTES
# =====================================================
@app.route('/student/me', methods=['GET'])
@jwt_required()
def student_profile():
    current_user = get_jwt_identity()

    if current_user.get('role') != 'student':
        return jsonify({"error": "Access denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, name, email, role FROM users WHERE id=%s",
        (current_user['id'],)
    )
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if not user:
        return jsonify({"error": "User not found"}), 404

    return jsonify(user)


# =====================================================
# 👮 WARDEN ROUTES
# =====================================================
@app.route('/warden/students', methods=['GET'])
@jwt_required()
def warden_students():
    current_user = get_jwt_identity()

    if current_user.get('role') != 'warden':
        return jsonify({"error": "Access denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT id, name, email FROM users WHERE role='student'"
    )

    students = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(students)


# =====================================================
# 👑 ADMIN ROUTES
# =====================================================
@app.route('/admin/users', methods=['GET'])
@jwt_required()
def admin_users():
    current_user = get_jwt_identity()

    if current_user.get('role') != 'admin':
        return jsonify({"error": "Access denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT id, name, email, role FROM users")
    users = cursor.fetchall()

    cursor.close()
    conn.close()

    return jsonify(users)


# =====================================================
# 🚀 RUN APP
# =====================================================
if __name__ == "__main__":
    app.run(debug=True)