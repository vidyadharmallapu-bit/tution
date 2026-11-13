import csv
import io
import os
import sys
import sqlite3
from datetime import datetime
from pathlib import Path

# ---------------------------------------------------------------------------
# Make sure our project/ package is importable when Vercel runs from /api
# ---------------------------------------------------------------------------
ROOT_DIR = Path(__file__).resolve().parent.parent
PROJECT_DIR = ROOT_DIR / "project"
if str(PROJECT_DIR) not in sys.path:
    sys.path.insert(0, str(PROJECT_DIR))

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
from dotenv import load_dotenv

# Load .env if it exists (local dev only; use Vercel env vars in production)
env_file = ROOT_DIR / "project" / ".env"
if env_file.exists():
    load_dotenv(env_file)

# ---------------------------------------------------------------------------
# App setup
# ---------------------------------------------------------------------------
app = Flask(
    __name__,
    template_folder=str(PROJECT_DIR / "templates"),
    static_folder=str(PROJECT_DIR / "static"),
    static_url_path="/static",
)

app.secret_key = os.environ.get("SECRET_KEY", "change-this-secret-key")

# ---------------------------------------------------------------------------
# Config values from environment variables
# ---------------------------------------------------------------------------
MAIL_SERVER   = os.environ.get("MAIL_SERVER",   "smtp.gmail.com")
MAIL_PORT     = int(os.environ.get("MAIL_PORT", 587))
MAIL_USE_TLS  = os.environ.get("MAIL_USE_TLS",  "True").lower() in ("true", "1", "yes")
MAIL_USERNAME = os.environ.get("MAIL_USERNAME")
MAIL_PASSWORD = os.environ.get("MAIL_PASSWORD")
OWNER_EMAIL   = os.environ.get("OWNER_EMAIL",   "kkrishnakumar86@gmail.com")
OWNER_NAME    = os.environ.get("OWNER_NAME",    "Dr. Krishna Kumar")
ADMIN_USERNAME = os.environ.get("ADMIN_USERNAME", "admin")
ADMIN_PASSWORD = os.environ.get("ADMIN_PASSWORD", "admin123")
PER_PAGE      = int(os.environ.get("PER_PAGE",  10))

# ---------------------------------------------------------------------------
# Database – stored in /tmp on Vercel (ephemeral, resets on each cold start)
# ---------------------------------------------------------------------------
DB_PATH = Path(os.environ.get("DATABASE_PATH", "/tmp/students.db"))


def get_db_connection():
    conn = sqlite3.connect(str(DB_PATH))
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    with get_db_connection() as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS students (
                id            INTEGER PRIMARY KEY AUTOINCREMENT,
                student_name  TEXT NOT NULL,
                parent_name   TEXT NOT NULL,
                phone         TEXT NOT NULL UNIQUE,
                email         TEXT NOT NULL UNIQUE,
                class_level   TEXT NOT NULL,
                school_name   TEXT NOT NULL,
                address       TEXT NOT NULL,
                registered_at TEXT NOT NULL
            )
            """
        )
        conn.commit()


init_db()

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------
import smtplib
from email.message import EmailMessage


def send_email(subject: str, body: str, recipient: str) -> bool:
    if not MAIL_USERNAME or not MAIL_PASSWORD:
        return False
    message = EmailMessage()
    message["Subject"] = subject
    message["From"]    = MAIL_USERNAME
    message["To"]      = recipient
    message.set_content(body)
    try:
        with smtplib.SMTP(MAIL_SERVER, MAIL_PORT) as smtp:
            if MAIL_USE_TLS:
                smtp.starttls()
            smtp.login(MAIL_USERNAME, MAIL_PASSWORD)
            smtp.send_message(message)
        return True
    except Exception as exc:
        app.logger.error("Error sending email: %s", exc)
        return False


def validate_registration(form_data):
    errors = []
    name        = form_data.get("studentName",  "").strip()
    parent      = form_data.get("parentName",   "").strip()
    phone       = form_data.get("phone",        "").strip()
    email       = form_data.get("email",        "").strip()
    class_level = form_data.get("classLevel",   "").strip()
    school      = form_data.get("schoolName",   "").strip()
    address     = form_data.get("address",      "").strip()

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
    with get_db_connection() as conn:
        row = conn.execute(
            "SELECT 1 FROM students WHERE email = ? OR phone = ? LIMIT 1",
            (email, phone),
        ).fetchone()
        return bool(row)


def save_student(data):
    with get_db_connection() as conn:
        conn.execute(
            """INSERT INTO students
               (student_name, parent_name, phone, email, class_level, school_name, address, registered_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
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
    today       = datetime.now().date()
    month_start = today.replace(day=1)
    with get_db_connection() as conn:
        total       = conn.execute("SELECT COUNT(*) FROM students").fetchone()[0]
        today_count = conn.execute(
            "SELECT COUNT(*) FROM students WHERE DATE(registered_at) = ?",
            (today.isoformat(),),
        ).fetchone()[0]
        month_count = conn.execute(
            "SELECT COUNT(*) FROM students WHERE DATE(registered_at) >= ?",
            (month_start.isoformat(),),
        ).fetchone()[0]
        recent = conn.execute(
            "SELECT * FROM students ORDER BY registered_at DESC LIMIT 10"
        ).fetchall()
    return {"total": total, "today": today_count, "month": month_count, "recent": recent}


def query_students(search=None, class_filter=None, page=1, per_page=PER_PAGE):
    offset     = (page - 1) * per_page
    conditions = []
    params     = []

    if search:
        conditions.append("(student_name LIKE ? OR parent_name LIKE ? OR email LIKE ? OR phone LIKE ?)")
        t = f"%{search}%"
        params.extend([t] * 4)

    if class_filter:
        conditions.append("class_level = ?")
        params.append(class_filter)

    where = f"WHERE {' AND '.join(conditions)}" if conditions else ""
    with get_db_connection() as conn:
        rows  = conn.execute(
            f"SELECT * FROM students {where} ORDER BY registered_at DESC LIMIT ? OFFSET ?",
            (*params, per_page, offset),
        ).fetchall()
        total = conn.execute(f"SELECT COUNT(*) FROM students {where}", params).fetchone()[0]
    return rows, total


def export_csv(students):
    output = io.StringIO()
    writer = csv.writer(output)
    writer.writerow(["ID","Student Name","Parent Name","Phone","Email","Class Level","School Name","Address","Registered At"])
    for s in students:
        writer.writerow([s["id"],s["student_name"],s["parent_name"],s["phone"],s["email"],s["class_level"],s["school_name"],s["address"],s["registered_at"]])
    output.seek(0)
    return output


def export_excel(students):
    try:
        import openpyxl
        from openpyxl.utils import get_column_letter
        wb = openpyxl.Workbook()
        ws = wb.active
        ws.title = "Registrations"
        headers = ["ID","Student Name","Parent Name","Phone","Email","Class Level","School Name","Address","Registered At"]
        ws.append(headers)
        for s in students:
            ws.append([s["id"],s["student_name"],s["parent_name"],s["phone"],s["email"],s["class_level"],s["school_name"],s["address"],s["registered_at"]])
        for i in range(1, len(headers) + 1):
            ws.column_dimensions[get_column_letter(i)].width = 18
        out = io.BytesIO()
        wb.save(out)
        out.seek(0)
        return out
    except ImportError:
        return None

# ---------------------------------------------------------------------------
# Routes
# ---------------------------------------------------------------------------

@app.route("/", methods=["GET", "POST"])
def home():
    if request.method == "POST":
        errors = validate_registration(request.form)
        if errors:
            flash(" ".join(errors), "danger")
            return redirect(url_for("home") + "#register")

        student_data = {
            "student_name": request.form["studentName"].strip(),
            "parent_name":  request.form["parentName"].strip(),
            "phone":        request.form["phone"].strip(),
            "email":        request.form["email"].strip(),
            "class_level":  request.form["classLevel"].strip(),
            "school_name":  request.form["schoolName"].strip(),
            "address":      request.form["address"].strip(),
            "registered_at": datetime.now().isoformat(sep=" ", timespec="seconds"),
        }

        if student_exists(student_data["email"], student_data["phone"]):
            flash("A student with this email or phone number already exists.", "warning")
            return redirect(url_for("home") + "#register")

        save_student(student_data)

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
        owner_sent = send_email("New Student Registration", owner_body, OWNER_EMAIL)
        student_body = (
            f"Dear {student_data['student_name']},\n\n"
            f"Thank you for registering with Bright Future Tuition Center.\n\n"
            f"We have successfully received your registration.\n\n"
            f"Our team will contact you shortly.\n\n"
            f"Regards,\nBright Future Tuition Center\n"
        )
        student_sent = send_email("Registration Successful", student_body, student_data["email"])

        if owner_sent and student_sent:
            flash("Registration successful. Confirmation email has been sent.", "success")
        elif owner_sent or student_sent:
            flash("Registration successful. Some email notifications could not be sent.", "warning")
        else:
            flash("Registration successful, but email notifications failed. Check SMTP config.", "warning")

        return redirect(url_for("home") + "#register")

    return render_template("index.html")


@app.route("/admin/login", methods=["GET", "POST"])
def admin_login():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "").strip()
        if username == ADMIN_USERNAME and password == ADMIN_PASSWORD:
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
    search       = request.args.get("search",       "").strip()
    class_filter = request.args.get("class_filter", "").strip()
    page         = int(request.args.get("page", 1))
    students, total = query_students(search, class_filter, page)
    total_pages  = (total + PER_PAGE - 1) // PER_PAGE
    stats        = get_dashboard_stats()
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


# ---------------------------------------------------------------------------
# Vercel entry-point – the WSGI app object must be named `app`
# ---------------------------------------------------------------------------
# Vercel's @vercel/python builder automatically detects the `app` variable.

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)

