from flask import Flask, render_template, request, redirect, url_for, flash, send_from_directory, jsonify, session
from flask_sqlalchemy import SQLAlchemy
from flask_login import LoginManager, UserMixin, login_user, logout_user, login_required, current_user
from werkzeug.utils import secure_filename
from flask_socketio import SocketIO, emit
from flask_cors import CORS
import os
import base64
from datetime import datetime, timedelta, time as dtime  # ✅ correct alias
from sqlalchemy.orm import joinedload
from collections import defaultdict
from calendar import monthrange, day_name
import calendar
from sqlalchemy import inspect
import json
import time as time_module  # ✅ for time.sleep() or timestamps
from datetime import datetime, date
from flask import send_from_directory
from datetime import datetime, timedelta



app = Flask(__name__)
app.secret_key = "ims_secret"


CORS(app)
socketio = SocketIO(app, cors_allowed_origins="*")
app.config["UPLOAD_FOLDER"] = os.path.join(os.getcwd(), "uploads")
os.makedirs(app.config["UPLOAD_FOLDER"], exist_ok=True)


# ✅ Added: custom fromjson filter
@app.template_filter("fromjson")
def fromjson_filter(value):
    try:
        return json.loads(value)
    except Exception:
        return value

# ==========================
# DATABASE (MySQL)
# ==========================
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://root:@localhost/ims_db"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

db = SQLAlchemy(app)
login_manager = LoginManager(app)
login_manager.login_view = "index"

# ==========================
# UPLOADS FOLDER
# ==========================
UPLOAD_FOLDER = os.path.join(os.path.dirname(__file__), "uploads")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

# ==========================
# MODELS
# ==========================
class User(UserMixin, db.Model):
    __tablename__ = "user"

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(100))
    role = db.Column(db.String(50))  # 'admin', 'student', 'hte', 'parent'
    total_hours = db.Column(db.Float, default=0)

    # Foreign keys
    parent_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    hte_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)
    selected_student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=True)

    # ✅ Relationships
    parent = db.relationship(
        'User',
        remote_side=[id],
        backref='children',
        foreign_keys=[parent_id]
    )

    hte = db.relationship(
        'User',
        foreign_keys=[hte_id],
        remote_side=[id],
        backref='students'
    )

    selected_student = db.relationship(
        'User',
        foreign_keys=[selected_student_id],
        remote_side=[id],
        post_update=True,
        backref='selected_by_parents'
    )


class Requests(db.Model):
    __tablename__ = "requests"
    id = db.Column(db.Integer, primary_key=True)
    student_name = db.Column(db.String(150))
    details = db.Column(db.Text)

class Endorsement(db.Model):
    __tablename__ = "endorsement"
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    hte_id = db.Column(db.Integer, db.ForeignKey("user.id"))
    title = db.Column(db.String(150))
    description = db.Column(db.Text)
    status = db.Column(db.String(50), default="Requested")
    admin_comment = db.Column(db.Text)
    endorsement_file = db.Column(db.String(255))
    hte_endorsement_file = db.Column(db.String(255))
    student = db.relationship("User", foreign_keys=[student_id], backref="endorsements")
    hte = db.relationship("User", foreign_keys=[hte_id])

class Attendance(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    file_name = db.Column(db.String(255))
    date = db.Column(db.Date, nullable=False)  # ✅ This is the missing column
    timestamp = db.Column(db.DateTime, nullable=False)
    in_am = db.Column(db.DateTime)
    out_am = db.Column(db.DateTime)
    in_pm = db.Column(db.DateTime)
    out_pm = db.Column(db.DateTime)
    total_hours = db.Column(db.Float)
    present = db.Column(db.Boolean, default=False)
    hte_approved = db.Column(db.Boolean, default=False)
    is_deleted = db.Column(db.Boolean, default=False)



    student = db.relationship('User', backref='attendances')
    


class DailyLog(db.Model):
    __tablename__ = 'daily_log'

    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey('user.id'))
    attendance_id = db.Column(db.Integer, db.ForeignKey('attendance.id'))  # Link to Attendance
    date = db.Column(db.Date)
    time = db.Column(db.Time)
    total_hours = db.Column(db.Float, default=0)
    in_am = db.Column(db.Time)
    out_am = db.Column(db.Time)
    in_pm = db.Column(db.Time)
    out_pm = db.Column(db.Time)
    description = db.Column(db.String(255))  # ✅ Added description column
    visible_to_admin = db.Column(db.Boolean, default=False)  # Control visibility in Admin view

    # Relationship
    student = db.relationship('User', backref=db.backref('daily_logs', lazy=True))
class DailyAccomplishment(db.Model):
    __tablename__ = "daily_accomplishment"
    
    id = db.Column(db.Integer, primary_key=True)
    student_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    date = db.Column(db.Date, nullable=False)
    accomplishment = db.Column(db.Text, nullable=False)  # JSON list of filenames



class ChatMessage(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    sender_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    receiver_id = db.Column(db.Integer, db.ForeignKey('user.id'), nullable=False)
    
    sender_role = db.Column(db.String(50), nullable=False)
    receiver_role = db.Column(db.String(50), nullable=False)
    
    content = db.Column(db.Text, nullable=False)  # message content
    timestamp = db.Column(db.DateTime, default=datetime.utcnow)
    read = db.Column(db.Boolean, default=False)
    
    # Relationships
    sender = db.relationship('User', foreign_keys=[sender_id], backref='sent_messages')
    receiver = db.relationship('User', foreign_keys=[receiver_id], backref='received_messages')

class Student(db.Model):
    __tablename__ = 'student'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)
    total_hours = db.Column(db.Float, default=0)
    remaining_hours = db.Column(db.Float, default=0)

    # Foreign key (each student is assigned to one HTE)
    hte_id = db.Column(db.Integer, db.ForeignKey('hte.id'))
    parent_id = db.Column(db.Integer, db.ForeignKey('parent.id'), nullable=True)
    



# 🔹 Define HTE AFTER Student, so the reference is recognized
class HTE(db.Model):
    __tablename__ = 'hte'

    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100), nullable=False)
    username = db.Column(db.String(100), unique=True, nullable=False)
    password = db.Column(db.String(200), nullable=False)

    # Relationship (one HTE can have many Students)
    students = db.relationship('Student', backref='hte', lazy=True)
# ==========================
# HELPER FUNCTION: Compute and Save Total Hours
# ==========================
def calculate_total_hours(student_id):
    """Compute total rendered hours based only on HTE-approved attendance."""
    REQUIRED_HOURS = 600
    attendances = Attendance.query.filter_by(
        student_id=student_id, hte_approved=True
    ).all()

    total_hours = sum(a.total_hours or 0 for a in attendances)
    remaining_hours = max(REQUIRED_HOURS - total_hours, 0)

    # ✅ Save automatically to User table
    student = User.query.get(student_id)
    if student:
        student.total_hours = round(total_hours, 2)
        # If you have remaining_hours column, include this line:
        # student.remaining_hours = round(remaining_hours, 2)
        db.session.commit()

    return round(total_hours, 2)


# ==========================
# HELPER FUNCTION: Convert to Datetime
# ==========================
def to_datetime(value):
    """Convert date or time value into a datetime object safely."""
    if isinstance(value, datetime):
        return value
    elif isinstance(value, dtime):  # ✅ use dtime, not time
        return datetime.combine(datetime.today(), value)
    elif isinstance(value, str):
        try:
            return datetime.fromisoformat(value)
        except ValueError:
            return None
    else:
        return None

def compute_total_hours(log):
    """Compute total hours worked per log."""
    total = 0
    if log.in_am and log.out_am:
        total += (datetime.combine(log.date, log.out_am) - datetime.combine(log.date, log.in_am)).total_seconds() / 3600
    if log.in_pm and log.out_pm:
        total += (datetime.combine(log.date, log.out_pm) - datetime.combine(log.date, log.in_pm)).total_seconds() / 3600
    return total

def fmt_time(val):
    """Format time safely."""
    if val:
        return val.strftime("%I:%M %p")
    return "—"
def fmt_date(val, fmt="%Y-%m-%d"):
    """
    Safely format a date or datetime object to a string.
    Returns an empty string if val is None or not a date/datetime.
    """
    if val is None:
        return ""
    
    if isinstance(val, (datetime, date)):
        return val.strftime(fmt)
    
    if isinstance(val, str):
        return val
    
    return str(val)



# ==========================
# PARENT MODEL
# ==========================
class Parent(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    name = db.Column(db.String(100))
    username = db.Column(db.String(50), unique=True)
    password = db.Column(db.String(100))

@app.template_filter('from_json')
def from_json(value):
    try:
        return json.loads(value)
    except Exception:
        return []

# ==========================
# LOGIN MANAGER
# ==========================
@login_manager.user_loader
def load_user(user_id):
    return db.session.get(User, int(user_id))


# ==========================
# ROUTES
# ==========================
@app.route("/")
def index():
    return render_template("login.html")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name = request.form["name"]
        username = request.form["username"]
        password = request.form["password"]
        role = request.form["role"]

        user = User(name=name, username=username, password=password, role=role)
        db.session.add(user)
        db.session.commit()
        flash("Registration successful! Please login.", "success")
        return redirect(url_for("index"))
    return render_template("register.html")

@app.route("/login", methods=["POST"])
def login():
    username = request.form["username"]
    password = request.form["password"]
    role = request.form["role"]

    user = User.query.filter_by(username=username, role=role).first()
    if user and user.password == password:
        login_user(user, remember="remember" in request.form)
        if user.role == "admin":
            return redirect(url_for("admin_dashboard"))
        elif user.role == "student":
            return redirect(url_for("student_dashboard"))
        elif user.role == "hte":
            return redirect(url_for("hte_dashboard"))
        elif user.role == "parent":
            return redirect(url_for("parent_dashboard"))
    flash("Invalid credentials!", "danger")
    return redirect(url_for("index"))

@app.route("/logout")
def logout():
    logout_user()
    return redirect(url_for("index"))

# ==========================
# DASHBOARDS
# ==========================
@app.route("/admin")
@login_required
def admin_dashboard():
    # Only allow admin users
    if current_user.role != "admin":
        return redirect(url_for("index"))

    # Count unread messages for the admin
    unread_count = ChatMessage.query.filter_by(
        receiver_id=current_user.id, read=False
    ).count()

    # Fetch users by role
    students = User.query.filter_by(role="student").all()
    parents = User.query.filter_by(role="parent").all()
    htes = User.query.filter_by(role="hte").all()

    # Fetch all endorsements with their related students
    endorsements = Endorsement.query.options(joinedload(Endorsement.student)).all()

    # Required OJT hours
    REQUIRED_HOURS = 600

    # Compute total and remaining hours per student
    for student in students:
        attendances = Attendance.query.filter_by(
            student_id=student.id, hte_approved=True
        ).all()

        # Sum hours: prioritize `hours_rendered`, fallback to 1 if no field
        total_hours = 0
        for a in attendances:
            if hasattr(a, "hours_rendered") and a.hours_rendered is not None:
                total_hours += a.hours_rendered
            else:
                total_hours += 1  # default to 1 hour per attendance if not specified

        remaining_hours = max(REQUIRED_HOURS - total_hours, 0)
        student.total_hours = round(total_hours, 2)
        student.remaining_hours = round(remaining_hours, 2)

        # Optional: save to DB if you store total_hours/remaining_hours in User table
        db_user = db.session.get(User, student.id)
        if db_user:
            db_user.total_hours = student.total_hours
            db_user.remaining_hours = student.remaining_hours

    db.session.commit()

    # Group attendance by student and month
    from collections import defaultdict

    attendance_records_by_student = {}
    for student in students:
        records = Attendance.query.filter_by(
            student_id=student.id, hte_approved=True
        ).order_by(Attendance.timestamp.desc()).all()

        records_by_month = defaultdict(list)
        for r in records:
            month_str = r.timestamp.strftime("%B %Y")
            records_by_month[month_str].append(r)

        attendance_records_by_student[student.id] = dict(records_by_month)

    # Logs for students with approved attendance
    approved_student_ids = [
        sid[0] for sid in db.session.query(Attendance.student_id)
        .filter(Attendance.hte_approved == True)
        .distinct()
        .all()
    ]

    all_logs = {
        student.id: DailyLog.query.filter_by(student_id=student.id, visible_to_admin=True)
        .order_by(DailyLog.date.desc())
        .all()
        for student in students
        if student.id in approved_student_ids
    }

    # Render Admin Dashboard
    return render_template(
        "dashboard_admin.html",
        students=students,
        parents=parents,
        htes=htes,
        endorsements=endorsements,
        unread_count=unread_count,
        all_logs=all_logs,
        attendance_records_by_student=attendance_records_by_student
    )


# ==========================
# ✅ ASSIGN HTE ENDPOINT
# ==========================
@app.route("/assign_hte", methods=["POST"])
@login_required
def assign_hte():
    if current_user.role != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    student_id = request.form.get("student_id")
    hte_id = request.form.get("hte_id")

    if not student_id or not hte_id:
        return jsonify({"success": False, "message": "Missing student or HTE ID"}), 400

    student = User.query.get(student_id)
    hte = User.query.get(hte_id)

    if not student or not hte:
        return jsonify({"success": False, "message": "Invalid student or HTE"}), 404

    # ✅ Assign HTE to student + update endorsements
    student.hte_id = hte.id
    endorsements = Endorsement.query.filter_by(student_id=student.id).all()
    for e in endorsements:
        e.hte_id = hte.id

    db.session.commit()
    return jsonify({"success": True, "message": f"Assigned {hte.name} to {student.name}"})


# ==========================
# ✅ ATTENDANCE GROUPING HELPER
# ==========================
def group_attendance(attendance_records):
    """
    Groups attendance by 5-day intervals and limits to 4 captures per day.
    """
    grouped = []
    if not attendance_records:
        return grouped

    start_date = attendance_records[0].timestamp.date()
    current_group = {"start": start_date, "end": start_date, "records": []}
    day_counter = 0
    current_day_records = []

    for att in attendance_records:
        att_date = att.timestamp.date()

        # New day
        if not current_day_records or current_day_records[-1].timestamp.date() != att_date:
            if current_day_records:
                # Keep max 4 captures per day
                current_group["records"].append(current_day_records[:4])
                day_counter += 1
                current_day_records = []

            # If reached 5 days → new group
            if day_counter == 5:
                grouped.append(current_group)
                current_group = {"start": att_date, "end": att_date, "records": []}
                day_counter = 0

        current_day_records.append(att)
        current_group["end"] = att_date

    # Add last day's records
    if current_day_records:
        current_group["records"].append(current_day_records[:4])

    if current_group["records"]:
        grouped.append(current_group)

    return grouped

@app.route("/student_dashboard")
@login_required
def student_dashboard():
    # ✅ Ensure only students can access
    if current_user.role != "student":
        return redirect(url_for("index"))

    # ✅ Get student endorsements
    my_endorsements = Endorsement.query.filter_by(student_id=current_user.id).all()

    # ✅ Attendance (active + deleted)
    active_attendance = Attendance.query.filter_by(
        student_id=current_user.id,
        is_deleted=False
    ).order_by(Attendance.timestamp.desc()).all()

    deleted_attendance = Attendance.query.filter_by(
        student_id=current_user.id,
        is_deleted=True
    ).order_by(Attendance.timestamp.desc()).all()

    grouped_attendance = group_attendance(active_attendance)

    # ✅ Get student's Daily Accomplishment Reports (DAR)
    dar_records = DailyAccomplishment.query.filter_by(
        student_id=current_user.id
    ).order_by(DailyAccomplishment.date.desc()).all()

    # ✅ Get student's Daily Logs
    daily_logs = DailyLog.query.filter_by(
        student_id=current_user.id
    ).order_by(DailyLog.date.desc()).all()

    # ✅ Safely convert total_hours to float
    for log in daily_logs:
        try:
            log.total_hours = float(log.total_hours or 0)
        except (TypeError, ValueError):
            log.total_hours = 0.0

    # ✅ Compute total and remaining hours safely
    total_hours_done = round(sum(log.total_hours for log in daily_logs), 2)
    remaining_hours = round(600 - total_hours_done, 2)

    # ✅ Unread message counts
    unread_count = ChatMessage.query.filter_by(
        receiver_id=current_user.id, sender_role="admin", read=False
    ).count()

    hte_unread_count = ChatMessage.query.filter_by(
        receiver_id=current_user.id, sender_role="hte", read=False
    ).count()

    # ✅ Get list of students (optional)
    students = User.query.filter_by(role="student").all()

    # ✅ Render template
    return render_template(
        "dashboard_student.html",
        requests=my_endorsements,
        attendance_groups=grouped_attendance,
        attendance=active_attendance,
        deleted_attendance=deleted_attendance,
        dar_records=dar_records,
        daily_logs=daily_logs,
        total_hours_done=total_hours_done,
        remaining_hours=remaining_hours,
        unread_count=unread_count,
        hte_unread_count=hte_unread_count,
        students=students
    )





# ==========================
# 🧭 HTE DASHBOARD
# ==========================
@app.route("/hte")
@login_required
def hte_dashboard():
    if current_user.role != "hte":
        return redirect(url_for("index"))

    # ✅ Get endorsements
    endorsements = (
        Endorsement.query
        .join(User, Endorsement.student_id == User.id)
        .filter(User.hte_id == current_user.id)
        .options(joinedload(Endorsement.student))
        .all()
    )

    # ✅ Get attendance
    attendance_records = (
        Attendance.query
        .join(User, Attendance.student_id == User.id)
        .filter(User.hte_id == current_user.id)
        .options(joinedload(Attendance.student))
        .order_by(Attendance.timestamp.asc())
        .all()
    )

    # ✅ Smart grouping
    grouped_attendance = defaultdict(lambda: defaultdict(lambda: defaultdict(list)))

    # Organize all records first by student and month
    temp_data = defaultdict(lambda: defaultdict(list))

    for record in attendance_records:
        student_name = record.student.name or f"Student-{record.student.id}"
        month_key = record.timestamp.strftime("%B %Y")
        temp_data[student_name][month_key].append(record)

    # Now decide: full month or week range
    for student, months in temp_data.items():
        for month_key, records in months.items():
            # Determine first and last day in this month’s records
            dates = sorted([r.timestamp.date() for r in records])
            start_date = dates[0]
            end_date = dates[-1]
            total_days = (end_date - start_date).days + 1

            # ✅ If attendance covers most of the month (≈25+ days), group by month
            if total_days >= 25:
                grouped_attendance[student][month_key]["Full Month"].extend(records)
            else:
                # ✅ Otherwise, group by week ranges (7-day chunks)
                week_start = start_date
                week_index = 1

                while week_start <= end_date:
                    week_end = min(week_start + timedelta(days=6), end_date)
                    week_label = f"Week {week_index} ({week_start.strftime('%b %d')}–{week_end.strftime('%d')})"
                    week_records = [r for r in records if week_start <= r.timestamp.date() <= week_end]
                    grouped_attendance[student][month_key][week_label].extend(week_records)
                    week_index += 1
                    week_start = week_end + timedelta(days=1)

    # ✅ Count unread messages
    unread_count = ChatMessage.query.filter_by(
        receiver_id=current_user.id,
        sender_role="student",
        read=False
    ).count()

    # ✅ Get all students assigned to this HTE for messaging
    assigned_students = User.query.filter_by(hte_id=current_user.id, role="student").all()

    return render_template(
        "dashboard_hte.html",
        requests=endorsements,
        grouped_attendance=grouped_attendance,
        unread_count=unread_count,
        assigned_students=assigned_students
    )

# 📄 View Accomplishment Reports (HTE side)
@app.route("/hte/accomplishment_reports/<int:hte_id>")
@login_required
def hte_accomplishment_reports(hte_id):
    if current_user.role != "hte" or current_user.id != hte_id:
        flash("Access denied.", "danger")
        return redirect(url_for("index"))

    # Get all students assigned to this HTE
    students = User.query.filter_by(hte_id=hte_id, role="student").all()

    # Collect their accomplishment report files (assuming stored in 'accomplishment_reports' folder)
    accomplishment_files = []
    for student in students:
        # Assuming each student can have multiple accomplishment reports saved in DB or folder
        folder_path = os.path.join(app.config["UPLOAD_FOLDER"], "accomplishment_reports", str(student.id))
        if os.path.exists(folder_path):
            for filename in os.listdir(folder_path):
                file_url = url_for("download_file", filename=f"accomplishment_reports/{student.id}/{filename}")
                accomplishment_files.append({
                    "student_name": student.name,
                    "filename": filename,
                    "file_url": file_url
                })

    return render_template("hte_accomplishment_reports.html", accomplishment_files=accomplishment_files)

@app.route("/hte/view_accomplishments/<int:student_id>")
@login_required
def hte_view_accomplishments(student_id):
    if current_user.role != "hte":
        return "Access Denied", 403

    # Ensure student is assigned to this HTE
    student = User.query.filter_by(id=student_id, hte_id=current_user.id).first()
    if not student:
        return "<p class='text-danger text-center'>Student not found or not assigned to you.</p>"

    dar_records = DailyAccomplishment.query.filter_by(student_id=student.id).order_by(DailyAccomplishment.date.desc()).all()

    if not dar_records:
        return "<p class='text-center text-muted'>No accomplishment reports uploaded yet.</p>"

    # Render only the table part
    html = render_template("hte_student_accomplishments.html", student=student, dar_records=dar_records)
    return html


@app.route('/view_hte/<int:hte_id>')
@login_required
def view_hte(hte_id):
    # Find the selected HTE
    hte = HTE.query.get_or_404(hte_id)

    # Get all students assigned to this HTE
    students = Student.query.filter_by(hte_id=hte.id).all()

    return render_template('view_hte.html', hte=hte, students=students)


# ==========================
# 🧭 PARENT DASHBOARD
# ==========================
from collections import defaultdict

@app.route("/parent", methods=['GET', 'POST'])
@login_required
def parent_dashboard():
    if current_user.role != "parent":
        return redirect(url_for("index"))

    # Get all children of the parent
    students = User.query.filter_by(parent_id=current_user.id, role="student").all()

    selected_student = None
    dar_records = []
    attendance_records_by_month = defaultdict(list)

    # Get selected student from session or attribute
    selected_student_id = getattr(current_user, "selected_student_id", None) or session.get("selected_student_id")
    if selected_student_id:
        selected_student = User.query.get(selected_student_id)

    # Fallback: pick first child if none selected
    if not selected_student and students:
        selected_student = students[0]

    # Fetch attendance records grouped by month
    if selected_student:
        attendance_records = Attendance.query.filter_by(
            student_id=selected_student.id, present=True
        ).order_by(Attendance.timestamp.desc()).all()

        for a in attendance_records:
            month = a.timestamp.strftime("%B %Y")
            attendance_records_by_month[month].append(a)

        # Fetch Daily Accomplishment records
        dar_records = DailyAccomplishment.query.filter_by(
            student_id=selected_student.id
        ).order_by(DailyAccomplishment.date.desc()).all()

    return render_template(
        "dashboard_parent.html",
        students=students,
        selected_student=selected_student,
        attendance_records_by_month=attendance_records_by_month,
        dar_records=dar_records
    )
@app.route('/parent/select_student/<int:student_id>', methods=['POST'])
@login_required
def parent_select_student(student_id):
    if current_user.role != 'parent':
        flash("Only parents can select a student.", "danger")
        return redirect(url_for('parent_dashboard'))

    student = User.query.get(student_id)
    if not student or student.role != 'student':
        flash("Invalid student selected.", "danger")
        return redirect(url_for('parent_dashboard'))

    # Link parent and student
    student.parent_id = current_user.id
    db.session.commit()

    flash("Child assigned successfully.", "success")
    return redirect(url_for('parent_dashboard'))


# ==========================
# 💬 STUDENT–ADMIN CHAT ROUTES
# ==========================
@app.route('/student_chat')
@login_required
def student_chat():
    if current_user.role != "student":
        return redirect(url_for("index"))

    # ✅ Default admin is user with role="admin" (first one found)
    admin_user = User.query.filter_by(role="admin").first()
    if not admin_user:
        flash("No admin found.", "danger")
        return redirect(url_for("index"))

    # ✅ Load chat messages between current student and admin
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == admin_user.id)) |
        ((ChatMessage.sender_id == admin_user.id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc()).all()

    # ✅ Mark all unread messages received by student as read
    unread_msgs = ChatMessage.query.filter_by(receiver_id=current_user.id, read=False).all()
    for msg in unread_msgs:
        msg.read = True
    db.session.commit()

    return render_template('chat.html', role='student', messages=messages, admin=admin_user)


@app.route('/admin_chat/<int:student_id>')
@login_required
def admin_chat(student_id):
    if current_user.role != "admin":
        return redirect(url_for("index"))

    student = User.query.get_or_404(student_id)

    # Load messages between admin and this student
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == student.id)) |
        ((ChatMessage.sender_id == student.id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc()).all()

    return render_template('chat.html', role='admin', student=student, messages=messages)

# Message route
@app.route("/admin_chat_hte/<int:hte_id>")
@login_required
def admin_chat_hte(hte_id):
    hte = User.query.get_or_404(hte_id)
    return render_template("chat_admin_hte.html", hte=hte)

@app.route("/get_messages/<int:receiver_id>")
@login_required
def get_messages(receiver_id):
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.receiver_id == receiver_id)) |
        ((ChatMessage.sender_id == receiver_id) & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc()).all()

    # Convert messages to JSON-friendly format
    messages_data = [
        {
            "id": msg.id,
            "sender_id": msg.sender_id,
            "receiver_id": msg.receiver_id,
            "sender_role": msg.sender_role,
            "receiver_role": msg.receiver_role,
            "content": msg.content,
            "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M"),
            "read": msg.read
        }
        for msg in messages
    ]

    return jsonify(messages_data)

# Upload Important File
@app.route("/upload_hte_file/<int:hte_id>", methods=["POST"])
@login_required
def upload_hte_file(hte_id):
    file = request.files.get("hte_file")
    if file:
        filename = secure_filename(file.filename)
        filepath = os.path.join(app.config["UPLOAD_FOLDER"], filename)
        file.save(filepath)
        # store filename in DB related to HTE
        hte = User.query.get(hte_id)
        hte.files = (hte.files or []) + [filename]  # assuming files stored as JSON list
        db.session.commit()
        flash("File uploaded successfully!", "success")
    return redirect(url_for("dashboard_admin"))



# Send message between admin and HTE
# -------------------- Send message Admin -> HTE & HTE -> Admin --------------------
@app.route("/send_admin_hte_message/<int:hte_id>", methods=["POST"])
@login_required
def send_admin_hte_message(hte_id):
    data = request.get_json()
    content = data.get("content", "").strip()
    if not content:
        return jsonify(success=False, message="Empty message.")

    # Determine sender and receiver
    if current_user.role == "admin":
        sender_role = "admin"
        receiver_role = "hte"
        receiver_id = hte_id
    else:
        sender_role = "hte"
        receiver_role = "admin"
        admin = User.query.filter_by(role="admin").first()
        receiver_id = admin.id if admin else None

    if not receiver_id:
        return jsonify(success=False, message="No admin found.")

    msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        sender_role=sender_role,
        receiver_role=receiver_role,
        content=content
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify(
        success=True,
        message_id=msg.id,
        timestamp=msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    )


# -------------------- Get messages Admin <-> HTE --------------------
@app.route("/get_admin_hte_messages/<int:hte_id>")
@login_required
def get_admin_hte_messages(hte_id):
    after_id = request.args.get("after_id", type=int)

    if current_user.role == "admin":
        user_id = hte_id
        partner_id = current_user.id
    else:
        user_id = current_user.id
        admin = User.query.filter_by(role="admin").first()
        partner_id = admin.id if admin else None

    if not partner_id:
        return jsonify(messages=[])

    query = ChatMessage.query.filter(
        ((ChatMessage.sender_id == user_id) & (ChatMessage.receiver_id == partner_id)) |
        ((ChatMessage.sender_id == partner_id) & (ChatMessage.receiver_id == user_id))
    ).order_by(ChatMessage.timestamp.asc())

    if after_id:
        query = query.filter(ChatMessage.id > after_id)

    messages = [
        {
            "id": m.id,
            "sender_name": m.sender.username if m.sender else "Unknown",
            "sender_role": m.sender_role,
            "content": m.content,
            "timestamp": m.timestamp.strftime("%Y-%m-%d %H:%M:%S"),
        }
        for m in query.all()
    ]

    return jsonify(messages=messages)

# -------------------- HTE Chat page --------------------
@app.route("/chat_hte_admin")
@login_required
def chat_hte_admin():
    if current_user.role != "hte":
        return redirect(url_for("index"))
    return render_template("chat_hte_admin.html")

# -------------------- HTE sends message to Admin --------------------
@app.route("/send_hte_admin_message", methods=["POST"])
@login_required
def send_hte_admin_message():
    if current_user.role != "hte":
        return jsonify({"success": False})

    data = request.get_json()
    content = data.get("content", "").strip()
    if not content:
        return jsonify({"success": False, "message": "Empty message."})

    admin = User.query.filter_by(role="admin").first()
    if not admin:
        return jsonify({"success": False, "message": "No admin found."})

    msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=admin.id,
        sender_role="hte",
        receiver_role="admin",
        content=content
    )
    db.session.add(msg)
    db.session.commit()

    return jsonify({
        "success": True,
        "message_id": msg.id,
        "timestamp": msg.timestamp.strftime("%Y-%m-%d %H:%M:%S")
    })



# 📁 Important Files - Admin & HTE Shared View
@app.route("/admin_files_hte/<int:hte_id>")
@login_required
def admin_files_hte(hte_id):
    hte = User.query.get_or_404(hte_id)
    # Assuming HTE's files are stored as JSON list or comma-separated string
    files = []
    if hte.files:
        try:
            if isinstance(hte.files, str):
                files = json.loads(hte.files)
            elif isinstance(hte.files, list):
                files = hte.files
        except Exception:
            files = [hte.files]
    return render_template("admin_files_hte.html", hte=hte, files=files)


@app.route("/download_hte_file/<path:filename>")
@login_required
def download_hte_file(filename):
    upload_folder = os.path.join(app.root_path, "uploads_hte")  # adjust folder name
    return send_from_directory(upload_folder, filename, as_attachment=True)
# ==========================
# 💬 STUDENT–HTE CHAT ROUTES
# ==========================
@app.route('/student_hte_chat')
@login_required
def student_hte_chat():
    if current_user.role != "student":
        return redirect(url_for("index"))

    # ✅ Show student ↔ HTE messages
    messages = get_hte_messages_for_student(current_user.id)
    mark_hte_messages_as_read(current_user.id)
    return render_template('student_hte_chat.html', messages=messages)

# ==========================
# 💬 HELPER FUNCTIONS FOR HTE CHAT
# ==========================
def get_hte_messages_for_student(student_id):
    return ChatMessage.query.filter(
        ((ChatMessage.sender_id == student_id) & (ChatMessage.sender_role == "student")) |
        ((ChatMessage.receiver_id == student_id) & (ChatMessage.sender_role == "hte"))
    ).order_by(ChatMessage.timestamp.asc()).all()


def mark_hte_messages_as_read(student_id):
    ChatMessage.query.filter_by(receiver_id=student_id, sender_role="hte", read=False).update({"read": True})
    db.session.commit()


def get_messages_for_hte(hte_id):
    return ChatMessage.query.filter(
        ((ChatMessage.sender_id == hte_id) & (ChatMessage.sender_role == "hte")) |
        ((ChatMessage.receiver_id == hte_id) & (ChatMessage.sender_role == "student"))
    ).order_by(ChatMessage.timestamp.asc()).all()


def mark_student_messages_as_read(hte_id):
    ChatMessage.query.filter_by(receiver_id=hte_id, sender_role="student", read=False).update({"read": True})
    db.session.commit()


# ==========================
# 💬 ROUTES
# ==========================
@app.route('/hte_chat')
@login_required
def hte_chat():
    if current_user.role != "hte":
        return redirect(url_for("index"))

    # ✅ Get all messages where current HTE is sender or receiver
    messages = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.sender_role == "hte")) |
        ((ChatMessage.receiver_id == current_user.id) & (ChatMessage.sender_role == "student"))
    ).order_by(ChatMessage.timestamp.asc()).all()

    # ✅ Mark all unread student messages as read
    unread_msgs = ChatMessage.query.filter_by(
        receiver_id=current_user.id,
        sender_role="student",
        read=False
    ).all()
    for msg in unread_msgs:
        msg.read = True
    db.session.commit()

    return render_template('hte_chat.html', messages=messages)


@app.route('/send_hte_message', methods=['POST'])
@login_required
def send_hte_message():
    # ✅ Allow only students or HTEs
    if getattr(current_user, "role", "").lower() not in ["student", "hte"]:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    receiver_id = data.get("receiver_id")
    message_text = (data.get("message") or "").strip()

    if not receiver_id or not message_text:
        return jsonify({"success": False, "error": "Message cannot be empty."})

    # Determine roles
    if current_user.role.lower() == "student":
        sender_role = "student"
        receiver_role = "hte"
        # Optional: ensure student has assigned HTE
        if not current_user.hte or current_user.hte.id != receiver_id:
            return jsonify({"success": False, "error": "Invalid HTE recipient."}), 403
    else:
        sender_role = "hte"
        receiver_role = "student"

    new_message = ChatMessage(
        sender_id=current_user.id,
        receiver_id=receiver_id,
        sender_role=sender_role,
        receiver_role=receiver_role,
        content=message_text,
        read=False
    )

    db.session.add(new_message)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": new_message.content,
        "timestamp": new_message.timestamp.strftime("%b %d, %I:%M %p")
    })

@app.route("/hte_chat_admin")
@login_required
def hte_chat_admin():
    if current_user.role != "hte":
        return redirect(url_for("index"))
    return render_template("chat_admin_hte.html", hte=current_user)


# ==========================
# 💬 Get messages for a selected student (AJAX)
# ==========================
@app.route("/hte/get_messages/<int:student_id>")
@login_required
def hte_get_messages(student_id):
    if current_user.role != "hte":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    # Optional: fetch only new messages after a timestamp
    after_timestamp = request.args.get("after")

    query = ChatMessage.query.filter(
        ((ChatMessage.sender_id == current_user.id) & (ChatMessage.sender_role == "hte") & (ChatMessage.receiver_id == student_id)) |
        ((ChatMessage.sender_id == student_id) & (ChatMessage.sender_role == "student") & (ChatMessage.receiver_id == current_user.id))
    ).order_by(ChatMessage.timestamp.asc())

    if after_timestamp:
        try:
            after_dt = datetime.fromisoformat(after_timestamp)
            query = query.filter(ChatMessage.timestamp > after_dt)
        except:
            pass  # ignore invalid timestamp

    messages = query.all()
    messages_list = [{
        "id": m.id,
        "sender_id": m.sender_id,
        "receiver_id": m.receiver_id,
        "sender_role": m.sender_role,
        "content": m.content,
        "timestamp": m.timestamp.isoformat(),
        "sender_name": current_user.name if m.sender_role=="hte" else m.receiver.name if m.receiver else "Student"
    } for m in messages]

    # Mark messages from student as read
    ChatMessage.query.filter_by(receiver_id=current_user.id, sender_id=student_id, sender_role="student", read=False).update({"read": True})
    db.session.commit()

    return jsonify({"success": True, "messages": messages_list})

@app.route("/hte/send_message/<int:student_id>", methods=["POST"])
@login_required
def hte_send_message(student_id):
    if current_user.role != "hte":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()
    if not content:
        return jsonify({"success": False, "error": "Message cannot be empty."})

    # Create new ChatMessage
    new_msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=student_id,
        sender_role="hte",
        receiver_role="student",
        content=content,
        read=False
    )
    db.session.add(new_msg)
    db.session.commit()

    return jsonify({
        "success": True,
        "message": new_msg.content,
        "timestamp": new_msg.timestamp.isoformat()
    })

# ==========================
# 💬 Send message to a student (AJAX)
# ==========================
@app.route("/hte/send_message/<int:student_id>", methods=["POST"])
@login_required
def send_message_to_student(student_id):
    if current_user.role != "hte":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    data = request.get_json(silent=True) or {}
    content = (data.get("content") or "").strip()

    if not content:
        return jsonify({"success": False, "message": "Message cannot be empty."})

    # Create new message
    new_msg = ChatMessage(
        sender_id=current_user.id,
        receiver_id=student_id,
        sender_role="hte",
        receiver_role="student",
        content=content,
        read=False
    )
    db.session.add(new_msg)
    db.session.commit()

    return jsonify({"success": True, "content": new_msg.content, "timestamp": new_msg.timestamp.strftime("%b %d, %I:%M %p")})





# 💾 CHAT MESSAGE SAVE (AJAX)
# ==========================
@app.route("/send_message", methods=["POST"])
@login_required
def send_message():
    data = request.get_json()
    receiver_id = data.get("receiver_id")
    content = data.get("content")

    if not receiver_id or not content:
        return jsonify({"error": "Missing receiver or content"}), 400

    receiver = User.query.get(receiver_id)
    if not receiver:
        return jsonify({"error": "Receiver not found"}), 404

    new_message = ChatMessage(
        sender_id=current_user.id,
        receiver_id=receiver.id,
        sender_role=current_user.role,
        receiver_role=receiver.role,
        content=content,
        timestamp=datetime.utcnow(),
        read=False
    )
    db.session.add(new_message)
    db.session.commit()

    return jsonify({"success": True, "message": "Message sent!"})


# ==========================
# ADMIN VIEW USER
# ==========================
@app.route("/admin/user/<int:user_id>")
@login_required
def admin_view_user(user_id):
    if current_user.role != "admin":
        return redirect(url_for("index"))
    user = User.query.get_or_404(user_id)
    endorsements = Endorsement.query.filter_by(student_id=user.id).all() if user.role == "student" else None
    attendances = Attendance.query.filter_by(student_id=user.id, present=True).order_by(Attendance.timestamp.desc()).all() if user.role == "student" else None
    return render_template("admin_view_user.html", user=user, endorsements=endorsements, attendances=attendances)

# -------------------------------
# ✅ ADMIN DASHBOARD + VIEW STUDENTS
# -------------------------------
@app.route("/view_students")
@login_required
def view_students():
    if current_user.role != "admin":
        return redirect(url_for("student_dashboard"))

    # ✅ Get all students
    students = User.query.filter_by(role="student").all()

    # ✅ Load computed total & remaining hours for each student
    for s in students:
        s.total_hours = calculate_total_hours(s.id)
        s.remaining_hours = max(0, 600 - s.total_hours)

    # ✅ Fetch logs (optional, for dashboard)
    all_logs = {
        student.id: DailyLog.query.filter_by(student_id=student.id)
        .order_by(DailyLog.date.desc())
        .all()
        for student in students
    }

    return render_template(
        "dashboard_admin.html",
        students=students,
        all_logs=all_logs
    )

@app.route("/admin/attendance/<int:student_id>")
@login_required
def admin_attendance(student_id):
    if current_user.role != "admin":
        return redirect(url_for("index"))

    # Get student info
    student = User.query.get_or_404(student_id)

    # Fetch all attendance records for the student (group by month)
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.timestamp.desc()).all()
    attendance_records_by_month = defaultdict(list)
    for r in records:
        month = r.timestamp.strftime("%B %Y")
        attendance_records_by_month[month].append(r)

    return render_template(
        "admin_attendance.html",
        student=student,
        attendance_records_by_month=attendance_records_by_month
    )



# -------------------------------
# ✅ ATTENDANCE VIEW PER STUDENT
# -------------------------------
# ✅ View Attendance Calendar (Admin / HTE / Student)
@app.route("/attendance/<int:student_id>")
@login_required
def view_attendance(student_id):

    # Access Control
    if current_user.role not in ["admin", "hte", "student"]:
        return redirect(url_for("index"))

    # Student Info
    student = User.query.get_or_404(student_id)

    # All attendance records for this student
    records = Attendance.query.filter_by(student_id=student.id).order_by(Attendance.timestamp.asc()).all()

    # Build attendance grouped by date
    attendance_by_date = {}
    for r in records:
        date_str = r.timestamp.strftime("%Y-%m-%d")
        if date_str not in attendance_by_date:
            attendance_by_date[date_str] = []
        attendance_by_date[date_str].append(r)

    # Current month and year
    today = datetime.now()
    current_year = today.year
    current_month = today.month

    # Render Template
    return render_template(
        "attendance_calendar.html",
        student=student,
        attendance_by_date=attendance_by_date,
        current_year=current_year,
        current_month=current_month
    )


@app.route("/attendance_calendar/<int:student_id>/<int:year>/<int:month>")
@login_required
def attendance_calendar(student_id, year, month):
    student = User.query.get_or_404(student_id)

    # Get all attendance records for the month
    start_date = date(year, month, 1)
    end_date = date(year, month, monthrange(year, month)[1])
    records = Attendance.query.filter(
        Attendance.student_id == student.id,
        Attendance.timestamp.between(start_date, end_date)
    ).all()

    # Group attendance by day
    attendance_by_day = defaultdict(list)
    for rec in records:
        day = rec.timestamp.day
        attendance_by_day[day].append(rec)

    # Build 'days' list for the calendar
    days = []

    # Add empty cells for the first weekday
    first_weekday, num_days = monthrange(year, month)
    for _ in range(first_weekday):
        days.append(None)

    # Add each day with its records
    for day_num in range(1, num_days + 1):
        day_records = attendance_by_day.get(day_num, [])
        days.append({
            "date": date(year, month, day_num),
            "records": day_records
        })

    return render_template(
        "attendance_calendar.html",
        student=student,
        days=days,
        month_name=start_date.strftime("%B"),
        year=year
    )

# -------------------------------
# ✅ MESSAGE (CHAT) PAGE
# -------------------------------
@app.route("/message/<int:student_id>")
@login_required
def message_student(student_id):
    if current_user.role not in ["admin", "hte"]:
        return redirect(url_for("index"))

    student = User.query.get_or_404(student_id)
    return render_template("message_chat.html", student=student)

# -------------------------------
# ✅ VIDEO CALL PAGE
# -------------------------------
@app.route("/video_call/<int:student_id>")
@login_required
def video_call(student_id):
    if current_user.role not in ["admin", "hte"]:
        return redirect(url_for("index"))

    student = User.query.get_or_404(student_id)
    return render_template("video_call.html", student=student)

@app.route("/admin/view_dar/<int:user_id>")
@login_required
def admin_view_dar(user_id):
    # Fetch the student
    student = User.query.get_or_404(user_id)
    # Fetch DAR uploads for that student (adjust table name)
    dar_records = DailyAccomplishment.query.filter_by(student_id=user_id).all()
    return render_template("admin_view_dar.html", student=student, dar_records=dar_records)

# ==========================
# DELETE ENDORSEMENT
# ==========================
@app.route("/admin/endorsement/delete/<int:req_id>", methods=["POST"])
@login_required
def delete_endorsement(req_id):
    if current_user.role != "admin":
        return redirect(url_for("index"))

    endorsement = Endorsement.query.get_or_404(req_id)
    for file_attr in ["endorsement_file", "hte_endorsement_file"]:
        file_name = getattr(endorsement, file_attr)
        if file_name:
            file_path = os.path.join(UPLOAD_FOLDER, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)
    db.session.delete(endorsement)
    db.session.commit()
    flash("Endorsement deleted successfully!", "success")
    return redirect(url_for("admin_dashboard"))

# ==========================
# STUDENT DELETE ENDORSEMENT
# ==========================
@app.route("/student/endorsement/delete/<int:req_id>", methods=["POST"])
@login_required
def student_delete_endorsement(req_id):
    if current_user.role != "student":
        return redirect(url_for("index"))

    endorsement = Endorsement.query.get_or_404(req_id)
    if endorsement.student_id != current_user.id:
        flash("Unauthorized action!", "danger")
        return redirect(url_for("student_dashboard"))

    # Delete associated files if exist
    for file_attr in ["endorsement_file", "hte_endorsement_file"]:
        file_name = getattr(endorsement, file_attr)
        if file_name:
            file_path = os.path.join(UPLOAD_FOLDER, file_name)
            if os.path.exists(file_path):
                os.remove(file_path)

    db.session.delete(endorsement)
    db.session.commit()
    flash("Endorsement deleted successfully!", "success")
    return redirect(url_for("student_dashboard"))

@app.route("/student/endorsement", methods=["POST"])
@login_required
def student_endorsement():
    if current_user.role != "student":
        return redirect(url_for("index"))

    # ✅ Ensure student has assigned HTE
    if not current_user.hte:
        flash("No HTE assigned by admin.", "warning")
        return redirect(url_for("student_dashboard"))

    title = request.form.get("title")
    description = request.form.get("description")

    if not title:
        flash("Title is required!", "danger")
        return redirect(url_for("student_dashboard"))

    endorsement = Endorsement(
        student_id=current_user.id,
        hte_id=current_user.hte.id,  # assigned HTE
        title=title,
        description=description,
        status="For HTE"  # sent directly to HTE
    )
    db.session.add(endorsement)
    db.session.commit()
    flash("Endorsement request submitted to your assigned HTE!", "success")
    return redirect(url_for("student_dashboard"))

    

# ==========================
# ADMIN SEND ENDORSEMENT TO STUDENT
# ==========================
@app.route("/admin/endorsement/<int:req_id>", methods=["POST"])
@login_required
def admin_endorsement(req_id):
    if current_user.role != "admin":
        return redirect(url_for("index"))
    endorsement = Endorsement.query.get_or_404(req_id)
    file = request.files.get("endorsement_file")
    admin_comment = request.form.get("admin_comment")
    if file:
        filename = f"admin_{req_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)
        endorsement.endorsement_file = filename
    if admin_comment:
        endorsement.admin_comment = admin_comment
    endorsement.status = "For Student"
    db.session.commit()
    flash("Endorsement sent to student!", "success")
    return redirect(url_for("admin_dashboard"))

@app.route("/student/send_to_hte/<int:req_id>", methods=["POST"])
@login_required
def send_to_hte(req_id):
    if getattr(current_user, "role", "").lower() != "student":
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    endorsement = Endorsement.query.get_or_404(req_id)

    # Only allow the student who owns the request
    if endorsement.student_id != current_user.id:
        return jsonify({"success": False, "error": "Unauthorized"}), 403

    # Only allow sending to the assigned HTE
    if not current_user.hte or endorsement.hte_id != current_user.hte.id:
        return jsonify({"success": False, "error": "Not authorized for this HTE"}), 403

    file = request.files.get("student_endorsement_file")
    if not file:
        return jsonify({"success": False, "error": "No file uploaded"}), 400

    try:
        filename = f"to_hte_{req_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        endorsement.endorsement_file = filename
        endorsement.status = "For HTE"
        db.session.commit()

        return jsonify({
            "success": True,
            "file_name": filename,
            "file_url": url_for("download_file", filename=filename),
            "status": endorsement.status
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================
# STUDENT SEND TO ADMIN (FIXED)
# ==========================
@app.route("/student/send_to_admin/<int:req_id>", methods=["POST"])
@login_required
def send_ht_file_to_admin(req_id):
    if current_user.role != "student":
        return redirect(url_for("index"))

    endorsement = Endorsement.query.get_or_404(req_id)
    # ✅ Only allow if HTE file exists and assigned correctly
    if endorsement.hte_id != current_user.hte.id or not endorsement.endorsement_file:
        flash("Cannot send: not assigned HTE or HTE file missing.", "danger")
        return redirect(url_for("student_dashboard"))

    file = request.files.get("hte_to_admin_file")
    if not file:
        flash("No file uploaded.", "danger")
        return redirect(url_for("student_dashboard"))

    try:
        filename = f"to_admin_{req_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        endorsement.hte_endorsement_file = filename
        endorsement.status = "Approved"
        db.session.commit()

        flash("File sent to Admin successfully!", "success")
    except Exception as e:
        flash(f"Error sending file: {str(e)}", "danger")

    return redirect(url_for("student_dashboard"))

# ==========================
# HTE UPLOAD ENDORSEMENT (AJAX)
# ==========================
@app.route("/hte/upload_endorsement/<int:req_id>", methods=["POST"])
@login_required
def hte_upload_endorsement(req_id):
    if current_user.role != "hte":
        return jsonify({"error": "Unauthorized"}), 403

    endorsement = Endorsement.query.get_or_404(req_id)

    # ✅ Only allow if HTE is assigned
    if endorsement.hte_id != current_user.id:
        return jsonify({"error": "Not authorized for this endorsement"}), 403

    file = request.files.get("hte_endorsement_file")
    if not file:
        return jsonify({"error": "No file uploaded"}), 400

    try:
        filename = f"hte_{req_id}_{secure_filename(file.filename)}"
        filepath = os.path.join(UPLOAD_FOLDER, filename)
        file.save(filepath)

        endorsement.hte_endorsement_file = filename
        endorsement.status = "Approved"
        db.session.commit()

        return jsonify({
            "success": True,
            "file_name": filename,
            "file_url": url_for("download_file", filename=filename),
            "status": endorsement.status
        })
    except Exception as e:
        return jsonify({"success": False, "error": str(e)}), 500

# ==========================
# HTE MARK ATTENDANCE (AJAX)
# ==========================
@app.route("/hte/mark_attendance/<int:record_id>", methods=["POST"])
@login_required
def hte_mark_attendance(record_id):
    # ✅ Only HTEs can mark attendance
    if current_user.role != "hte":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    try:
        record = Attendance.query.get_or_404(record_id)
        data = request.get_json()

        # ✅ Update attendance presence & approval
        record.present = bool(data.get("present", False))
        record.hte_approved = record.present  # automatically approve if marked present
        db.session.commit()

        # ✅ Handle DailyLog creation or visibility
        existing_log = DailyLog.query.filter_by(attendance_id=record.id).first()

        if record.present:
            # Create a new DailyLog if it doesn't exist
            if not existing_log:
                new_log = DailyLog(
                    student_id=record.student_id,
                    attendance_id=record.id,
                    date=record.timestamp.date(),
                    time=record.timestamp.time(),
                    description="Marked Present by HTE ✅",
                    visible_to_admin=True,  # make visible for admin
                )
                db.session.add(new_log)
            else:
                # Update existing log visibility
                existing_log.visible_to_admin = True
            db.session.commit()
        else:
            # If unchecked, hide it from admin instead of deleting
            if existing_log:
                existing_log.visible_to_admin = False
                db.session.commit()

        return jsonify({
            "success": True,
            "message": "Attendance marked and approved successfully!"
        })

    except Exception as e:
        db.session.rollback()
        print("❌ Error in hte_mark_attendance:", e)
        return jsonify({
            "success": False,
            "message": "Attendance update failed.",
            "error": str(e)
        }), 500

# ==========================
# STUDENT ATTENDANCE (AJAX)
# ==========================

@app.route("/attendance/<int:student_id>")
@login_required
def view_attendance_calendar(student_id):
    if current_user.role not in ["admin", "hte", "student"]:
        return redirect(url_for("index"))

    # Get student
    student = User.query.get_or_404(student_id)

    # Get all attendance records for the student
    attendance_records = Attendance.query.filter_by(student_id=student.id).all()

    # Group attendance by date
    attendance_by_day = defaultdict(list)
    for r in attendance_records:
        record_date = r.timestamp.date()  # Use timestamp to get the date
        attendance_by_day[record_date].append(r)

    # Current month/year
    today = date.today()
    year = today.year
    month = today.month

    # Calendar setup
    total_days = monthrange(year, month)[1]
    first_day = date(year, month, 1).weekday()  # Monday = 0

    days = []

    # Empty slots before first day (Sunday = 0)
    for _ in range((first_day + 1) % 7):
        days.append(None)

    # Fill calendar days
    for day_num in range(1, total_days + 1):
        current_date = date(year, month, day_num)
        records = attendance_by_day.get(current_date, [])
        days.append({
            "date": current_date,
            "records": records,  # list of Attendance objects for the day
        })

    return render_template(
        "attendance_calendar.html",
        student=student,
        year=year,
        month_name=date(year, month, 1).strftime("%B"),
        days=days,
    )

# ✅ STUDENT SUBMIT ATTENDANCE (via photo or scan)
@app.route("/student/attendance", methods=["POST"])
@login_required
def student_attendance():
    if current_user.role != "student":
        return jsonify(success=False, error="Unauthorized"), 403

    data = request.get_json()
    img_data = data.get("attendance_file")
    if not img_data:
        return jsonify(success=False, error="No image data received")

    # ⚡ Decode base64 image
    import base64, re
    img_str = re.sub('^data:image/.+;base64,', '', img_data)
    img_bytes = base64.b64decode(img_str)

    # ⚡ Save image file
    from datetime import datetime
    import os
    filename = f"attendance_{current_user.id}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.png"
    upload_folder = os.path.join("uploads")
    os.makedirs(upload_folder, exist_ok=True)
    file_path = os.path.join(upload_folder, filename)
    with open(file_path, "wb") as f:
        f.write(img_bytes)

    # ⚡ Create Attendance record
    from datetime import date, datetime as dt
    attendance_record = Attendance(
        student_id=current_user.id,
        file_name=filename,
        timestamp=dt.now()
    )
    db.session.add(attendance_record)

    # ⚡ Update DailyLog automatically
    today = date.today()
    now = dt.now().time()
    daily_log = DailyLog.query.filter_by(student_id=current_user.id, date=today).first()

    if not daily_log:
        daily_log = DailyLog(
            student_id=current_user.id,
            attendance_id=attendance_record.id,
            date=today,
            in_am=now,
            time=now,
            visible_to_admin=True,
            description="Auto-generated from attendance capture"
        )
        db.session.add(daily_log)
    else:
        # Fill the next available slot: out_am → in_pm → out_pm
        if not daily_log.out_am:
            daily_log.out_am = now
            daily_log.time = now
        elif not daily_log.in_pm:
            daily_log.in_pm = now
            daily_log.time = now
        elif not daily_log.out_pm:
            daily_log.out_pm = now
            daily_log.time = now
        else:
            db.session.commit()
            return jsonify(success=False, error="Already completed 4 attendance logs today!")

        # Update total_hours if both in_am and out_pm exist
        if daily_log.in_am and daily_log.out_pm:
            t1 = datetime.combine(today, daily_log.in_am)
            t2 = datetime.combine(today, daily_log.out_pm)
            daily_log.total_hours = round((t2 - t1).seconds / 3600, 2)

    db.session.commit()

    return jsonify(
        success=True,
        id=attendance_record.id,
        file_url=url_for('download_file', filename=filename),
        timestamp=attendance_record.timestamp.isoformat(),
        message="Attendance captured and saved!"
    )


@app.route('/student/attendance/save', methods=['POST'])
@login_required
def save_attendance():
    if current_user.role != "student":
        return redirect(url_for("index"))

    date_today = datetime.now().date()
    time_now = datetime.now()

    # ✅ Create Attendance record
    attendance = Attendance(
        student_id=current_user.id,
        date=date_today,
        timestamp=time_now,
        in_am=time_now,  # adjust depending on what you capture
        present=1
    )
    db.session.add(attendance)
    db.session.flush()  # get attendance.id before commit

    # ✅ Automatically create a linked Daily Log
    daily_log = DailyLog(
        student_id=current_user.id,
        attendance_id=attendance.id,
        date=date_today,
        in_am=attendance.in_am,
        out_am=attendance.out_am,
        in_pm=attendance.in_pm,
        out_pm=attendance.out_pm,
        total_hours=compute_total_hours(attendance) or 0,
        description="Auto-generated from attendance record",
        visible_to_admin=True  # make visible to admin
    )
    db.session.add(daily_log)
    db.session.commit()

    flash("Attendance and Daily Log saved successfully!", "success")
    return redirect(url_for("student_daily_log"))





# ==========================
# DELETE ATTENDANCE RECORD (AJAX)
# ==========================
@app.route("/student/delete_attendance/<int:record_id>", methods=["POST"])
@login_required
def delete_attendance(record_id):
    # Only allow students to perform deletion
    if current_user.role != "student":
        return jsonify({"error": "Unauthorized"}), 403

    record = Attendance.query.get_or_404(record_id)

    # Ensure the record belongs to the logged-in student
    if record.student_id != current_user.id:
        return jsonify({"error": "Unauthorized"}), 403

    # 🟡 Soft delete instead of removing the file or record
    record.is_deleted = True

    db.session.commit()
    return jsonify({"success": True, "deleted_id": record_id, "message": "Attendance soft deleted"})

@app.route('/student/restore_attendance/<int:id>', methods=['POST'])
@login_required
def restore_attendance_student(id):
    record = Attendance.query.get_or_404(id)
    if record.student_id != current_user.id:
        return jsonify(success=False, error="Unauthorized")
    record.is_deleted = False
    db.session.commit()
    return jsonify(success=True)
@app.route('/student/permanent_delete_attendance/<int:id>', methods=['POST'])
@login_required
def permanent_delete_attendance(id):
    record = Attendance.query.get_or_404(id)
    if record.student_id != current_user.id:
        return jsonify(success=False, error="Unauthorized")
    # Optionally remove the file
    file_path = os.path.join(app.config['UPLOAD_FOLDER'], record.file_name)
    if os.path.exists(file_path):
        os.remove(file_path)
    db.session.delete(record)
    db.session.commit()
    return jsonify(success=True)

@app.route('/admin_daily_log/<int:student_id>')
@login_required
def admin_daily_log(student_id):
    student = User.query.get_or_404(student_id)
    daily_logs = DailyLog.query.filter_by(student_id=student_id).order_by(DailyLog.date.desc()).all()

    # ✅ Build cleaned log data for template
    log_data = []
    total_done_hours = 0.0

    for log in daily_logs:
        hours_done = compute_total_hours(log)
        total_done_hours += hours_done
        log_data.append({
            'date': fmt_date(log.date),
            'in_am': fmt_time(log.in_am),
            'out_am': fmt_time(log.out_am),
            'in_pm': fmt_time(log.in_pm),
            'out_pm': fmt_time(log.out_pm),
            'hours_done': f"{hours_done:.2f}"
        })

    remaining_hours = max(600.0 - total_done_hours, 0.0)

    return render_template(
        'admin_daily_log.html',
        student=student,
        daily_logs=log_data,
        total_done_hours=total_done_hours,
        remaining_hours=remaining_hours
    )


# ==========================
# STUDENT DAILY LOG DASHBOARD
# ==========================
@app.route("/student/daily_log")
@login_required
def student_daily_log():
    if current_user.role != "student":
        return redirect(url_for("index"))

    # ✅ Get all attendance and daily logs
    attendances = (
        db.session.query(Attendance)
        .filter_by(student_id=current_user.id)
        .order_by(Attendance.date.desc())
        .all()
    )

    daily_logs = (
        db.session.query(DailyLog)
        .filter_by(student_id=current_user.id)
        .order_by(DailyLog.date.desc())
        .all()
    )

    # ✅ Compute total and remaining hours
    total_done_hours = sum(compute_total_hours(log) or 0 for log in daily_logs)
    remaining_hours = max(0, 600 - total_done_hours)

    display_logs = []

    # ✅ Use daily logs if available
    if daily_logs:
        for log in daily_logs:
            if (log.total_hours and log.total_hours > 0) or any([log.in_am, log.out_am, log.in_pm, log.out_pm]):
                display_logs.append({
                    "date": fmt_date(log.date),
                    "in_am": fmt_time(log.in_am),
                    "out_am": fmt_time(log.out_am),
                    "in_pm": fmt_time(log.in_pm),
                    "out_pm": fmt_time(log.out_pm),
                    "total_hours": f"{compute_total_hours(log):.2f}",
                    "description": log.description or "",
                })
    # ✅ If no DailyLog entries exist yet, use Attendance data
    elif attendances:
        for att in attendances:
            if (att.total_hours and att.total_hours > 0) or any([att.in_am, att.out_am, att.in_pm, att.out_pm]):
                display_logs.append({
                    "date": fmt_date(att.date),
                    "in_am": fmt_time(att.in_am),
                    "out_am": fmt_time(att.out_am),
                    "in_pm": fmt_time(att.in_pm),
                    "out_pm": fmt_time(att.out_pm),
                    "total_hours": f"{compute_total_hours(att):.2f}" if hasattr(att, 'total_hours') else "0",
                    "description": "Auto-display from attendance record",
                })

    return render_template(
        "dashboard_daily_log.html",
        student=current_user,
        daily_logs=display_logs,
        total_done_hours=total_done_hours,
        remaining_hours=remaining_hours,
        total_hours=total_done_hours,
    )



# ==========================
# STUDENT ADD DAILY LOG ENTRY
# ==========================
@app.route("/student/daily_log/add", methods=["POST"])
@login_required
def add_daily_log():
    if current_user.role != "student":
        return redirect(url_for("index"))

    date_str = request.form.get("date")
    in_am_str = request.form.get("in_am")
    out_am_str = request.form.get("out_am")
    in_pm_str = request.form.get("in_pm")
    out_pm_str = request.form.get("out_pm")
    task_description = request.form.get("task_description")
    total_hours_input = request.form.get("total_hours")

    if not date_str or not task_description:
        flash("Date and task description are required!", "danger")
        return redirect(url_for("student_daily_log"))

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()
        in_am = datetime.strptime(in_am_str, "%H:%M").time() if in_am_str else None
        out_am = datetime.strptime(out_am_str, "%H:%M").time() if out_am_str else None
        in_pm = datetime.strptime(in_pm_str, "%H:%M").time() if in_pm_str else None
        out_pm = datetime.strptime(out_pm_str, "%H:%M").time() if out_pm_str else None

        # Calculate total hours if not manually provided
        if total_hours_input:
            total_hours = float(total_hours_input)
        else:
            total_hours = 0
            if in_am and out_am:
                total_hours += (datetime.combine(date_obj, out_am) - datetime.combine(date_obj, in_am)).total_seconds() / 3600
            if in_pm and out_pm:
                total_hours += (datetime.combine(date_obj, out_pm) - datetime.combine(date_obj, in_pm)).total_seconds() / 3600

        # ✅ Create the log entry
        log = DailyLog(
            student_id=current_user.id,
            date=date_obj,
            in_am=in_am,
            out_am=out_am,
            in_pm=in_pm,
            out_pm=out_pm,
            description=task_description,  # ✅ use correct column name
            total_hours=total_hours,
            visible_to_admin=True  # ✅ make it visible to admin
        )

        db.session.add(log)
        db.session.commit()
        flash("✅ Daily log added successfully!", "success")

    except Exception as e:
        flash(f"❌ Failed to add daily log: {str(e)}", "danger")

    return redirect(url_for("student_daily_log"))



# ==========================
# STUDENT DELETE DAILY LOG
# ==========================
@app.route("/student/daily_log/delete/<int:log_id>", methods=["POST"])
@login_required
def delete_daily_log(log_id):
    if current_user.role != "student":
        return redirect(url_for("index"))
    log = DailyLog.query.get_or_404(log_id)
    if log.student_id != current_user.id:
        return redirect(url_for("student_daily_log"))

    db.session.delete(log)
    db.session.commit()
    flash("Daily log deleted successfully!", "success")
    return redirect(url_for("student_daily_log"))

# ==========================
# STUDENT DAR UPLOAD (FIXED)
# ==========================
from flask import request, jsonify, url_for
from flask_login import login_required, current_user
import os, json
from werkzeug.utils import secure_filename
from datetime import datetime

@app.route("/student/dar_upload", methods=["POST"], endpoint="student_dar_upload")
@login_required
def student_dar_upload():
    if current_user.role != "student":
        return jsonify({"success": False, "error": "Unauthorized access"}), 403

    date_str = request.form.get("dar_date")
    files = request.files.getlist("dar_files")

    if not date_str:
        return jsonify({"success": False, "error": "Date is required."}), 400

    try:
        date_obj = datetime.strptime(date_str, "%Y-%m-%d").date()

        upload_folder = os.path.join(app.root_path, "static", "dar_uploads")
        os.makedirs(upload_folder, exist_ok=True)

        saved_files = []
        for file in files:
            if file and file.filename:
                filename = secure_filename(file.filename)
                file.save(os.path.join(upload_folder, filename))
                saved_files.append(filename)

        if not saved_files:
            return jsonify({"success": False, "error": "No valid files uploaded."}), 400

        # Save record in DB
        new_dar = DailyAccomplishment(
            student_id=current_user.id,
            date=date_obj,
            accomplishment=json.dumps(saved_files)  # JSON list of filenames
        )
        db.session.add(new_dar)
        db.session.commit()

        return jsonify({
            "success": True,
            "id": new_dar.id,
            "date": new_dar.date.isoformat(),
            "files": saved_files,
            "file_base_url": url_for("static", filename="dar_uploads", _external=True)
        })

    except Exception as e:
        db.session.rollback()
        return jsonify({"success": False, "error": str(e)}), 500

@app.route('/view_accomplishment_reports/<int:student_id>')
@login_required
def view_accomplishment_reports(student_id):
    if current_user.role != "admin":
        return redirect(url_for("index"))

    student = User.query.get_or_404(student_id)
    dar_records = DailyAccomplishment.query.filter_by(student_id=student_id)\
        .order_by(DailyAccomplishment.date.desc()).all()

    return render_template(
        'view_accomplishment_reports.html',
        student=student,
        dar_records=dar_records  # ✅ must match the template
    )

@app.route('/download_accomplishment/<filename>')
@login_required
def download_accomplishment(filename):
    upload_folder = app.config['UPLOAD_FOLDER']
    return send_from_directory(upload_folder, filename, as_attachment=True)


# ==========================
# DOWNLOAD FILE ROUTE (FORCE DIRECT DOWNLOAD)
# ==========================
@app.route("/uploads/<filename>")
@login_required
def download_file(filename):
    return send_from_directory(UPLOAD_FOLDER, filename, as_attachment=True)

# ==========================
# STUDENT DOWNLOAD ENDORSEMENT
# ==========================
@app.route("/student/download_endorsement/<int:req_id>")
@login_required
def download_endorsement(req_id):
    endorsement = Endorsement.query.get_or_404(req_id)
    if endorsement.student_id != current_user.id:
        flash("Unauthorized access!", "danger")
        return redirect(url_for("student_dashboard"))
    if not endorsement.endorsement_file:
        flash("No endorsement file available for download.", "danger")
        return redirect(url_for("student_dashboard"))
    return send_from_directory(
        UPLOAD_FOLDER,
        endorsement.endorsement_file,
        as_attachment=True
    )

# ==========================
# HTE DOWNLOAD APPROVED ENDORSEMENT (NEW)
# ==========================
@app.route("/hte/download_approved/<int:req_id>")
@login_required
def hte_download_approved(req_id):
    if current_user.role != "hte":
        flash("Unauthorized access!", "danger")
        return redirect(url_for("index"))
    endorsement = Endorsement.query.get_or_404(req_id)
    if not endorsement.hte_endorsement_file:
        flash("No approved endorsement file available.", "danger")
        return redirect(url_for("hte_dashboard"))
    return send_from_directory(
        UPLOAD_FOLDER,
        endorsement.hte_endorsement_file,
        as_attachment=True
    )

# -------------------------------
# SocketIO events
# -------------------------------
@socketio.on('call_request')
def handle_call_request(data):
    student_id = data.get('studentId')
    student_name = data.get('studentName')
    # Notify admin about incoming call
    emit('incoming_call', {'studentId': student_id, 'studentName': student_name}, broadcast=True)

@socketio.on('call_accept')
def handle_call_accept(data):
    student_id = data.get('studentId')
    print(f"Admin accepted call from student {student_id}")
    # Here you can emit events to start WebRTC signaling

@socketio.on('call_end')
def handle_call_end():
    print("Call ended by admin")
    # Here you can notify student to close video


if __name__ == '__main__':
    socketio.run(app, host='0.0.0.0', port=5000, debug=True)
