from flask import Flask, render_template, request, redirect, url_for, flash, session
import sqlite3
import os

app = Flask(__name__)
app.secret_key = "studentgrantsecret"
app.config["TEMPLATES_AUTO_RELOAD"] = True

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
DATABASE = os.path.join(BASE_DIR, "student_grants.db")


@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response


def get_db_connection():
    conn = sqlite3.connect(DATABASE, check_same_thread=False)
    conn.row_factory = sqlite3.Row
    return conn


def init_db():
    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT NOT NULL UNIQUE,
            password TEXT NOT NULL,
            role TEXT NOT NULL DEFAULT 'user'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS grants (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            grant_name TEXT NOT NULL,
            award_amount REAL,
            education_level_required TEXT,
            minimum_gpa REAL,
            enrollment_required TEXT,
            academic_year_required TEXT,
            need_based INTEGER DEFAULT 0,
            requires_statement INTEGER DEFAULT 0,
            priority_group TEXT,
            status TEXT NOT NULL DEFAULT 'Open'
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS applications (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_name TEXT NOT NULL,
            student_id TEXT,
            email TEXT NOT NULL,
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
            reason TEXT,
            fund_use TEXT,
            other_aid TEXT,
            special_circumstances TEXT,
            agreement_confirmed INTEGER DEFAULT 0,
            enrollment_confirmed INTEGER DEFAULT 0,
            submitted_by TEXT,
            eligibility_result TEXT,
            eligibility_reason TEXT,
            status TEXT NOT NULL DEFAULT 'Pending',
            admin_final_decision TEXT DEFAULT 'Pending Review',
            awarded_amount REAL,
            review_notes TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
            FOREIGN KEY (grant_id) REFERENCES grants(id)
        )
    """)

    cursor.execute("SELECT * FROM users WHERE username = ?", ("admin",))
    admin_user = cursor.fetchone()

    if not admin_user:
        cursor.execute(
            "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
            ("admin", "1234", "admin")
        )

    cursor.execute("SELECT COUNT(*) AS count FROM grants")
    grant_count = cursor.fetchone()["count"]

    if grant_count == 0:
        sample_grants = [
            (
                "Academic Excellence Grant",
                2500,
                "Undergraduate",
                3.5,
                "Full-Time",
                "Junior",
                0,
                1,
                "High-Achieving Students",
                "Open"
            ),
            (
                "Need-Based Student Support Grant",
                3000,
                "Any",
                2.5,
                "Full-Time",
                "Any",
                1,
                1,
                "Students with Financial Need",
                "Open"
            ),
            (
                "Graduate Achievement Grant",
                4000,
                "Graduate",
                3.2,
                "Part-Time",
                "Any",
                0,
                1,
                "Graduate Students",
                "Open"
            )
        ]

        cursor.executemany("""
            INSERT INTO grants (
                grant_name, award_amount, education_level_required, minimum_gpa,
                enrollment_required, academic_year_required, need_based,
                requires_statement, priority_group, status
            )
            VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """, sample_grants)

    conn.commit()
    conn.close()


def check_eligibility(student_data, grant):
    reasons = []
    eligible = True

    grant_education = grant["education_level_required"]
    grant_min_gpa = grant["minimum_gpa"]
    grant_enrollment = grant["enrollment_required"]
    grant_academic_year = grant["academic_year_required"]

    student_education = student_data["education_level"]
    student_gpa = float(student_data["gpa"])
    student_enrollment = student_data["enrollment_status"]
    student_academic_year = student_data["academic_year"]
    student_reason = student_data["reason"]
    student_special_circumstances = student_data["special_circumstances"]

    if grant_education and grant_education != "Any":
        if student_education != grant_education:
            eligible = False
            reasons.append(f"Education level does not match requirement ({grant_education}).")
        else:
            reasons.append("Education level matches grant requirement.")

    if grant_min_gpa is not None:
        if student_gpa < float(grant_min_gpa):
            eligible = False
            reasons.append(f"GPA is below required minimum of {grant_min_gpa}.")
        else:
            reasons.append("GPA meets minimum requirement.")

    if grant_enrollment and grant_enrollment != "Any":
        if student_enrollment != grant_enrollment:
            eligible = False
            reasons.append(f"Enrollment status does not match requirement ({grant_enrollment}).")
        else:
            reasons.append("Enrollment status matches requirement.")

    if grant_academic_year and grant_academic_year != "Any":
        if student_academic_year != grant_academic_year:
            eligible = False
            reasons.append(f"Academic year does not match requirement ({grant_academic_year}).")
        else:
            reasons.append("Academic year matches requirement.")

    if grant["need_based"]:
        reasons.append("This is a need-based grant and may require additional review.")
        hardship_text = f"{student_reason} {student_special_circumstances}".strip().lower()
        hardship_keywords = [
            "financial",
            "hardship",
            "emergency",
            "family",
            "medical",
            "job loss",
            "housing",
            "tuition",
            "support"
        ]

        if any(word in hardship_text for word in hardship_keywords):
            reasons.append("Student application includes indicators of financial or personal need.")
        else:
            reasons.append("Need-based grant selected, but hardship indicators may require manual review.")

    if grant["requires_statement"]:
        if len(student_reason.strip()) < 20:
            eligible = False
            reasons.append("Application statement is too short for this grant.")
        else:
            reasons.append("Application statement meets minimum detail expectation.")

    if grant["priority_group"]:
        reasons.append(f"Priority consideration for: {grant['priority_group']}.")

    if eligible:
        result = "Eligible"
        reasons.insert(0, "Student appears eligible based on automated screening.")
    else:
        result = "Not Eligible"
        reasons.insert(0, "Student does not fully meet automated screening requirements.")

    return result, " ".join(reasons)


@app.route("/")
def home():
    return render_template("index.html")


@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute(
        "SELECT * FROM users WHERE username = ? AND password = ?",
        (username, password)
    )
    user = cursor.fetchone()
    conn.close()

    if user:
        session["username"] = user["username"]
        session["role"] = user["role"]
        flash("Login successful.", "success")

        if user["role"] == "admin":
            return redirect(url_for("dashboard"))
        return redirect(url_for("user_dashboard"))

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
        flash("Please enter a username and password.", "error")
        return redirect(url_for("signup"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM users WHERE username = ?", (username,))
    existing_user = cursor.fetchone()

    if existing_user:
        conn.close()
        flash("Username already exists. Try a different one.", "error")
        return redirect(url_for("signup"))

    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (?, ?, ?)",
        (username, password, "user")
    )
    conn.commit()
    conn.close()

    flash("Account created successfully. You can log in now.", "success")
    return redirect(url_for("home"))


@app.route("/dashboard")
def dashboard():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    if session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("user_dashboard"))

    status_filter = request.args.get("status", "").strip()

    conn = get_db_connection()
    cursor = conn.cursor()

    if status_filter:
        cursor.execute("""
            SELECT a.*, g.grant_name, g.award_amount AS grant_award_amount
            FROM applications a
            LEFT JOIN grants g ON a.grant_id = g.id
            WHERE a.status = ?
            ORDER BY a.created_at DESC
        """, (status_filter,))
    else:
        cursor.execute("""
            SELECT a.*, g.grant_name, g.award_amount AS grant_award_amount
            FROM applications a
            LEFT JOIN grants g ON a.grant_id = g.id
            ORDER BY a.created_at DESC
        """)

    applications = cursor.fetchall()
    conn.close()

    return render_template(
        "dashboard.html",
        applications=applications,
        username=session["username"]
    )


@app.route("/user-dashboard")
def user_dashboard():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        SELECT a.*, g.grant_name, g.award_amount AS grant_award_amount
        FROM applications a
        LEFT JOIN grants g ON a.grant_id = g.id
        WHERE a.submitted_by = ?
        ORDER BY a.created_at DESC
    """, (session["username"],))
    applications = cursor.fetchall()
    conn.close()

    return render_template(
        "user_dashboard.html",
        username=session["username"],
        applications=applications
    )


@app.route("/forgot-password")
def forgot_password():
    return render_template("forgot-password.html")


@app.route("/apply")
def apply():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    if session.get("role") == "admin":
        flash("Admins do not submit grant applications.", "error")
        return redirect(url_for("dashboard"))

    conn = get_db_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT * FROM grants WHERE status = 'Open' ORDER BY grant_name ASC")
    grants = cursor.fetchall()
    conn.close()

    return render_template("apply.html", grants=grants)


@app.route("/submit-application", methods=["POST"])
def submit_application():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    if session.get("role") == "admin":
        flash("Admins cannot submit grant applications.", "error")
        return redirect(url_for("dashboard"))

    grant_id = request.form.get("grant_id")
    if not grant_id:
        flash("Please select a grant before submitting.", "error")
        return redirect(url_for("apply"))

    student_name = request.form["student_name"]
    student_id = request.form["student_id"]
    email = request.form["email"]
    phone = request.form["phone"]
    education_level = request.form["education_level"]
    school_name = request.form["school_name"]
    academic_year = request.form["academic_year"]
    major = request.form["major"]
    gpa = request.form["gpa"]
    enrollment_status = request.form["enrollment_status"]
    semester = request.form["semester"]
    reason = request.form["reason"]
    fund_use = request.form["fund_use"]
    other_aid = request.form["other_aid"]
    special_circumstances = request.form["special_circumstances"]
    agreement_confirmed = 1 if request.form.get("agreement_confirmed") else 0
    enrollment_confirmed = 1 if request.form.get("enrollment_confirmed") else 0
    submitted_by = session["username"]

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("SELECT * FROM grants WHERE id = ?", (grant_id,))
    grant = cursor.fetchone()

    if not grant:
        conn.close()
        flash("Selected grant was not found.", "error")
        return redirect(url_for("apply"))

    student_data = {
        "education_level": education_level,
        "gpa": gpa,
        "enrollment_status": enrollment_status,
        "academic_year": academic_year,
        "reason": reason,
        "special_circumstances": special_circumstances
    }

    eligibility_result, eligibility_reason = check_eligibility(student_data, grant)
    grant_type = grant["grant_name"]

    cursor.execute("""
        INSERT INTO applications (
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
            grant_id,
            grant_type,
            reason,
            fund_use,
            other_aid,
            special_circumstances,
            agreement_confirmed,
            enrollment_confirmed,
            submitted_by,
            eligibility_result,
            eligibility_reason,
            status,
            admin_final_decision
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
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
        grant_id,
        grant_type,
        reason,
        fund_use,
        other_aid,
        special_circumstances,
        agreement_confirmed,
        enrollment_confirmed,
        submitted_by,
        eligibility_result,
        eligibility_reason,
        "Pending",
        "Pending Review"
    ))

    conn.commit()
    conn.close()

    flash("Application submitted successfully. Automated eligibility screening completed.", "success")
    return redirect(url_for("user_dashboard"))


@app.route("/update-status", methods=["POST"])
def update_status():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    if session.get("role") != "admin":
        flash("Access denied. Admins only.", "error")
        return redirect(url_for("user_dashboard"))

    application_id = request.form["application_id"]
    status = request.form["status"]
    admin_final_decision = request.form["admin_final_decision"]
    awarded_amount = request.form.get("awarded_amount", "").strip()
    review_notes = request.form.get("review_notes", "").strip()

    if awarded_amount == "":
        awarded_amount = None

    conn = get_db_connection()
    cursor = conn.cursor()

    cursor.execute("""
        UPDATE applications
        SET status = ?,
            admin_final_decision = ?,
            awarded_amount = ?,
            review_notes = ?
        WHERE id = ?
    """, (status, admin_final_decision, awarded_amount, review_notes, application_id))

    conn.commit()
    conn.close()

    flash("Application updated successfully.", "success")
    return redirect(url_for("dashboard"))


@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))


init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port)
