from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mail import Mail, Message
from werkzeug.utils import secure_filename
import os
import random
import string
import matplotlib
matplotlib.use('Agg')
from database import (
    ROLE_ADMIN,
    ROLE_FACULTY,
    ROLE_STUDENT,
    add_status_update,
    delete_complaint,
    get_categories,
    get_category_counts,
    get_complaint_by_id,
    get_complaint_by_ticket,
    get_complaints,
    get_status_counts,
    get_status_history,
    init_app as init_database,
    insert_complaint,
    mark_complaint_resolved,
    update_complaint,
    verify_user,
)
from dotenv import load_dotenv

load_dotenv()

STUDENT_CATEGORIES = [
    'Academic', 'Hostel', 'Library', 'Campus Security', 'Waste Management',
    'Washroom', 'Transport', 'Sports', 'Fee Issue', 'Attendance', 'Lab Equipment'
]

FACULTY_CATEGORIES = [
    'Curriculum', 'Classroom Facilities', 'Lab Equipment', 'Administration',
    'Student Discipline', 'IT Support', 'Research Support', 'Library Resources',
    'Academic Integrity', 'Safety & Security', 'Infrastructure'
]


def get_categories_for_role(role):
    if role == ROLE_FACULTY:
        return FACULTY_CATEGORIES
    return STUDENT_CATEGORIES


app = Flask(__name__)
app.jinja_env.globals['current_year'] = datetime.now().year
secret_key = os.environ.get('SECRET_KEY', '').strip()
if not secret_key:
    raise RuntimeError('Set SECRET_KEY in your environment before starting the app.')
app.config['SECRET_KEY'] = secret_key
app.config['MAIL_SERVER'] = os.environ.get('MAIL_SERVER', 'smtp.gmail.com')
app.config['MAIL_PORT'] = int(os.environ.get('MAIL_PORT', 587))
app.config['MAIL_USE_TLS'] = True
app.config['MAIL_USE_SSL'] = False
app.config['MAIL_USERNAME'] = os.environ.get('MAIL_USERNAME')
app.config['MAIL_PASSWORD'] = os.environ.get('MAIL_PASSWORD')
app.config['MAIL_DEFAULT_SENDER'] = (
    os.environ.get('MAIL_DEFAULT_SENDER') or app.config['MAIL_USERNAME']
)

mail = Mail(app)
init_database(app)


@app.route('/')
def home():
    return render_template('login.html')


def send_otp_email(email, otp):
    try:
        msg = Message(
            'Your OTP Code',
            sender=app.config['MAIL_DEFAULT_SENDER'],
            recipients=[email],
        )
        msg.body = f'Your OTP code is {otp}'
        mail.send(msg)
        return True
    except Exception as exc:
        print('OTP ERROR:', exc)
        return False


@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'GET':
        return render_template('login.html')

    email = request.form.get('email', '').strip().lower()
    password = request.form.get('password', '').strip()
    role = request.form.get('role', ROLE_STUDENT)

    if not email or not password:
        flash('Email and password are required.')
        return redirect(url_for('home'))

    if role not in [ROLE_STUDENT, ROLE_FACULTY, ROLE_ADMIN]:
        flash('Please choose a valid role.')
        return redirect(url_for('home'))

    user = verify_user(email, password, role)
    if user is None:
        flash('Invalid email, password, or role.')
        return redirect(url_for('home'))

    session.clear()
    session['email'] = user.email
    session['role'] = user.role
    session['name'] = user.name

    if user.role == ROLE_ADMIN:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('user_dashboard'))


@app.route('/logout')
def logout():
    session.clear()
    flash('You have been logged out.')
    return redirect(url_for('home'))


@app.route('/verify_otp', methods=['POST'])
def verify_otp():
    entered_otp = request.form['otp']
    if entered_otp == session.get('otp'):
        return redirect(url_for('user_dashboard'))
    flash('Invalid OTP. Please try again.')
    return redirect(url_for('home'))


@app.route('/dashboard')
def user_dashboard():
    if 'email' not in session:
        return redirect(url_for('home'))
    if session.get('role') == ROLE_ADMIN:
        return redirect(url_for('admin_dashboard'))
    return render_template('dashboard.html', role=session.get('role', ROLE_STUDENT), user_name=session.get('name', 'User'))


@app.route('/complaint_form')
def complaint_form():
    role = session.get('role', ROLE_STUDENT)
    return render_template('complaint_form.html', categories=get_categories_for_role(role), role=role)


@app.route('/submit_complaint', methods=['POST'])
def submit_complaint():
    email = session.get('email')
    if not email:
        flash('Please log in first.')
        return redirect(url_for('home'))

    prn_or_faculty_id = request.form.get('prn_or_faculty_id', '').strip()
    category = request.form.get('category', '').strip()
    description = request.form.get('description', '').strip()

    if not prn_or_faculty_id or not category or not description:
        flash('Please complete all required complaint fields.')
        return redirect(url_for('complaint_form'))

    image_path = None
    if 'image' in request.files:
        image = request.files['image']
        if image and image.filename:
            filename = secure_filename(image.filename)
            upload_dir = os.path.join(app.static_folder, 'uploads')
            os.makedirs(upload_dir, exist_ok=True)
            image.save(os.path.join(upload_dir, filename))
            image_path = filename

    ticket_id = insert_complaint(
        email=email,
        prn_or_faculty_id=prn_or_faculty_id,
        category=category,
        description=description,
        image_path=image_path,
        submitted_by_role=session.get('role', ROLE_STUDENT),
    )
    flash(f'Complaint submitted! Ticket ID: {ticket_id}')
    return redirect(url_for('complaint_form'))


@app.route('/track', methods=['GET', 'POST'])
def track_complaint():
    complaint = None
    tracked_by_user = False

    if request.method == 'POST':
        ticket_id = request.form.get('complaint_id')
        if ticket_id:
            complaint = get_complaint_by_ticket(ticket_id.strip())
            if complaint and session.get('email') and complaint.email == session.get('email'):
                tracked_by_user = True
        if not complaint:
            flash('Complaint not found')

    if complaint:
        history = get_status_history(complaint.id)
        can_edit = session.get('email') == complaint.email or session.get('role') == ROLE_ADMIN
    else:
        history = []
        can_edit = False

    return render_template('track.html', complaint=complaint, history=history, can_edit=can_edit, tracked_by_user=tracked_by_user)


@app.route('/complaint/<int:complaint_id>/edit', methods=['GET', 'POST'])
def edit_complaint(complaint_id):
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        flash('Complaint not found.')
        return redirect(url_for('track_complaint'))

    if session.get('email') != complaint.email and session.get('role') != ROLE_ADMIN:
        flash('You can only edit your own complaint.')
        return redirect(url_for('user_dashboard'))

    if request.method == 'POST':
        category = request.form.get('category', '').strip()
        description = request.form.get('description', '').strip()
        prn_or_faculty_id = request.form.get('prn_or_faculty_id', '').strip()

        if not category or not description or not prn_or_faculty_id:
            flash('Please complete all fields before saving.')
            return redirect(url_for('edit_complaint', complaint_id=complaint_id))

        image_path = complaint.image_path
        if 'image' in request.files:
            image = request.files['image']
            if image and image.filename:
                filename = secure_filename(image.filename)
                upload_dir = os.path.join(app.static_folder, 'uploads')
                os.makedirs(upload_dir, exist_ok=True)
                image.save(os.path.join(upload_dir, filename))
                image_path = filename

        update_complaint(
            complaint_id=complaint_id,
            category=category,
            description=description,
            prn_or_faculty_id=prn_or_faculty_id,
            image_path=image_path,
        )
        flash('Complaint updated successfully.')
        return redirect(url_for('track_complaint'))

    categories = get_categories_for_role(session.get('role', ROLE_STUDENT))
    return render_template('edit_complaint.html', complaint=complaint, categories=categories)


@app.route('/complaint/<int:complaint_id>/delete', methods=['POST'])
def delete_complaint_route(complaint_id):
    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        flash('Complaint not found.')
        return redirect(url_for('track_complaint'))

    if session.get('email') != complaint.email and session.get('role') != ROLE_ADMIN:
        flash('You are not authorized to delete this complaint.')
        return redirect(url_for('user_dashboard'))

    delete_complaint(complaint_id)
    flash('Complaint deleted successfully.')
    if session.get('role') == ROLE_ADMIN:
        return redirect(url_for('admin_dashboard'))
    return redirect(url_for('user_dashboard'))


@app.route('/admin_dashboard')
def admin_dashboard():
    role = session.get('role')
    if role != ROLE_ADMIN:
        flash('Admin access required.')
        return redirect(url_for('home'))

    generate_graphs()
    selected_category = request.args.get('category', '').strip()
    selected_status = request.args.get('status', '').strip()

    complaints = get_complaints(
        category=selected_category or None,
        status=selected_status or None,
    )
    categories = get_categories()
    complaint_data = []
    for complaint in complaints:
        complaint_data.append({
            'complaint': complaint,
            'history': get_status_history(complaint.id)
        })

    return render_template(
        'admin_dashboard.html',
        complaints=complaint_data,
        categories=categories,
        selected_category=selected_category,
        selected_status=selected_status,
    )


@app.route('/complaint/<int:complaint_id>/status_update', methods=['POST'])
def complaint_status_update(complaint_id):
    if session.get('role') != ROLE_ADMIN:
        flash('Admin access required.')
        return redirect(url_for('home'))

    status = request.form.get('status', '').strip()
    note = request.form.get('note', '').strip()
    if not status:
        flash('Please select a complaint status.')
        return redirect(url_for('admin_dashboard'))

    add_status_update(complaint_id, status, note=note or 'Status updated by admin.', updated_by='admin')
    flash('Complaint status updated.')
    return redirect(url_for('admin_dashboard'))


@app.route('/mark_resolved/<int:complaint_id>', methods=['POST'])
def mark_resolved(complaint_id):
    if session.get('role') != ROLE_ADMIN:
        flash('Admin access required.')
        return redirect(url_for('home'))

    complaint = get_complaint_by_id(complaint_id)
    if complaint is None:
        flash('Complaint not found.')
    elif mark_complaint_resolved(complaint_id):
        flash('Complaint marked as resolved!')
    else:
        flash('Unable to update complaint status.')
    return redirect(url_for('admin_dashboard'))


def generate_graphs():
    import matplotlib.pyplot as plt

    graph_dir = os.path.join(app.static_folder, 'graphs')
    os.makedirs(graph_dir, exist_ok=True)

    category_counts = get_category_counts()
    categories = [item[0] for item in category_counts]
    counts = [item[1] for item in category_counts]

    plt.figure(figsize=(10, 6))
    if categories:
        colors = ['#4f46e5', '#0ea5e9', '#9333ea', '#f59e0b', '#14b8a6', '#6366f1', '#06b6d4', '#8b5cf6']
        bar_colors = [colors[i % len(colors)] for i in range(len(categories))]
        plt.bar(categories, counts, color=bar_colors)
        for i, v in enumerate(counts):
            plt.text(i, v + 0.2, str(v), ha='center', fontsize=10)
        plt.xticks(rotation=30, ha='right')
        plt.grid(axis='y', linestyle='--', alpha=0.3)
    else:
        plt.text(0.5, 0.5, 'No complaints yet', ha='center')
        plt.axis('off')

    plt.title('Category-wise Complaint Distribution')
    plt.xlabel('Categories')
    plt.ylabel('Number of Complaints')
    plt.tight_layout()
    plt.savefig(os.path.join(graph_dir, 'category_distribution.png'))
    plt.close()

    resolved_count, not_resolved_count = get_status_counts()
    plt.figure(figsize=(7, 7))
    if resolved_count + not_resolved_count > 0:
        plt.pie(
            [resolved_count, not_resolved_count],
            labels=['Resolved', 'Not Resolved'],
            autopct='%1.1f%%',
            colors=['#16a34a', '#dc2626'],
            startangle=140,
        )
        plt.axis('equal')
    else:
        plt.text(0.5, 0.5, 'No complaints yet', ha='center')
        plt.axis('off')

    plt.title('Resolved vs Not Resolved Complaints')
    plt.tight_layout()
    plt.savefig(os.path.join(graph_dir, 'resolved_vs_not_resolved.png'))
    plt.close()


@app.route('/send_otp', methods=['GET', 'POST'])
def trigger_otp():
    if request.method == 'POST':
        return login()
    return redirect(url_for('home'))


if __name__ == '__main__':
    app.run(debug=True)
