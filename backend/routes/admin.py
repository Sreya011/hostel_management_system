from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_db_connection

admin_bp = Blueprint('admin', __name__)

@admin_bp.route('/admin/users', methods=['GET'])
@jwt_required()
def get_users():
    current_user = get_jwt_identity()

    # Role check
    if current_user.get('role') != 'admin':
        return jsonify({"error": "Access denied"}), 403

    try:
        conn = get_db_connection()
        cursor = conn.cursor(dictionary=True)

        cursor.execute("SELECT id, name, email, role FROM users")
        users = cursor.fetchall()

        return jsonify(users), 200

    except Exception as e:
        return jsonify({"error": str(e)}), 500

    finally:
        cursor.close()
        conn.close()