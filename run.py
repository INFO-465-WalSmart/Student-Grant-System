from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
from datetime import datetime, timedelta
from pathlib import Path
import random
import os
import smtplib
from email.message import EmailMessage
from dotenv import load_dotenv

load_dotenv()

app = Flask(__name__)
app.secret_key = "studentgrantsecret"
app.config["TEMPLATES_AUTO_RELOAD"] = True

BASE_DIR = Path(__file__).resolve().parent
DB_PATH = BASE_DIR / "student_grants.db"

ADMIN_EMAIL = os.getenv("ADMIN_EMAIL", "adammorkous7@gmail.com")


def get_db_connection():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def send_email(to_email, subject, body):
    email_user = os.getenv("EMAIL_USER")
    email_password = os.getenv("EMAIL_PASSWORD")

    if not email_user or not email_password:
        print("Email not configured. Check EMAIL_USER and EMAIL_PASSWORD in .env")
        return False

    if not to_email or "@" not in to_email:
        print(f"Email not sent. Invalid recipient: {to_email}")
        return False

    msg = EmailMessage()
    msg["Subject"] = subject
    msg["From"] = email_user
    msg["To"] = to_email
    msg.set_content(body)

    try:
        with smtplib.SMTP_SSL("smtp.gmail.com", 465) as smtp:
            smtp.login(email_user, email_password)
            smtp.send_message(msg)
        print(f"Email sent to {to_email}")
        return True
    except Exception as e:
        print("Email failed:", e)
        return False


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def table_columns(table_name):
    conn = get_db_connection()
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    conn.close()
    return cols


def add_column_if_missing(table_name, column_name, column_definition):
    conn = get_db_connection()
    cols = [row["name"] for row in conn.execute(f"PRAGMA table_info({table_name})").fetchall()]
    if column_name not in cols:
        conn.execute(f"ALTER TABLE {table_name} ADD COLUMN {column_name} {column_definition}")
        conn.commit()
    conn.close()


def init_db():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grant_name TEXT NOT NULL,
            grant_type TEXT DEFAULT 'General Aid',
            description TEXT,
            award_amount REAL DEFAULT 0,
            status TEXT DEFAULT 'Open',
            education_level_required TEXT DEFAULT 'Any',
            minimum_gpa REAL,
            enrollment_required TEXT,
            academic_year_required TEXT,
            need_based INTEGER DEFAULT 0,
            requires_statement INTEGER DEFAULT 1,
            priority_group TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT,
            student_id TEXT,
            email TEXT,
            phone TEXT,
            education_level TEXT,
            school_name TEXT,
            academic_year TEXT,
            major TEXT,
            gpa REAL,
            enrollment_status TEXT,
            semester TEXT,
            grant_id INTEGER,
            grant_type TEXT,
            amount REAL DEFAULT 0,
            reason TEXT,
            fund_use TEXT,
            other_aid TEXT,
            special_circumstances TEXT,
            agreement_confirmed INTEGER DEFAULT 0,
            enrollment_confirmed INTEGER DEFAULT 0,
            submitted_by TEXT,
            eligibility_result TEXT,
            eligibility_reason TEXT,
            status TEXT DEFAULT 'Pending',
            admin_final_decision TEXT DEFAULT 'Pending Review',
            awarded_amount REAL,
            review_notes TEXT,
            created_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (grant_id) REFERENCES grants(id)
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS notifications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            application_id INTEGER,
            student_email TEXT,
            student_name TEXT,
            notification_type TEXT,
            message TEXT,
            status TEXT DEFAULT 'Generated',
            sent_at TEXT DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (application_id) REFERENCES applications(id)
        )
    """)

    conn.commit()
    conn.close()

    # Safe migration support for older DB files.
    for column_name, definition in {
        "grant_type": "TEXT DEFAULT 'General Aid'",
        "description": "TEXT",
        "award_amount": "REAL DEFAULT 0",
        "status": "TEXT DEFAULT 'Open'",
        "education_level_required": "TEXT DEFAULT 'Any'",
        "minimum_gpa": "REAL",
        "enrollment_required": "TEXT",
        "academic_year_required": "TEXT",
        "need_based": "INTEGER DEFAULT 0",
        "requires_statement": "INTEGER DEFAULT 1",
        "priority_group": "TEXT",
        "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    }.items():
        add_column_if_missing("grants", column_name, definition)

    for column_name, definition in {
        "student_id": "TEXT",
        "phone": "TEXT",
        "education_level": "TEXT",
        "school_name": "TEXT",
        "academic_year": "TEXT",
        "major": "TEXT",
        "gpa": "REAL",
        "enrollment_status": "TEXT",
        "semester": "TEXT",
        "grant_id": "INTEGER",
        "grant_type": "TEXT",
        "amount": "REAL DEFAULT 0",
        "reason": "TEXT",
        "fund_use": "TEXT",
        "other_aid": "TEXT",
        "special_circumstances": "TEXT",
        "agreement_confirmed": "INTEGER DEFAULT 0",
        "enrollment_confirmed": "INTEGER DEFAULT 0",
        "submitted_by": "TEXT",
        "eligibility_result": "TEXT",
        "eligibility_reason": "TEXT",
        "admin_final_decision": "TEXT DEFAULT 'Pending Review'",
        "awarded_amount": "REAL",
        "review_notes": "TEXT",
        "created_at": "TEXT DEFAULT CURRENT_TIMESTAMP",
    }.items():
        add_column_if_missing("applications", column_name, definition)

    seed_base_data()


def seed_base_data():
    conn = get_db_connection()
    cur = conn.cursor()

    cur.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", ("admin", "admin123", "admin"))
    cur.execute("INSERT OR IGNORE INTO users (username, password, role) VALUES (?, ?, ?)", ("student", "student123", "user"))

    # Prevent duplicate grants
    cur.execute("DELETE FROM grants")
    cur.execute("DELETE FROM sqlite_sequence WHERE name='grants'")

    grants = [
        ("Emergency Relief Grant", "Emergency Relief", "Short-term support for urgent student needs such as housing, food, medical costs, or transportation.", 1200, "Open", "Any", 0.0, "Full-time", "Any", 1, 1, "Students with urgent financial hardship"),
        ("Academic Excellence Grant", "Merit", "Award for students with strong academic performance and continued enrollment.", 2500, "Open", "Undergraduate", 3.5, "Full-time", "Any", 0, 1, "High GPA students"),
        ("First Generation Support Grant", "Need-Based", "Support for first-generation students who need help covering education-related expenses.", 1800, "Open", "Any", 2.5, "Full-time", "Any", 1, 1, "First-generation students"),
        ("Technology Access Grant", "Technology", "Funding for laptops, software, or internet access needed for coursework.", 900, "Open", "Any", 2.0, "Any", "Any", 1, 1, "Students with technology barriers"),
    ]

    for grant in grants:
        cur.execute("""
            INSERT INTO grants (
                grant_name, grant_type, description, award_amount, status,
                education_level_required, minimum_gpa, enrollment_required,
                academic_year_required, need_based, requires_statement, priority_group
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, grant)



    conn.commit()
    conn.close()


def check_eligibility(student_data, grant):
    reasons = []
    eligible = True

    grant_education = grant["education_level_required"] or "Any"
    grant_min_gpa = grant["minimum_gpa"]
    grant_enrollment = grant["enrollment_required"] or "Any"
    grant_academic_year = grant["academic_year_required"] or "Any"

    student_education = student_data["education_level"]
    student_gpa = float(student_data["gpa"] or 0)
    student_enrollment = student_data["enrollment_status"]
    student_academic_year = student_data["academic_year"]
    student_reason = student_data["reason"] or ""
    student_special_circumstances = student_data["special_circumstances"] or ""

    if grant_education != "Any" and student_education != grant_education:
        eligible = False
        reasons.append(f"Education level does not match requirement ({grant_education}).")
    else:
        reasons.append("Education level matches grant requirement.")

    if grant_min_gpa is not None and student_gpa < float(grant_min_gpa):
        eligible = False
        reasons.append(f"GPA is below required minimum of {grant_min_gpa}.")
    elif grant_min_gpa is not None:
        reasons.append("GPA meets minimum requirement.")

    if grant_enrollment != "Any" and student_enrollment != grant_enrollment:
        eligible = False
        reasons.append(f"Enrollment status does not match requirement ({grant_enrollment}).")
    else:
        reasons.append("Enrollment status matches requirement.")

    if grant_academic_year != "Any" and student_academic_year != grant_academic_year:
        eligible = False
        reasons.append(f"Academic year does not match requirement ({grant_academic_year}).")
    else:
        reasons.append("Academic year matches requirement.")

    if grant["need_based"]:
        hardship_text = f"{student_reason} {student_special_circumstances}".lower()
        hardship_keywords = ["financial", "hardship", "emergency", "family", "medical", "job loss", "housing", "tuition", "support"]
        if any(word in hardship_text for word in hardship_keywords):
            reasons.append("Application includes indicators of financial or personal need.")
        else:
            reasons.append("Need-based grant selected, but hardship indicators may require manual review.")

    if grant["requires_statement"] and len(student_reason.strip()) < 20:
        eligible = False
        reasons.append("Application statement is too short for this grant.")

    if eligible:
        reasons.insert(0, "Student appears eligible based on automated screening.")
        return "Eligible", " ".join(reasons)

    reasons.insert(0, "Student does not fully meet automated screening requirements.")
    return "Not Eligible", " ".join(reasons)


def login_required():
    if "username" not in session:
        flash("Please log in first.", "error")
        return False
    return True


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"].strip()
    password = request.form["password"].strip()

    conn = get_db_connection()
    user = conn.execute("SELECT * FROM users WHERE username = ? AND password = ?", (username, password)).fetchone()
    conn.close()

    if user:
        session["username"] = user["username"]
        session["role"] = user["role"]
        flash("Login successful.", "success")
        return redirect(url_for("dashboard" if user["role"] == "admin" else "user_dashboard"))

    flash("Invalid username or password.", "error")
    return redirect(url_for("home"))


@app.route("/signup")
def signup():
    return render_template("signup.html")


@app.route("/register", methods=["POST"])
def register():
    username = request.form["username"].strip()
    password = request.form["password"].strip()

    if not username or not password:
        flash("Please enter an email and password.", "error")
        return redirect(url_for("signup"))

    if "@" not in username:
        flash("Please use an email address as your username.", "error")
        return redirect(url_for("signup"))

    conn = get_db_connection()
    existing_user = conn.execute("SELECT * FROM users WHERE username = ?", (username,)).fetchone()

    if existing_user:
        conn.close()
        flash("Username already exists. Try a different one.", "error")
        return redirect(url_for("signup"))

    conn.execute("INSERT INTO users (username, password, role) VALUES (?, ?, ?)", (username, password, "user"))
    conn.commit()
    conn.close()

    send_email(
        username,
        "Welcome to Student Grant System",
        """Your Student Grant System account has been created successfully.

You can now log in, apply for grants, and track your application status."""
    )

    flash("Account created successfully. You can log in now. A welcome email was sent.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    if not login_required():
        return redirect(url_for("home"))

    if session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("user_dashboard"))

    status_filter = request.args.get("status", "").strip()
    grant_type_filter = request.args.get("grant_type", "").strip()
    start_date = request.args.get("start_date", "").strip()
    end_date = request.args.get("end_date", "").strip()
    new_only = request.args.get("new_only", "").strip()

    query = """
        SELECT a.*, g.grant_name, g.grant_type AS official_grant_type, g.award_amount AS grant_award_amount
        FROM applications a
        LEFT JOIN grants g ON a.grant_id = g.id
        WHERE 1=1
    """
    params = []

    if status_filter:
        query += " AND a.status = ?"
        params.append(status_filter)

    if grant_type_filter:
        query += " AND COALESCE(g.grant_type, a.grant_type) = ?"
        params.append(grant_type_filter)

    if start_date:
        query += " AND date(a.created_at) >= date(?)"
        params.append(start_date)

    if end_date:
        query += " AND date(a.created_at) <= date(?)"
        params.append(end_date)

    if new_only:
        query += " AND a.status = 'Pending'"

    query += " ORDER BY a.created_at DESC"

    conn = get_db_connection()
    applications = conn.execute(query, params).fetchall()
    grant_types = conn.execute("SELECT DISTINCT grant_type FROM grants WHERE grant_type IS NOT NULL ORDER BY grant_type").fetchall()

    stats = {
        "today": conn.execute("SELECT COUNT(*) AS c FROM applications WHERE date(created_at) = date('now')").fetchone()["c"],
        "pending": conn.execute("SELECT COUNT(*) AS c FROM applications WHERE status = 'Pending'").fetchone()["c"],
        "approved": conn.execute("SELECT COUNT(*) AS c FROM applications WHERE status = 'Approved'").fetchone()["c"],
        "denied": conn.execute("SELECT COUNT(*) AS c FROM applications WHERE status = 'Denied'").fetchone()["c"],
    }

    conn.close()
    return render_template(
        "dashboard.html",
        applications=applications,
        grant_types=grant_types,
        stats=stats,
        filters=request.args,
        username=session["username"]
    )


@app.route("/user-dashboard")
def user_dashboard():
    if not login_required():
        return redirect(url_for("home"))

    status_filter = request.args.get("status", "").strip()
    grant_type_filter = request.args.get("grant_type", "").strip()

    query = """
        SELECT a.*, g.grant_name, g.grant_type AS official_grant_type, g.description, g.award_amount AS grant_award_amount
        FROM applications a
        LEFT JOIN grants g ON a.grant_id = g.id
        WHERE a.submitted_by = ?
    """
    params = [session["username"]]

    if status_filter:
        query += " AND a.status = ?"
        params.append(status_filter)

    if grant_type_filter:
        query += " AND COALESCE(g.grant_type, a.grant_type) = ?"
        params.append(grant_type_filter)

    query += " ORDER BY a.created_at DESC"

    conn = get_db_connection()
    applications = conn.execute(query, params).fetchall()
    grant_types = conn.execute("SELECT DISTINCT grant_type FROM grants WHERE grant_type IS NOT NULL ORDER BY grant_type").fetchall()
    conn.close()

    return render_template(
        "user_dashboard.html",
        username=session["username"],
        applications=applications,
        grant_types=grant_types,
        filters=request.args
    )


@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot-password.html")


@app.route("/apply")
def apply():
    if not login_required():
        return redirect(url_for("home"))

    if session.get("role") == "admin":
        flash("Admins do not submit grant applications.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    grants = conn.execute("SELECT * FROM grants WHERE status = 'Open' ORDER BY grant_name ASC").fetchall()
    conn.close()

    return render_template("apply.html", grants=grants)


@app.route("/submit-application", methods=["POST"])
def submit_application():
    if not login_required():
        return redirect(url_for("home"))

    if session.get("role") == "admin":
        flash("Admins cannot submit grant applications.", "error")
        return redirect(url_for("dashboard"))

    grant_id = request.form.get("grant_id")

    if not grant_id:
        flash("Please select a grant before submitting.", "error")
        return redirect(url_for("apply"))

    conn = get_db_connection()
    grant = conn.execute("SELECT * FROM grants WHERE id = ?", (grant_id,)).fetchone()

    if not grant:
        conn.close()
        flash("Selected grant was not found.", "error")
        return redirect(url_for("apply"))

    student_data = {
        "education_level": request.form["education_level"],
        "gpa": request.form["gpa"],
        "enrollment_status": request.form["enrollment_status"],
        "academic_year": request.form["academic_year"],
        "reason": request.form["reason"],
        "special_circumstances": request.form.get("special_circumstances", ""),
    }

    eligibility_result, eligibility_reason = check_eligibility(student_data, grant)

    status = "Pending"
    admin_final_decision = "Pending Review"
    requested_amount = float(grant["award_amount"] or 0)

    cur = conn.cursor()
    cur.execute("""
        INSERT INTO applications (
            student_name, student_id, email, phone, education_level, school_name,
            academic_year, major, gpa, enrollment_status, semester, grant_id, grant_type,
            amount, reason, fund_use, other_aid, special_circumstances, agreement_confirmed,
            enrollment_confirmed, submitted_by, eligibility_result, eligibility_reason,
            status, admin_final_decision
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    """, (
        request.form["student_name"],
        request.form["student_id"],
        request.form["email"],
        request.form["phone"],
        request.form["education_level"],
        request.form["school_name"],
        request.form["academic_year"],
        request.form["major"],
        request.form["gpa"],
        request.form["enrollment_status"],
        request.form["semester"],
        grant_id,
        grant["grant_type"],
        requested_amount,
        request.form["reason"],
        request.form["fund_use"],
        request.form.get("other_aid", ""),
        request.form.get("special_circumstances", ""),
        1 if request.form.get("agreement_confirmed") else 0,
        1 if request.form.get("enrollment_confirmed") else 0,
        session["username"],
        eligibility_result,
        eligibility_reason,
        status,
        admin_final_decision
    ))

    application_id = cur.lastrowid

    student_message = f"""Hello {request.form["student_name"]},

Your grant application was submitted successfully.

Grant: {grant["grant_name"]}
Grant Type: {grant["grant_type"]}
Eligibility Result: {eligibility_result}
Current Status: {status}

You can log in to the Student Grant System to track your application status.
"""

    admin_message = f"""A new grant application is pending review.

Student: {request.form["student_name"]}
Student Email: {request.form["email"]}
Grant: {grant["grant_name"]}
Grant Type: {grant["grant_type"]}
Eligibility Result: {eligibility_result}
Status: {status}

Please review this application in the admin dashboard.
"""

    send_email(
        request.form["email"],
        "Grant Application Submitted",
        student_message
    )

    # Since applications are submitted as Pending, notify the admin.
    send_email(
        ADMIN_EMAIL,
        "New Pending Grant Application",
        admin_message
    )

    conn.execute("""
        INSERT INTO notifications (application_id, student_email, student_name, notification_type, message, status)
        VALUES (?, ?, ?, ?, ?, ?)
    """, (
        application_id,
        request.form["email"],
        request.form["student_name"],
        "Application Submitted",
        "Student confirmation email sent and admin pending-review email generated.",
        "Sent"
    ))

    conn.commit()
    conn.close()

    flash("Application submitted successfully. Student and admin email notifications were sent.", "success")
    return redirect(url_for("user_dashboard"))


@app.route("/update-status", methods=["POST"])
def update_status():
    if not login_required():
        return redirect(url_for("home"))

    if session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("user_dashboard"))

    application_id = request.form["application_id"]
    status = request.form["status"]
    admin_final_decision = request.form["admin_final_decision"]
    awarded_amount = request.form.get("awarded_amount", "").strip() or None
    review_notes = request.form.get("review_notes", "").strip()

    conn = get_db_connection()
    app_row = conn.execute("SELECT * FROM applications WHERE id = ?", (application_id,)).fetchone()

    conn.execute("""
        UPDATE applications
        SET status = ?, admin_final_decision = ?, awarded_amount = ?, review_notes = ?
        WHERE id = ?
    """, (status, admin_final_decision, awarded_amount, review_notes, application_id))

    if app_row and status in ["Approved", "Denied"]:
        message = f"""Hello {app_row["student_name"]},

Your grant application status has been updated.

New Status: {status}
Decision: {admin_final_decision}
Awarded Amount: {awarded_amount if awarded_amount else "N/A"}
Review Notes: {review_notes if review_notes else "No additional notes provided."}

Please log in to the Student Grant System for more details.
"""

        email_sent = send_email(
            app_row["email"],
            "Grant Application Status Update",
            message
        )

        conn.execute("""
            INSERT INTO notifications (application_id, student_email, student_name, notification_type, message, status)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (
            application_id,
            app_row["email"],
            app_row["student_name"],
            f"Application {status}",
            message,
            "Sent" if email_sent else "Generated"
        ))

    conn.commit()
    conn.close()

    flash("Application updated successfully. Notification record generated when applicable.", "success")
    return redirect(url_for("dashboard"))


@app.route("/notifications")
def notifications():
    if not login_required():
        return redirect(url_for("home"))

    if session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("user_dashboard"))

    conn = get_db_connection()
    rows = conn.execute("""
        SELECT n.*, a.status AS application_status, a.grant_type
        FROM notifications n
        LEFT JOIN applications a ON n.application_id = a.id
        ORDER BY n.sent_at DESC
    """).fetchall()
    conn.close()

    return render_template("notifications.html", notifications=rows, username=session["username"])


@app.route("/seed-demo-data")
def seed_demo_data_route():
    if not login_required():
        return redirect(url_for("home"))

    if session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("user_dashboard"))

    seed_demo_applications()
    flash("Demo data added for the admin dashboard.", "success")
    return redirect(url_for("dashboard"))


def seed_demo_applications():
    conn = get_db_connection()
    cursor = conn.cursor()

    students = [
        ("John Doe", "johndoe@gmail.com"),
        ("Jane Smith", "janesmith@gmail.com"),
        ("Alex Johnson", "alexjohnson@gmail.com"),
        ("Chris Lee", "chrislee@gmail.com"),
        ("Maria Garcia", "mariagarcia@gmail.com"),
        ("Taylor Brown", "taylorbrown@gmail.com"),
    ]

    grants = conn.execute("SELECT * FROM grants ORDER BY id").fetchall()
    statuses = ["Pending", "Approved", "Denied"]

    if not grants:
        conn.close()
        return

    for _ in range(20):
        student_name, email = random.choice(students)
        grant = random.choice(grants)
        status = random.choice(statuses)

        student_id = str(random.randint(100000, 999999))
        phone = "804-" + str(random.randint(1000000, 9999999))
        education_level = "Undergraduate"
        school_name = "VCU"
        academic_year = random.choice(["Freshman", "Sophomore", "Junior", "Senior"])
        major = random.choice(["Information Systems", "Computer Science", "Business", "Nursing", "Psychology"])
        gpa = round(random.uniform(2.0, 4.0), 2)
        enrollment_status = "Full-time"
        semester = random.choice(["Fall", "Spring"])
        reason = "Financial hardship due to unexpected expenses and education-related costs."
        fund_use = random.choice(["Tuition and fees", "Housing", "Books and supplies", "Technology"])
        other_aid = random.choice(["None", "Pell Grant", "Scholarship", "Work study"])
        special_circumstances = random.choice(["Family emergency", "Medical expense", "Job loss", "Transportation issue"])
        eligibility_result = "Eligible" if gpa >= float(grant["minimum_gpa"] or 0) else "Not Eligible"
        eligibility_reason = "Auto-generated demo screening based on GPA and grant criteria."
        admin_final_decision = status if status != "Pending" else "Pending Review"
        awarded_amount = random.randint(500, 3000) if status == "Approved" else None
        review_notes = "Auto-generated for demo."
        amount = random.randint(1000, 5000)
        created_at = datetime.now() - timedelta(days=random.randint(0, 10))

        cursor.execute("""
            INSERT INTO applications (
                student_name, student_id, email, phone, education_level, school_name,
                academic_year, major, gpa, enrollment_status, semester, grant_id, grant_type,
                amount, reason, fund_use, other_aid, special_circumstances, agreement_confirmed,
                enrollment_confirmed, submitted_by, eligibility_result, eligibility_reason,
                status, admin_final_decision, awarded_amount, review_notes, created_at
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, (
            student_name,
            student_id,
            email,
            phone,
            education_level,
            school_name,
            academic_year,
            major,
            gpa,
            enrollment_status,
            semester,
            grant["id"],
            grant["grant_type"],
            amount,
            reason,
            fund_use,
            other_aid,
            special_circumstances,
            1,
            1,
            "student",
            eligibility_result,
            eligibility_reason,
            status,
            admin_final_decision,
            awarded_amount,
            review_notes,
            created_at
        ))

    conn.commit()
    conn.close()


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    app.run(debug=True)
