from flask import Flask, render_template, request, redirect, url_for, session, flash
import sqlite3
import os
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash

app = Flask(__name__)
app.secret_key = os.getenv("SECRET_KEY", "dev-secret-key")
DB = "campus.db"

def get_db():
    conn = sqlite3.connect(DB)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    conn.execute("""CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE NOT NULL,
        password TEXT NOT NULL)""")
    conn.execute("""CREATE TABLE IF NOT EXISTS reports (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id INTEGER NOT NULL,
        report_type TEXT NOT NULL,
        item_name TEXT NOT NULL,
        description TEXT NOT NULL,
        location TEXT NOT NULL,
        report_date TEXT NOT NULL,
        contact TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'Active',
        created_at TEXT NOT NULL,
        FOREIGN KEY (user_id) REFERENCES users(id))""")

    user = conn.execute("SELECT id FROM users WHERE username=?", ("student",)).fetchone()
    if not user:
        conn.execute("INSERT INTO users (username,password) VALUES (?,?)",
                     ("student", generate_password_hash("student123")))
    conn.commit()
    conn.close()

@app.route("/login", methods=["GET","POST"])
def login():
    if request.method == "POST":
        username = request.form.get("username","").strip()
        password = request.form.get("password","")
        if not username or not password:
            flash("Username and password are required.", "error")
            return redirect(url_for("login"))
        conn = get_db()
        user = conn.execute("SELECT * FROM users WHERE username=?", (username,)).fetchone()
        conn.close()
        if user and check_password_hash(user["password"], password):
            session["user_id"] = user["id"]
            session["username"] = user["username"]
            return redirect(url_for("index"))
        flash("Invalid username or password.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

@app.route("/")
def index():
    if "user_id" not in session:
        return redirect(url_for("login"))
    search = request.args.get("search","").strip()
    report_type = request.args.get("type","")
    status = request.args.get("status","Active")
    conn = get_db()
    query = """SELECT reports.*, users.username FROM reports
               JOIN users ON reports.user_id=users.id WHERE 1=1"""
    params = []
    if search:
        query += " AND (item_name LIKE ? OR description LIKE ? OR location LIKE ?)"
        like = f"%{search}%"
        params += [like, like, like]
    if report_type in ("Lost","Found"):
        query += " AND report_type=?"
        params.append(report_type)
    if status in ("Active","Resolved"):
        query += " AND reports.status=?"
        params.append(status)
    query += " ORDER BY reports.id DESC"
    reports = conn.execute(query, params).fetchall()
    counts = {
        "Lost": conn.execute("SELECT COUNT(*) FROM reports WHERE report_type='Lost' AND status='Active'").fetchone()[0],
        "Found": conn.execute("SELECT COUNT(*) FROM reports WHERE report_type='Found' AND status='Active'").fetchone()[0]
    }
    conn.close()
    return render_template("index.html", reports=reports, search=search,
                           report_type=report_type, status=status, counts=counts)

@app.route("/report", methods=["GET","POST"])
def report():
    if "user_id" not in session:
        return redirect(url_for("login"))
    if request.method == "POST":
        report_type = request.form.get("report_type","")
        item_name = request.form.get("item_name","").strip()
        description = request.form.get("description","").strip()
        location = request.form.get("location","").strip()
        report_date = request.form.get("report_date","").strip()
        contact = request.form.get("contact","").strip()
        errors = []
        if report_type not in ("Lost","Found"): errors.append("Please select Lost or Found.")
        if not item_name: errors.append("Item name is required.")
        if not description: errors.append("Description is required.")
        if not location: errors.append("Location is required.")
        if not report_date: errors.append("Date is required.")
        if not contact: errors.append("Contact information is required.")
        if errors:
            for e in errors: flash(e, "error")
            return render_template("report.html", form=request.form)
        conn = get_db()
        conn.execute("""INSERT INTO reports
            (user_id,report_type,item_name,description,location,report_date,contact,status,created_at)
            VALUES (?,?,?,?,?,?,?,'Active',?)""",
            (session["user_id"],report_type,item_name,description,location,report_date,contact,
             datetime.now().strftime("%d %b %Y, %I:%M %p")))
        conn.commit()
        conn.close()
        flash("Report submitted successfully!", "success")
        return redirect(url_for("index"))
    return render_template("report.html", form={})

@app.route("/report/<int:report_id>")
def details(report_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    report = conn.execute("""SELECT reports.*, users.username FROM reports
                             JOIN users ON reports.user_id=users.id
                             WHERE reports.id=?""", (report_id,)).fetchone()
    conn.close()
    if not report:
        flash("Report not found.", "error")
        return redirect(url_for("index"))
    return render_template("details.html", report=report)

@app.route("/resolve/<int:report_id>", methods=["POST"])
def resolve(report_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    report = conn.execute("SELECT user_id FROM reports WHERE id=?", (report_id,)).fetchone()
    if not report:
        conn.close()
        flash("Report not found.", "error")
        return redirect(url_for("index"))
    if report["user_id"] != session["user_id"]:
        conn.close()
        flash("You can only resolve your own reports.", "error")
        return redirect(url_for("details", report_id=report_id))
    conn.execute("UPDATE reports SET status='Resolved' WHERE id=?", (report_id,))
    conn.commit()
    conn.close()
    flash("Report marked as resolved.", "success")
    return redirect(url_for("details", report_id=report_id))

@app.route("/delete/<int:report_id>", methods=["POST"])
def delete_report(report_id):
    if "user_id" not in session:
        return redirect(url_for("login"))
    conn = get_db()
    report = conn.execute("SELECT user_id FROM reports WHERE id=?", (report_id,)).fetchone()
    if not report:
        conn.close()
        flash("Report not found.", "error")
        return redirect(url_for("index"))
    if report["user_id"] != session["user_id"]:
        conn.close()
        flash("You can only delete your own reports.", "error")
        return redirect(url_for("details", report_id=report_id))
    conn.execute("DELETE FROM reports WHERE id=?", (report_id,))
    conn.commit()
    conn.close()
    flash("Report deleted.", "success")
    return redirect(url_for("index"))

init_db()

if __name__ == "__main__":
    app.run(debug=False, use_reloader=False, port=5000)
