from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_bcrypt import Bcrypt
from flask_jwt_extended import (
    JWTManager, create_access_token, jwt_required, get_jwt_identity
)
import mysql.connector
from config import Config

# -------------------------
# CREATE APP
# -------------------------
app = Flask(__name__)
app.config.from_object(Config)
CORS(app)

bcrypt = Bcrypt(app)
jwt = JWTManager(app)

# -------------------------
# DATABASE CONNECTION FUNCTION
# -------------------------
def get_db_connection():
    return mysql.connector.connect(
        host=app.config['DB_HOST'],
        user=app.config['DB_USER'],
        password=app.config['DB_PASSWORD'],
        database=app.config['DB_NAME']
    )

# -------------------------
# IMPORT BLUEPRINTS
# -------------------------
from routes.admin import admin_bp
from routes.warden import warden_bp
from routes.student import student_bp

app.register_blueprint(admin_bp)
app.register_blueprint(warden_bp)
app.register_blueprint(student_bp)

# -------------------------
# REGISTER API
# -------------------------
@app.route('/register', methods=['POST'])
def register():
    data = request.get_json()

    name = data['name']
    email = data['email']
    password = data['password']
    role = data.get('role', 'student')

    hashed_password = bcrypt.generate_password_hash(password).decode('utf-8')

    conn = get_db_connection()
    cursor = conn.cursor()

    try:
        cursor.execute("""
            INSERT INTO users (name, email, password, role)
            VALUES (%s, %s, %s, %s)
        """, (name, email, hashed_password, role))

        conn.commit()
        return jsonify({"message": "User registered successfully"}), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 400

    finally:
        cursor.close()
        conn.close()


# -------------------------
# LOGIN API
# -------------------------
@app.route('/login', methods=['POST'])
def login():
    if request.is_json:
        data = request.get_json()
        email = data['email']
        password = data['password']
    else:
        email = request.form['email']
        password = request.form['password']

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT id, password, role FROM users WHERE email=%s", (email,))
    user = cursor.fetchone()

    cursor.close()
    conn.close()

    if user and bcrypt.check_password_hash(user[1], password):
        access_token = create_access_token(identity={
            "id": user[0],
            "role": user[2]
        })
        return jsonify({
            "message": "Login successful",
            "token": access_token
        }), 200

    return jsonify({"error": "Invalid credentials"}), 401


# -------------------------
# PROTECTED ROUTE
# -------------------------
@app.route('/dashboard', methods=['GET'])
@jwt_required()
def dashboard():
    current_user = get_jwt_identity()
    return jsonify({
        "message": "Welcome!",
        "user": current_user
    })


if __name__ == "__main__":
    app.run(debug=True)