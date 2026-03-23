from flask import Flask, render_template, request, redirect, url_for, flash, session
import mysql.connector

app = Flask(__name__)
app.secret_key = "studentgrantsecret"
app.config["TEMPLATES_AUTO_RELOAD"] = True

@app.after_request
def add_header(response):
    response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate, proxy-revalidate, max-age=0"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response

def get_db_connection():
    return mysql.connector.connect(
        host="localhost",
        user="root",
        password="62451",
        database="student_grants"
    )

@app.route("/")
def home():
    return render_template("index.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute(
        "SELECT * FROM users WHERE username = %s AND password = %s",
        (username, password)
    )
    user = cursor.fetchone()

    cursor.close()
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

    cursor.execute("SELECT * FROM users WHERE username = %s", (username,))
    existing_user = cursor.fetchone()

    if existing_user:
        cursor.close()
        conn.close()
        flash("Username already exists. Try a different one.", "error")
        return redirect(url_for("signup"))

    cursor.execute(
        "INSERT INTO users (username, password, role) VALUES (%s, %s, %s)",
        (username, password, "user")
    )
    conn.commit()

    cursor.close()
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

    conn = get_db_connection()
    cursor = conn.cursor(dictionary=True)

    cursor.execute("SELECT * FROM applications ORDER BY created_at DESC")
    applications = cursor.fetchall()

    cursor.close()
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
    cursor = conn.cursor(dictionary=True)

    query = """
    SELECT * FROM applications
    WHERE submitted_by = %s
    ORDER BY created_at DESC
    """
    cursor.execute(query, (session["username"],))
    applications = cursor.fetchall()

    cursor.close()
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

    return render_template("apply.html")

@app.route("/submit-application", methods=["POST"])
def submit_application():
    if "username" not in session:
        flash("Please log in first.", "error")
        return redirect(url_for("home"))

    if session.get("role") == "admin":
        flash("Admins cannot submit grant applications.", "error")
        return redirect(url_for("dashboard"))

    student_name = request.form["student_name"]
    email = request.form["email"]
    grant_type = request.form["grant_type"]
    amount = request.form["amount"]
    submitted_by = session["username"]

    conn = get_db_connection()
    cursor = conn.cursor()

    query = """
    INSERT INTO applications (student_name, email, grant_type, amount, submitted_by)
    VALUES (%s, %s, %s, %s, %s)
    """
    cursor.execute(query, (student_name, email, grant_type, amount, submitted_by))
    conn.commit()

    cursor.close()
    conn.close()

    flash("Application submitted successfully.", "success")
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

    conn = get_db_connection()
    cursor = conn.cursor()

    query = "UPDATE applications SET status = %s WHERE id = %s"
    cursor.execute(query, (status, application_id))
    conn.commit()

    cursor.close()
    conn.close()

    flash(f"Application status updated to {status}.", "success")
    return redirect(url_for("dashboard"))

@app.route("/logout")
def logout():
    session.clear()
    flash("Logged out successfully.", "success")
    return redirect(url_for("home"))

if __name__ == "__main__":
    app.run(debug=True)