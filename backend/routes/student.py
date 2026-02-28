from flask import Blueprint, jsonify
from flask_jwt_extended import jwt_required, get_jwt_identity
from db import get_db_connection

student_bp = Blueprint('student', __name__)

@student_bp.route('/student/profile', methods=['GET'])
@jwt_required()
def get_student_profile():
    current_user = get_jwt_identity()

    if current_user['role'] != 'student':
        return jsonify({"error": "Access denied"}), 403

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT id, name, email FROM users WHERE id = %s",
        (current_user['id'],)
    )

    student = cursor.fetchone()

    cursor.close()
    conn.close()

    if not student:
        return jsonify({"error": "Student not found"}), 404

    return jsonify({
        "id": student[0],
        "name": student[1],
        "email": student[2]
    })