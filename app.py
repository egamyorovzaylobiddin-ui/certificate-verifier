"""
QR Code Certificate Verification System for Volunteers
======================================================
Flask + SQLite + qrcode

Install:  pip install flask "qrcode[pil]"
Run:      python app.py
Open:     http://127.0.0.1:5000/

How it works
------------
1. Admin submits a volunteer's name, event and issue date on the home page.
2. The row is saved in SQLite; the database assigns an auto-incrementing ID
   (1, 2, 3, ...).
3. A QR code pointing to  <BASE_URL>/verify/<id>  is generated and saved as
   static/qrcodes/<id>.png.
4. Anyone scanning the QR code lands on /verify/<id>, which looks the ID up
   in the database and shows either a green "VALID" page or a red "FAKE" page.
"""

import os
import re
import sqlite3
from datetime import date

import qrcode
from flask import Flask, g, redirect, render_template_string, request, url_for, flash

# --------------------------------------------------------------------------
# Configuration
# --------------------------------------------------------------------------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
DB_PATH = os.path.join(BASE_DIR, "certificates.db")
QR_DIR = os.path.join(BASE_DIR, "static", "qrcodes")

# The public address that gets encoded in the QR codes. When you deploy the
# app, set this to your real domain, e.g. BASE_URL=https://certs.example.org
# Scanning from a phone will NOT work with 127.0.0.1 (that is the phone itself);
# use your computer's LAN IP (e.g. http://192.168.1.20:5000) for phone tests.
BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:5000").rstrip("/")

app = Flask(__name__)
# Needed for flash() messages. Change this in production.
app.secret_key = os.environ.get("SECRET_KEY", "dev-secret-change-me")

os.makedirs(QR_DIR, exist_ok=True)


# --------------------------------------------------------------------------
# Database helpers
# --------------------------------------------------------------------------
def get_db():
    """Open one SQLite connection per request and reuse it."""
    if "db" not in g:
        g.db = sqlite3.connect(DB_PATH)
        g.db.row_factory = sqlite3.Row  # access columns by name
    return g.db


@app.teardown_appcontext
def close_db(exc):
    """Close the connection automatically when the request ends."""
    db = g.pop("db", None)
    if db is not None:
        db.close()


def init_db():
    """Create the certificates table if it doesn't exist.

    INTEGER PRIMARY KEY AUTOINCREMENT guarantees IDs start at 1 and always
    increase (1, 2, 3, ...) and are never reused, even after deletions.
    """
    with sqlite3.connect(DB_PATH) as conn:
        conn.execute(
            """
            CREATE TABLE IF NOT EXISTS certificates (
                id         INTEGER PRIMARY KEY AUTOINCREMENT,
                full_name  TEXT NOT NULL,
                event_name TEXT NOT NULL,
                issue_date TEXT NOT NULL
            )
            """
        )


# --------------------------------------------------------------------------
# QR code generation
# --------------------------------------------------------------------------
def generate_qr(cert_id):
    """Create static/qrcodes/<id>.png encoding the verification URL."""
    verify_url = f"{BASE_URL}/verify/{cert_id}"
    img = qrcode.make(verify_url)  # returns a PIL image
    img.save(os.path.join(QR_DIR, f"{cert_id}.png"))
    return verify_url


# --------------------------------------------------------------------------
# HTML templates (kept inline so everything lives in a single file)
# --------------------------------------------------------------------------
ADMIN_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Certificate Admin</title>
  <style>
    * { box-sizing: border-box; }
    body { font-family: system-ui, sans-serif; background:#f4f6f8; margin:0; color:#222; }
    .wrap { max-width: 960px; margin: 0 auto; padding: 24px 16px; }
    h1 { margin-top: 0; }
    .card { background:#fff; border-radius:10px; padding:20px; margin-bottom:24px;
            box-shadow:0 1px 4px rgba(0,0,0,.1); }
    label { display:block; font-weight:600; margin:12px 0 4px; }
    input { width:100%; padding:10px; border:1px solid #bbb; border-radius:6px; font-size:1rem; }
    button { margin-top:16px; padding:10px 22px; background:#1a73e8; color:#fff;
             border:0; border-radius:6px; font-size:1rem; cursor:pointer; }
    button:hover { background:#155ec0; }
    .flash-ok  { background:#e6f4ea; color:#137333; padding:10px; border-radius:6px; margin-bottom:12px; }
    .flash-err { background:#fce8e6; color:#c5221f; padding:10px; border-radius:6px; margin-bottom:12px; }
    .table-scroll { overflow-x:auto; }           /* responsive: scroll on small screens */
    table { width:100%; border-collapse:collapse; min-width:560px; }
    th, td { text-align:left; padding:10px; border-bottom:1px solid #e3e3e3; vertical-align:middle; }
    th { background:#fafafa; }
    img.qr { width:90px; height:90px; }
  </style>
</head>
<body>
<div class="wrap">
  <h1>🎓 Volunteer Certificate Admin</h1>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for cat, msg in messages %}
      <div class="{{ 'flash-ok' if cat == 'ok' else 'flash-err' }}">{{ msg }}</div>
    {% endfor %}
  {% endwith %}

  <div class="card">
    <h2>Issue a new certificate</h2>
    <form method="post" action="{{ url_for('home') }}">
      <label for="full_name">Full Name</label>
      <input id="full_name" name="full_name" maxlength="120" required>

      <label for="event_name">Event Name</label>
      <input id="event_name" name="event_name" maxlength="160" required>

      <label for="issue_date">Issue Date</label>
      <input id="issue_date" name="issue_date" type="date" value="{{ today }}" required>

      <button type="submit">Create certificate &amp; QR code</button>
    </form>
  </div>

  <div class="card">
    <h2>All certificates ({{ certs|length }})</h2>
    <div class="table-scroll">
      <table>
        <thead>
          <tr><th>ID</th><th>Name</th><th>Event</th><th>Date</th><th>QR code</th></tr>
        </thead>
        <tbody>
        {% for c in certs %}
          <tr>
            <td>{{ c['id'] }}</td>
            <td>{{ c['full_name'] }}</td>
            <td>{{ c['event_name'] }}</td>
            <td>{{ c['issue_date'] }}</td>
            <td>
              <a href="{{ url_for('verify', cert_id=c['id']) }}" target="_blank">
                <img class="qr" src="{{ url_for('static', filename='qrcodes/' ~ c['id'] ~ '.png') }}"
                     alt="QR code for certificate {{ c['id'] }}">
              </a>
            </td>
          </tr>
        {% else %}
          <tr><td colspan="5">No certificates yet. Create the first one above.</td></tr>
        {% endfor %}
        </tbody>
      </table>
    </div>
  </div>
</div>
</body>
</html>
"""

VALID_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Valid Certificate</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#e6f4ea; margin:0; min-height:100vh;
           display:flex; align-items:center; justify-content:center; padding:16px; }
    .box { background:#fff; border-top:10px solid #1e8e3e; border-radius:12px; max-width:520px;
           width:100%; padding:32px; text-align:center; box-shadow:0 4px 16px rgba(0,0,0,.15); }
    h1 { color:#137333; margin-top:0; }
    dl { text-align:left; margin:24px 0 0; }
    dt { color:#666; font-size:.85rem; text-transform:uppercase; letter-spacing:.05em; margin-top:14px; }
    dd { margin:2px 0 0; font-size:1.2rem; font-weight:600; }
    .note { margin-top:24px; color:#666; font-size:.9rem; }
  </style>
</head>
<body>
  <div class="box">
    <h1>✅ VALID CERTIFICATE</h1>
    <p>This certificate was issued by our organization and exists in the official database.</p>
    <dl>
      <dt>Certificate No.</dt><dd>{{ cert['id'] }}</dd>
      <dt>Volunteer</dt><dd>{{ cert['full_name'] }}</dd>
      <dt>Event</dt><dd>{{ cert['event_name'] }}</dd>
      <dt>Issue Date</dt><dd>{{ cert['issue_date'] }}</dd>
    </dl>
    <p class="note">Check that the name above matches the name on the certificate you hold.</p>
  </div>
</body>
</html>
"""

FAKE_TEMPLATE = """
<!doctype html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>Fake Certificate</title>
  <style>
    body { font-family: system-ui, sans-serif; background:#fce8e6; margin:0; min-height:100vh;
           display:flex; align-items:center; justify-content:center; padding:16px; }
    .box { background:#fff; border-top:10px solid #d93025; border-radius:12px; max-width:520px;
           width:100%; padding:32px; text-align:center; box-shadow:0 4px 16px rgba(0,0,0,.15); }
    h1 { color:#c5221f; margin-top:0; }
  </style>
</head>
<body>
  <div class="box">
    <h1>❌ WARNING: FAKE CERTIFICATE</h1>
    <p>Certificate ID <strong>{{ cert_id }}</strong> does <strong>not exist</strong> in the
       official database.</p>
    <p>Do not trust this certificate. Please contact the issuing organization.</p>
  </div>
</body>
</html>
"""


# --------------------------------------------------------------------------
# Routes
# --------------------------------------------------------------------------
@app.route("/", methods=["GET", "POST"])
def home():
    """Admin panel: create certificates (POST) and list them (GET)."""
    db = get_db()

    if request.method == "POST":
        full_name = request.form.get("full_name", "").strip()
        event_name = request.form.get("event_name", "").strip()
        issue_date = request.form.get("issue_date", "").strip()

        # Basic server-side validation (never trust the browser alone)
        if not full_name or not event_name or not issue_date:
            flash("All fields are required.", "err")
        elif not re.fullmatch(r"\d{4}-\d{2}-\d{2}", issue_date):
            flash("Invalid date format.", "err")
        else:
            # Parameterized query -> protects against SQL injection
            cur = db.execute(
                "INSERT INTO certificates (full_name, event_name, issue_date) VALUES (?, ?, ?)",
                (full_name, event_name, issue_date),
            )
            db.commit()
            cert_id = cur.lastrowid          # the auto-generated numeric ID (1, 2, 3, ...)
            url = generate_qr(cert_id)       # creates static/qrcodes/<id>.png
            flash(f"Certificate #{cert_id} created. QR points to {url}", "ok")

        # Post/Redirect/Get: avoids duplicate submissions on page refresh
        return redirect(url_for("home"))

    certs = db.execute("SELECT * FROM certificates ORDER BY id DESC").fetchall()
    return render_template_string(ADMIN_TEMPLATE, certs=certs, today=date.today().isoformat())


@app.route("/verify/<int:cert_id>")
def verify(cert_id):
    """Public page opened when a QR code is scanned."""
    cert = get_db().execute(
        "SELECT * FROM certificates WHERE id = ?", (cert_id,)
    ).fetchone()

    if cert:
        return render_template_string(VALID_TEMPLATE, cert=cert)
    # 404 status so automated checkers also see it as "not found"
    return render_template_string(FAKE_TEMPLATE, cert_id=cert_id), 404


# --------------------------------------------------------------------------
# Entry point
# --------------------------------------------------------------------------
if __name__ == "__main__":
    init_db()
    # debug=True is for local development only; turn it off in production.
    app.run(host="127.0.0.1", port=5000, debug=True)
