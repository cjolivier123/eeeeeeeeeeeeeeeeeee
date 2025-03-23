from flask import Flask, render_template, redirect, url_for, request, flash, session
from flask_sqlalchemy import SQLAlchemy
from gunicorn.app.base import BaseApplication
from abilities import apply_sqlite_migrations
import os
import re
import werkzeug.security as security

app = Flask(__name__, static_folder='static')
app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///banking.db'
app.config['SECRET_KEY'] = os.environ.get('SECRET_KEY', 'fallback_secret_key_for_development')
db = SQLAlchemy(app)

class User(db.Model):
    __tablename__ = 'users'  # Match the table name in migrations
    id = db.Column(db.Integer, primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=False)
    name = db.Column(db.String(120), nullable=False)  # Match NOT NULL in migration
    password = db.Column(db.String(255), nullable=False)
    phone_number = db.Column(db.String(20), nullable=False)
    country_code = db.Column(db.String(5), nullable=False)
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    account = db.relationship('BankAccount', uselist=False, back_populates='user')

class BankAccount(db.Model):
    __tablename__ = 'bank_accounts'
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey('users.id'), nullable=False)
    account_number = db.Column(db.String(20), unique=True, nullable=False)
    balance = db.Column(db.Float, default=0.0, nullable=False)
    user = db.relationship('User', back_populates='account')
    transactions = db.relationship('Transaction', back_populates='account', order_by='Transaction.created_at.desc()')

class Transaction(db.Model):
    __tablename__ = 'transactions'
    id = db.Column(db.Integer, primary_key=True)
    account_id = db.Column(db.Integer, db.ForeignKey('bank_accounts.id'), nullable=False)
    amount = db.Column(db.Float, nullable=False)
    transaction_type = db.Column(db.String(20), nullable=False)  # deposit, withdrawal, transfer
    description = db.Column(db.String(255))
    created_at = db.Column(db.DateTime, server_default=db.func.now())
    account = db.relationship('BankAccount', back_populates='transactions')

with app.app_context():
    apply_sqlite_migrations(db.engine, db.Model, "migrations")

@app.route("/")
def home_route():
    return render_template("home.html")

@app.route("/login", methods=['GET', 'POST'])
def login_route():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        user = User.query.filter_by(email=email).first()
        if user and security.check_password_hash(user.password, password):
            session['user_id'] = user.id
            return redirect(url_for('dashboard_route'))
        else:
            flash('Invalid email or password', 'error')
            return render_template("login.html")
    return render_template("login.html")

@app.route("/register", methods=['GET', 'POST'])
def register_route():
    if request.method == 'POST':
        email = request.form['email']
        password = request.form['password']
        phone_number = request.form['phone_number']
        country_code = request.form['country_code']

        # Basic validation
        if not re.match(r"[^@]+@[^@]+\.[^@]+", email):
            flash('Invalid email format', 'error')
            return render_template("register.html")

        if len(password) < 8:
            flash('Password must be at least 8 characters long', 'error')
            return render_template("register.html")

        existing_user = User.query.filter_by(email=email).first()
        if existing_user:
            flash('Email already registered', 'error')
            return render_template("register.html")

        hashed_password = security.generate_password_hash(password)
        new_user = User(
            email=email,
            name=email.split('@')[0],  # Use part before @ as default name
            password=hashed_password,
            phone_number=phone_number,
            country_code=country_code
        )
        db.session.add(new_user)
        db.session.commit()

        flash('Registration successful', 'success')
        return redirect(url_for('login_route'))

    return render_template("register.html")

@app.route("/dashboard")
def dashboard_route():
    if 'user_id' not in session:
        flash('Please login first', 'error')
        return redirect(url_for('login_route'))
        
    user = User.query.get(session['user_id'])
    if not user:
        session.clear()
        flash('User not found', 'error')
        return redirect(url_for('login_route'))
        
    if not user.account:
        # Create a default bank account if not exists
        account = BankAccount(
            user_id=user.id,
            account_number=f"1234{user.id:04d}5678",
            balance=1000.0  # Default starting balance
        )
        db.session.add(account)
        db.session.commit()

        # Create some sample transactions
        sample_transactions = [
            Transaction(account_id=account.id, amount=500.0, transaction_type='deposit', description='Initial deposit'),
            Transaction(account_id=account.id, amount=-50.0, transaction_type='withdrawal', description='ATM Withdrawal'),
            Transaction(account_id=account.id, amount=200.0, transaction_type='deposit', description='Salary'),
        ]
        db.session.add_all(sample_transactions)
        db.session.commit()
        
        # Refresh user object to get the new account
        user = User.query.get(session['user_id'])

    return render_template("dashboard.html",
        user=user,
        account=user.account,
        transactions=user.account.transactions[:5]  # Last 5 transactions
    )

@app.route("/logout")
def logout_route():
    # Clear any session data
    session.clear()
    flash('You have been logged out', 'success')
    return redirect(url_for('home_route'))

class StandaloneApplication(BaseApplication):
    def __init__(self, app, options=None):
        self.application = app
        self.options = options or {}
        super().__init__()

    def load_config(self):
        for key, value in self.options.items():
            if key in self.cfg.settings and value is not None:
                self.cfg.set(key.lower(), value)

    def load(self):
        return self.application

@app.route("/download")
def download_source():
    import os
    import zipfile
    from flask import send_file
    from io import BytesIO

    # Create an in-memory zip file
    memory_zip = BytesIO()
    with zipfile.ZipFile(memory_zip, 'w', zipfile.ZIP_DEFLATED) as zf:
        # Add main.py
        with open('main.py', 'r', encoding='utf-8') as f:
            zf.writestr('main.py', f.read())

        # Add requirements.txt
        with open('requirements.txt', 'r', encoding='utf-8') as f:
            zf.writestr('requirements.txt', f.read())

        # Add templates
        for template in os.listdir('templates'):
            if os.path.isfile(os.path.join('templates', template)):
                try:
                    with open(os.path.join('templates', template), 'r', encoding='utf-8') as f:
                        zf.writestr(f'templates/{template}', f.read())
                except UnicodeDecodeError:
                    with open(os.path.join('templates', template), 'rb') as f:
                        zf.writestr(f'templates/{template}', f.read())

        # Add migrations
        for migration in os.listdir('migrations'):
            with open(os.path.join('migrations', migration), 'r', encoding='utf-8') as f:
                zf.writestr(f'migrations/{migration}', f.read())

        # Add static files
        for root, dirs, files in os.walk('static'):
            for file in files:
                file_path = os.path.join(root, file)
                with open(file_path, 'rb') as f:
                    zf.writestr(
                        os.path.relpath(file_path, 'static'),
                        f.read()
                    )

    memory_zip.seek(0)

    # Send file for download
    return send_file(
        memory_zip,
        mimetype='application/zip',
        as_attachment=True,
        download_name='securebank_source.zip'
    )

if __name__ == "__main__":
    options = {
        "bind": "0.0.0.0:8080",
        "workers": 4,
        "loglevel": "info",
        "accesslog": "-",
        "preload_app": True
    }
    StandaloneApplication(app, options).run()