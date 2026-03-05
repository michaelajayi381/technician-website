from flask import Flask, render_template, request, redirect, url_for, session, send_from_directory
import sqlite3
import os
from datetime import datetime
from werkzeug.utils import secure_filename

app = Flask(__name__)
app.secret_key = "supersecretkey"

DATABASE = "database.db"
app.config['UPLOAD_FOLDER'] = 'static/uploads'

# Ensure upload folder exists
os.makedirs(app.config['UPLOAD_FOLDER'], exist_ok=True)

# -------------------------
# DATABASE INIT
# -------------------------
def init_db():
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        CREATE TABLE IF NOT EXISTS bookings (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            serviceType TEXT,
            issueType TEXT,
            description TEXT,
            urgency TEXT,
            fullName TEXT,
            phone TEXT,
            address TEXT,
            date TEXT,
            photo TEXT,
            status TEXT DEFAULT 'Pending',
            is_deleted INTEGER DEFAULT 0,
            created_at TEXT
        )
    ''')
    conn.commit()
    conn.close()

init_db()

# -------------------------
# USER ROUTES
# -------------------------
@app.route('/')
def index():
    return render_template('user/index.html')

@app.route('/services')
def services():
    return render_template('user/services.html')

# -------------------------
# BOOKING ROUTE
# -------------------------
@app.route("/booking", methods=["GET", "POST"])
def booking():

    if request.method == "GET":
        service = request.args.get("service", "")

        issues_dict = {
            "Electrical": ["Wiring", "Sockets", "Circuit Issues", "Generators", "Others"],
            "Mechanical": ["Engine", "Machines", "Belts & Gears", "Hydraulic/Pneumatic", "Others"],
            "Installation": ["AC Setup", "Solar Installation", "CCTV Installation", "Machine Setup", "Others"],
            "Maintenance": ["Preventive Servicing", "Lubrication", "Safety Checks", "Emergency Support", "Others"],
            "Electronics": ["Gadgets Repair", "Inverter Repair", "PCB Troubleshooting", "Solar Panel Repair", "Others"]
        }

        issues = issues_dict.get(service, [])
        return render_template("user/booking.html", service=service, issues=issues)

    # ---------------- POST ----------------
    serviceType = request.form.get('serviceType')
    issueType = request.form.get('issue')
    description = request.form.get('description')
    urgency = request.form.get('urgency')
    fullName = request.form.get('fullName')
    phone = request.form.get('phone')
    address = request.form.get('address')
    date = request.form.get('date')

    # Handle file upload safely
    photo_file = request.files.get('photo')
    photo_filename = None

    if photo_file and photo_file.filename:
        photo_filename = secure_filename(photo_file.filename)
        photo_path = os.path.join(app.config['UPLOAD_FOLDER'], photo_filename)
        photo_file.save(photo_path)

    # Save to database
    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute('''
        INSERT INTO bookings (
            serviceType, issueType, description, urgency,
            fullName, phone, address, date, photo, created_at
        ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
    ''', (
        serviceType, issueType, description, urgency,
        fullName, phone, address, date,
        photo_filename, datetime.now()
    ))
    conn.commit()
    conn.close()

    session['customerName'] = fullName
    return redirect(url_for('confirmation'))

# -------------------------
# CONFIRMATION
# -------------------------
@app.route('/confirmation')
def confirmation():
    name = session.get('customerName', '')
    return render_template('user/confirmation.html', customerName=name)

# -------------------------
# ADMIN LOGIN
# -------------------------
@app.route('/admin/login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')

        if username == 'adminprime' and password == 'Michael$123,':
            session['admin_logged_in'] = True
            return redirect(url_for('admin_dashboard'))
        else:
            return render_template('admin/login.html', error="Invalid credentials")

    return render_template('admin/login.html')

# -------------------------
# ADMIN DASHBOARD
# -------------------------
@app.route('/admin/dashboard')
def admin_dashboard():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    search_query = request.args.get('search', '')
    status_filter = request.args.get('status', '')

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()

    query = "SELECT * FROM bookings WHERE is_deleted=0"
    params = []

    if status_filter:
        query += " AND status=?"
        params.append(status_filter)

    if search_query:
        query += " AND (fullName LIKE ? OR phone LIKE ?)"
        params.extend([f"%{search_query}%", f"%{search_query}%"])

    query += " ORDER BY created_at DESC"
    c.execute(query, params)
    bookings = c.fetchall()
    conn.close()

    return render_template(
        'admin/dashboard.html',
        bookings=bookings,
        search_query=search_query,
        status_filter=status_filter
    )

# -------------------------
# TOGGLE STATUS
# -------------------------
@app.route('/admin/toggle_status/<int:booking_id>')
def toggle_status(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("SELECT status FROM bookings WHERE id=?", (booking_id,))
    current = c.fetchone()[0]

    new_status = 'Completed' if current == 'Pending' else 'Pending'
    c.execute("UPDATE bookings SET status=? WHERE id=?", (new_status, booking_id))

    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

# -------------------------
# DELETE (MOVE TO TRASH)
# -------------------------
@app.route('/admin/delete/<int:booking_id>')
def delete_booking(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE bookings SET is_deleted=1 WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_dashboard'))

# -------------------------
# VIEW TRASH
# -------------------------
@app.route('/admin/trash')
def admin_trash():
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DATABASE)
    conn.row_factory = sqlite3.Row
    c = conn.cursor()
    c.execute("SELECT * FROM bookings WHERE is_deleted=1 ORDER BY created_at DESC")
    bookings = c.fetchall()
    conn.close()

    return render_template('admin/trash.html', bookings=bookings)

# -------------------------
# RESTORE
# -------------------------
@app.route('/admin/restore/<int:booking_id>')
def restore_booking(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("UPDATE bookings SET is_deleted=0 WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_trash'))

# -------------------------
# PERMANENT DELETE
# -------------------------
@app.route('/admin/permanent_delete/<int:booking_id>')
def permanent_delete_booking(booking_id):
    if not session.get('admin_logged_in'):
        return redirect(url_for('admin_login'))

    conn = sqlite3.connect(DATABASE)
    c = conn.cursor()
    c.execute("DELETE FROM bookings WHERE id=?", (booking_id,))
    conn.commit()
    conn.close()

    return redirect(url_for('admin_trash'))

# -------------------------
# ADMIN LOGOUT
# -------------------------
@app.route('/admin/logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    return redirect(url_for('admin_login'))

# -------------------------
# RUN APP
# -------------------------
if __name__ == '__main__':
    app.run(debug=True)
