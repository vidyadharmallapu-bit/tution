import csv
import io
import os
import sqlite3
from datetime import datetime
from flask import (
    Flask,
    render_template,
    request,
    redirect,
    url_for,
    flash,
    session,
    send_file,
)
from config import Config
from database import get_db_connection, init_db
import smtplib
from email.message import EmailMessage

app = Flask(__name__)
app.config.from_object(Config)

init_db()


def send_email(subject: str, body: str, recipient: str) -> bool:
    if not app.config["MAIL_USERNAME"] or not app.config["MAIL_PASSWORD"]:
        return False

    message = EmailMessage()
    message["Subject"] = subject
    message["From"] = app.config["MAIL_USERNAME"]
    message["To"] = recipient
    message.set_content(body)

    try:
        with smtplib.SMTP(app.config["MAIL_SERVER"], app.config["MAIL_PORT"]) as smtp:
            if app.config["MAIL_USE_TLS"]:
                smtp.starttls()
            smtp.login(app.config["MAIL_USERNAME"], app.config["MAIL_PASSWORD"])
            smtp.send_message(message)
        return True
    except Exception as exc:
        app.logger.error("Error sending email: %s", exc)
        return False


def validate_registration(form_data):
    errors = []
    name = form_data.get("studentName", "").strip()
    parent = form_data.get("parentName", "").strip()
    phone = form_data.get("phone", "").strip()
    email = form_data.get("email", "").strip()
    class_level = form_data.get("classLevel", "").strip()
    school = form_data.get("schoolName", "").strip()
    address = form_data.get("address", "").strip()

    if not name:
        errors.append("Student name is required.")
    if not parent:
        errors.append("Parent name is required.")
    if not phone or not phone.isdigit() or len(phone) != 10:
        errors.append("Enter a valid 10-digit phone number.")
    if not email or "@" not in email or "." not in email:
        errors.append("Enter a valid email address.")
    if class_level not in [str(x) for x in range(3, 11)]:
        errors.append("Select a valid class level.")
    if not school:
        errors.append("School name is required.")
    if not address:
        errors.append("Address is required.")

    return errors


def student_exists(email, phone):
    query = "SELECT 1 FROM students WHERE email = ? OR phone = ? LIMIT 1"
    with get_db_connection() as conn:
        row = conn.execute(query, (email, phone)).fetchone()
        return bool(row)


def save_student(data):
    query = """
    INSERT INTO students (student_name, parent_name, phone, email, class_level, school_name, address, registered_at)
    VALUES (?, ?, ?, ?, ?, ?, ?, ?)
    """
    with get_db_connection() as conn:
        conn.execute(
            query,
            (
                data["student_name"],
                data["parent_name"],
                data["phone"],
                data["email"],
                data["class_level"],
                data["school_name"],
                data["address"],
                data["registered_at"],
            ),
        )
        conn.commit()


def get_dashboard_stats():
    today = datetime.now().date()
    month_start = today.replace(day=1)

    with get_db_connection() as conn:
        total = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM students WHERE DATE(registered_at) = ?", (today.isoformat(),)
        ).fetchone()[0]
        month_count = conn.execute(
            "SELECT COUNT(*) FROM students WHERE DATE(registered_at) >= ?", (month_start.isoformat(),)
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT * FROM students ORDER BY registered_at DESC LIMIT 10"
        ).fetchall()

    return {
        "total": total,
        "today": today_count,
        "month": month_count,
        "recent": recent,
    }


def query_students(search=None, class_filter=None, page=1, per_page=10):
    offset = (page - 1) * per_page
    conditions = []
    params = []

    if search:
        conditions.append("(student_name LIKE ? OR parent_name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        search_term = f"%{search}%"
        params.extend([search_term] * 4)

    if class_filter:
        conditions.append("class_level = ?")
        params.append(class_filter)

    where_clause = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    query = f"SELECT * FROM students {where_clause} ORDER BY registered_at DESC LIMIT ? OFFSET ?"
    count_query = f"SELECT COUNT(*) FROM students {where_clause}"

    with get_db_connection() as conn:
        rows = conn.execute(query, (*params, per_page, offset)).fetchall()
        total = conn.execute(count_query, params).fetchone()[0]

    return rows, total


def export_csv(students):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow([
        "ID",
        "Student Name",
        "Parent Name",
        "Phone",
        "Email",
        "Class Level",
        "School Name",
        "Address",
        "Registered At",
    ])

    for student in students:
        writer.writerow([
            student["id"],
            student["student_name"],
            student["parent_name"],
            student["phone"],
            student["email"],
            student["class_level"],
            student["school_name"],
            student["address"],
            student["registered_at"],
        ])

    output.seek(0)
    return output


def export_excel(students):
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter

        workbook = openpyxl.Workbook()
        sheet = workbook.active
        sheet.title = "Registrations"
        headers = [
            "ID",
            "Student Name",
            "Parent Name",
            "Phone",
            "Email",
            "Class Level",
            "School Name",
            "Address",
            "Registered At",
        ]
        sheet.append(headers)

        for student in students:
            sheet.append([
                student["id"],
                student["student_name"],
                student["parent_name"],
                student["phone"],
                student["email"],
                student["class_level"],
                student["school_name"],
                student["address"],
                student["registered_at"],
            ])

        for i, _ in enumerate(headers, start=1):
            sheet.column_dimensions[get_column_letter(i)].width = 18

        output = io.BytesIO()
        workbook.save(output)
        output.seek(0)
        return output
    except ImportError:
        return None


@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        errors = validate_registration(request.form)
        if errors:
            flash(" ".join(errors), "danger")
            return redirect(url_for("home") + "#register")

        student_data = {
            "student_name": request.form["studentName"].strip(),
            "parent_name": request.form["parentName"].strip(),
            "phone": request.form["phone"].strip(),
            "email": request.form["email"].strip(),
            "class_level": request.form["classLevel"].strip(),
            "school_name": request.form["schoolName"].strip(),
            "address": request.form["address"].strip(),
            "registered_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }

        if student_exists(student_data["email"], student_data["phone"]):
            flash("A student with this email or phone number already exists.", "warning")
            return redirect(url_for("home") + "#register")

        save_student(student_data)

        owner_subject = "New Student Registration"
        owner_body = (
            f"A new student has registered.\n\n"
            f"Student Name: {student_data['student_name']}\n"
            f"Parent Name: {student_data['parent_name']}\n"
            f"Phone: {student_data['phone']}\n"
            f"Email: {student_data['email']}\n"
            f"Class: {student_data['class_level']}\n"
            f"School: {student_data['school_name']}\n"
            f"Address: {student_data['address']}\n"
            f"Registration Time: {student_data['registered_at']}\n"
        )
        owner_email_sent = send_email(owner_subject, owner_body, app.config["OWNER_EMAIL"])

        student_subject = "Registration Successful"
        student_body = (
            f"Dear {student_data['student_name']},\n\n"
            f"Thank you for registering with Bright Future Tuition Center.\n\n"
            f"We have successfully received your registration.\n\n"
            f"Our team will contact you shortly.\n\n"
            f"Regards,\n"
            f"Bright Future Tuition Center\n"
        )
        student_email_sent = send_email(student_subject, student_body, student_data["email"])

        if owner_email_sent and student_email_sent:
            flash("Registration successful. Confirmation email has been sent.", "success")
        elif owner_email_sent or student_email_sent:
            flash(
                "Registration successful. Some email notifications could not be sent. Please verify your email settings.",
                "warning",
            )
        else:
            flash(
                "Registration successful, but email notifications failed. Please check SMTP configuration.",
                "warning",
            )

        return redirect(url_for("home") + "#register")

    return render_template("index.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()

        if (
            username == app.config["ADMIN_USERNAME"]
            and password == app.config["ADMIN_PASSWORD"]
        ):
            session["admin_logged_in"] = True
            return redirect(url_for("admin_dashboard"))

        flash("Invalid username or password.", "danger")

    return render_template("admin_login.html")


@app.route("/admin/logout")
def admin_logout():
    session.pop("admin_logged_in", None)
    return redirect(url_for("admin_login"))


@app.route("/admin")
def admin_dashboard():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    search = request.args.get("search", "").strip()
    class_filter = request.args.get("class_filter", "").strip()
    page = int(request.args.get("page", 1))
    per_page = app.config["PER_PAGE"]

    students, total = query_students(search, class_filter, page, per_page)
    total_pages = (total + per_page - 1) // per_page
    stats = get_dashboard_stats()

    return render_template(
        "admin.html",
        students=students,
        total=total,
        page=page,
        total_pages=total_pages,
        search=search,
        class_filter=class_filter,
        stats=stats,
    )


@app.route("/admin/delete/<int:student_id>")
def admin_delete(student_id):
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    with get_db_connection() as conn:
        conn.execute("DELETE FROM students WHERE id = ?", (student_id,))
        conn.commit()

    flash("Registration deleted successfully.", "success")
    return redirect(url_for("admin_dashboard"))


@app.route("/admin/export/csv")
def admin_export_csv():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    students, _ = query_students()
    output = export_csv(students)
    return send_file(
        io.BytesIO(output.getvalue().encode("utf-8")),
        mimetype="text/csv",
        as_attachment=True,
        download_name="students.csv",
    )


@app.route("/admin/export/excel")
def admin_export_excel():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    students, _ = query_students()
    workbook = export_excel(students)
    if workbook is None:
        flash("Excel export is not available. Install openpyxl.", "warning")
        return redirect(url_for("admin_dashboard"))

    return send_file(
        workbook,
        mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        as_attachment=True,
        download_name="students.xlsx",
    )


@app.route("/admin/print")
def admin_print():
    if not session.get("admin_logged_in"):
        return redirect(url_for("admin_login"))

    students, _ = query_students()
    return render_template("admin_print.html", students=students)


if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
