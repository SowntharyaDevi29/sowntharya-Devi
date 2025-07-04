import os
from flask import Flask, render_template, request, redirect, url_for, flash, session
from flask_mysqldb import MySQL
from werkzeug.security import generate_password_hash, check_password_hash
import mysql.connector

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'a5a4s8r6h1q2d3h8')  # Fallback for local dev

# MySQL configuration from environment variables
app.config['MYSQL_HOST'] = os.environ.get('MYSQL_HOST')
app.config['MYSQL_USER'] = os.environ.get('MYSQL_USER')
app.config['MYSQL_PASSWORD'] = os.environ.get('MYSQL_PASSWORD')
app.config['MYSQL_DB'] = os.environ.get('MYSQL_DB')
app.config['MYSQL_CURSORCLASS'] = 'DictCursor'  # Optional: for dict-based results

mysql = MySQL(app)

# Flag to track if database has been initialized
db_initialized = False

# Initialize database tables
def init_db():
    global db_initialized
    try:
        with app.app_context():
            # Debug: Print MySQL config to verify environment variables
            print(f"Attempting to connect to MySQL with: "
                  f"host={app.config['MYSQL_HOST']}, "
                  f"user={app.config['MYSQL_USER']}, "
                  f"db={app.config['MYSQL_DB']}")

            if mysql.connection is None:
                # Attempt a direct connection to diagnose the issue
                try:
                    conn = mysql.connector.connect(
                        host=app.config['MYSQL_HOST'],
                        user=app.config['MYSQL_USER'],
                        password=app.config['MYSQL_PASSWORD'],
                        database=app.config['MYSQL_DB']
                    )
                    conn.close()
                    print("Direct MySQL connection test successful")
                except mysql.connector.Error as e:
                    raise Exception(f"MySQL connection test failed: {str(e)}")

                raise Exception("MySQL connection is not established via Flask-MySQLdb")

            cur = mysql.connection.cursor()
            cur.execute('''
                CREATE TABLE IF NOT EXISTS users (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    username VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS students (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    register_number VARCHAR(20) UNIQUE NOT NULL,
                    department VARCHAR(50) NOT NULL,
                    year VARCHAR(10) NOT NULL
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS complaints (
                    complaint_id INT AUTO_INCREMENT PRIMARY KEY,
                    student_name VARCHAR(100) NOT NULL,
                    email VARCHAR(100) NOT NULL,
                    register_number VARCHAR(20) NOT NULL,
                    department VARCHAR(50) NOT NULL,
                    year VARCHAR(10) NOT NULL,
                    category VARCHAR(50) NOT NULL,
                    title VARCHAR(100) NOT NULL,
                    description TEXT NOT NULL,
                    status VARCHAR(20) DEFAULT 'Submitted',
                    submitted_on TIMESTAMP DEFAULT CURRENT_TIMESTAMP
                )
            ''')
            cur.execute('''
                CREATE TABLE IF NOT EXISTS admins (
                    id INT AUTO_INCREMENT PRIMARY KEY,
                    admin_id VARCHAR(50) UNIQUE NOT NULL,
                    password VARCHAR(255) NOT NULL
                )
            ''')
            mysql.connection.commit()
            cur.close()
            print("Database initialized successfully")
            db_initialized = True
    except Exception as e:
        print(f"Error initializing database: {str(e)}")
        raise

# Run database initialization before the first request
@app.before_request
def initialize_database():
    global db_initialized
    if not db_initialized:
        try:
            init_db()
        except Exception as e:
            flash(f"Database initialization failed: {str(e)}", "error")
            return render_template('error.html', error=str(e)), 500

@app.route('/')
def home():
    if 'username' in session:
        return render_template('home.html', username=session['username'])
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        try:
            cur = mysql.connection.cursor()
            cur.execute('SELECT password FROM users WHERE username = %s', (username,))
            user = cur.fetchone()
            cur.close()
            
            if user and check_password_hash(user['password'], password):
                session['username'] = username
                flash('Login successful!', 'success')
                return redirect(url_for('home'))
            else:
                flash('Invalid username or password', 'error')
                return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('login'))
    
    return render_template('login.html')

@app.route('/signup', methods=['GET', 'POST'])
def signup():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']
        
        hashed_password = generate_password_hash(password, method='pbkdf2:sha256')
        
        try:
            cur = mysql.connection.cursor()
            cur.execute('INSERT INTO users (username, password) VALUES (%s, %s)', 
                       (username, hashed_password))
            mysql.connection.commit()
            cur.close()
            flash('Signup successful! Please log in.', 'success')
            return redirect(url_for('login'))
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return redirect(url_for('signup'))
    
    return render_template('signup.html')

@app.route('/logout')
def logout():
    session.pop('username', None)
    flash('You have been logged out.', 'success')
    return redirect(url_for('login'))

@app.route('/submit', methods=['GET', 'POST'])
def submit_complaint():
    if 'username' not in session:
        flash('Please log in to submit a complaint.', 'error')
        return redirect(url_for('login'))
    
    if request.method == 'POST':
        name = request.form['name']
        email = request.form['email']
        register_number = request.form['register_number']
        department = request.form['department']
        year = request.form['year']
        category = request.form['category']
        title = request.form['title']
        description = request.form['description']

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM students WHERE register_number = %s AND department = %s AND year = %s",
                        (register_number, department, year))
            student = cur.fetchone()

            if not student:
                cur.close()
                return render_template('submit_complaint.html', error="You are not a verified student. Complaint not accepted.")

            cur.execute("""
                INSERT INTO complaints (student_name, email, register_number, department, year, category, title, description, status)
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, 'Submitted')
            """, (name, email, register_number, department, year, category, title, description))
            mysql.connection.commit()
            cur.close()

            return redirect(f'/my_complaint?email={email}')
        except Exception as e:
            flash(f'Error submitting complaint: {str(e)}', 'error')
            return render_template('submit_complaint.html')

    return render_template('submit_complaint.html')

@app.route('/my_complaint')
def my_complaints():
    email = request.args.get('email')
    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM complaints WHERE email = %s", (email,))
        complaints = cur.fetchall()
        cur.close()
        return render_template('my_complaint.html', complaints=complaints, email=email)
    except Exception as e:
        flash(f'Error fetching complaints: {str(e)}', 'error')
        return render_template('my_complaint.html', complaints=[], email=email)

@app.route('/search_complaint', methods=['GET', 'POST'])
def search_complaint():
    complaints = []
    email = None

    if request.method == 'POST':
        email = request.form.get('email')
        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT * FROM complaints WHERE email = %s", (email,))
            complaints = cur.fetchall()
            cur.close()
        except Exception as e:
            flash(f'Error searching complaints: {str(e)}', 'error')

    return render_template('search_complaint.html', complaints=complaints, email=email)

@app.route('/admin_login', methods=['GET', 'POST'])
def admin_login():
    if request.method == 'POST':
        admin_id = request.form['admin_id']
        password = request.form['password']

        try:
            cur = mysql.connection.cursor()
            cur.execute("SELECT password FROM admins WHERE admin_id = %s", (admin_id,))
            admin = cur.fetchone()
            cur.close()

            if admin and check_password_hash(admin['password'], password):
                session['admin_logged_in'] = True
                flash('Admin login successful!', 'success')
                return redirect(url_for('admin'))
            else:
                flash('Invalid admin ID or password', 'error')
                return render_template('admin_login.html', error="Invalid admin ID or password")
        except Exception as e:
            flash(f'Error: {str(e)}', 'error')
            return render_template('admin_login.html', error="Error during login")

    return render_template('admin_login.html')

@app.route('/admin', methods=['GET', 'POST'])
def admin():
    if not session.get('admin_logged_in'):
        flash('Please log in as admin.', 'error')
        return redirect(url_for('admin_login'))

    if request.method == 'POST':
        complaint_id = request.form.get('complaint_id')
        new_status = request.form.get('status')
        if complaint_id and new_status:
            allowed_statuses = ['Submitted', 'Pending', 'In Progress', 'Resolved']
            if new_status in allowed_statuses:
                try:
                    cur = mysql.connection.cursor()
                    cur.execute("SELECT 1 FROM complaints WHERE complaint_id = %s", (complaint_id,))
                    if not cur.fetchone():
                        flash("Complaint ID does not exist.", "error")
                    else:
                        cur.execute("UPDATE complaints SET status = %s WHERE complaint_id = %s", (new_status, complaint_id))
                        mysql.connection.commit()
                        flash("Status updated successfully.", "success")
                    cur.close()
                except Exception as e:
                    flash(f"Error updating status: {str(e)}", "error")
            else:
                flash("Invalid status selected.", "error")
        else:
            flash("Missing complaint ID or status.", "error")
        return redirect(url_for('admin'))

    try:
        cur = mysql.connection.cursor()
        cur.execute("SELECT * FROM complaints ORDER BY submitted_on DESC")
        complaints = cur.fetchall()
        cur.close()
        return render_template('admin_dash.html', complaints=complaints)
    except Exception as e:
        flash(f'Error fetching complaints: {str(e)}', 'error')
        return render_template('admin_dash.html', complaints=[])

@app.route('/admin_logout')
def admin_logout():
    session.pop('admin_logged_in', None)
    flash('Admin logged out successfully.', 'success')
    return redirect(url_for('admin_login'))

if __name__ == '__main__':
    app.run(host='0.0.0.0', port=int(os.environ.get('PORT', 5000)))
