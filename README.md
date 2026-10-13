# JSPM University Complaint System

A Flask and SQLite application for university students and faculty to submit and track complaints, with an administrator dashboard for managing complaints and reviewing status history.

## Features

- Separate student and faculty complaint categories and forms
- Admin dashboard with status updates and complaint history
- Complaint editing and deletion
- Login sessions and role-based access
- Email OTP support, configured through environment variables

## Setup

1. Install Python 3.10 or later and create/activate a virtual environment.
2. Install dependencies:

   ```powershell
   python -m pip install -r requirements.txt
   ```

3. Copy `.env.example` to `.env`. Set a unique `SECRET_KEY` and configure `ADMIN_EMAIL` and `ADMIN_PASSWORD` to bootstrap the initial admin account. Configure the mail variables to enable OTP email.
4. Start the app:

   ```powershell
   python app.py
   ```

The SQLite database is created locally as `database.db` and is intentionally excluded from version control. Do not commit `.env`, database files, or uploaded complaint attachments.

## Security notes

- No default admin or demo accounts are created. Set a strong, unique admin password in `.env` before first startup.
- New passwords are stored as hashes. Existing accounts with legacy plaintext passwords are upgraded to hashes when they successfully log in.
- Set a stable, randomly generated `SECRET_KEY` for deployments so sessions remain valid across restarts.
