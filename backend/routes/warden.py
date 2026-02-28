from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_db_connection

warden_bp = Blueprint('warden', __name__)

@warden_bp.route('/warden/students', methods=['GET'])
@jwt_required()
def view_students():
    current_user = get_jwt_identity()

    if current_user.get('role') != 'warden':
        return jsonify({"error": "Access denied"}), 403

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("""
            SELECT id, name, email
            FROM users
            WHERE role = 'student'
        """)

        students = cursor.fetchall()
        return jsonify(students), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()