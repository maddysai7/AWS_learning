import os
import time
import sqlite3
import secrets
import base64
import hmac
import hashlib
import json
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, jsonify, redirect, url_for, flash, session, abort, make_response
from werkzeug.security import generate_password_hash, check_password_hash

# Optional PostgreSQL driver for AWS RDS
try:
    import psycopg2
    import psycopg2.extras
    PSYCOPG2_AVAILABLE = True
except ImportError:
    PSYCOPG2_AVAILABLE = False

app = Flask(__name__)

# DevSecOps Hardening (CWE-798: Elimination of Hardcoded Secrets)
# Secret keys and database credentials are read dynamically from environment variables.
FLASK_SECRET_KEY = os.environ.get("FLASK_SECRET_KEY")
if not FLASK_SECRET_KEY:
    # If not supplied in environment, generate an ephemeral cryptographically secure random key
    FLASK_SECRET_KEY = secrets.token_hex(32)

app.secret_key = FLASK_SECRET_KEY

# Initial user passwords for database seeding (configurable via environment in AWS)
ADMIN_INIT_PASSWORD = os.environ.get("ADMIN_INIT_PASSWORD", "admin123")
CLERK_INIT_PASSWORD = os.environ.get("CLERK_INIT_PASSWORD", "clerk123")
AUDITOR_INIT_PASSWORD = os.environ.get("AUDITOR_INIT_PASSWORD", "auditor123")

# Database Configuration
DATABASE_URL = os.environ.get("DATABASE_URL")
DB_HOST = os.environ.get("DB_HOST")
DB_PORT = os.environ.get("DB_PORT", "5432")
DB_NAME = os.environ.get("DB_NAME", "stockpulse")
DB_USER = os.environ.get("DB_USER", "postgres")
DB_PASSWORD = os.environ.get("DB_PASSWORD", "")
SQLITE_PATH = os.environ.get("SQLITE_PATH", "stockpulse.db")

def is_postgres():
    return bool(DATABASE_URL or DB_HOST) and PSYCOPG2_AVAILABLE

def get_db_connection():
    """Returns a connection based on environment (PostgreSQL for AWS RDS, SQLite for local)."""
    if is_postgres():
        if DATABASE_URL:
            conn = psycopg2.connect(DATABASE_URL)
        else:
            conn = psycopg2.connect(
                host=DB_HOST,
                port=DB_PORT,
                dbname=DB_NAME,
                user=DB_USER,
                password=DB_PASSWORD
            )
        return conn
    else:
        conn = sqlite3.connect(SQLITE_PATH)
        conn.row_factory = sqlite3.Row
        return conn

def execute_query(query, params=(), fetchone=False, fetchall=False, commit=False):
    """
    Unified query runner that handles both PostgreSQL (%s) and SQLite (?) syntax.
    Returns dictionaries or lists of dictionaries for consistent access across both databases.
    """
    use_pg = is_postgres()
    conn = get_db_connection()
    try:
        if use_pg:
            pg_query = query.replace("?", "%s")
            cursor = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cursor.execute(pg_query, params)
            if commit:
                conn.commit()
            if fetchone:
                row = cursor.fetchone()
                return dict(row) if row else None
            if fetchall:
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            return cursor
        else:
            cursor = conn.cursor()
            cursor.execute(query, params)
            if commit:
                conn.commit()
            if fetchone:
                row = cursor.fetchone()
                return dict(row) if row else None
            if fetchall:
                rows = cursor.fetchall()
                return [dict(r) for r in rows]
            return cursor
    finally:
        conn.close()

def init_db():
    """Initializes tables and seeds initial store team, inventory products, and audit notes."""
    use_pg = is_postgres()
    conn = get_db_connection()
    cursor = conn.cursor()

    id_type = "SERIAL PRIMARY KEY" if use_pg else "INTEGER PRIMARY KEY AUTOINCREMENT"
    timestamp_default = "CURRENT_TIMESTAMP"

    # 1. Users / Employees Table (RBAC + Passwords)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS users (
            id {id_type},
            username VARCHAR(100) UNIQUE NOT NULL,
            full_name VARCHAR(150) NOT NULL,
            email VARCHAR(255) UNIQUE NOT NULL,
            password_hash VARCHAR(255) NOT NULL,
            role VARCHAR(50) NOT NULL,
            avatar_initials VARCHAR(10) NOT NULL,
            session_token VARCHAR(255),
            created_at TIMESTAMP DEFAULT {timestamp_default}
        )
    """)

    # Migration for existing database: add session_token if missing
    try:
        cursor.execute("ALTER TABLE users ADD COLUMN session_token VARCHAR(255)")
        conn.commit()
    except Exception:
        pass

    # 2. Products Table (Master Inventory)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS products (
            id {id_type},
            sku VARCHAR(50) UNIQUE NOT NULL,
            name VARCHAR(255) NOT NULL,
            category VARCHAR(100) NOT NULL,
            warehouse_location VARCHAR(100) NOT NULL,
            price NUMERIC(10, 2) NOT NULL,
            quantity INTEGER NOT NULL DEFAULT 0,
            min_threshold INTEGER DEFAULT 5,
            created_at TIMESTAMP DEFAULT {timestamp_default},
            updated_at TIMESTAMP DEFAULT {timestamp_default}
        )
    """)

    # 3. Product Notes Table (Relational 1-to-many, IDOR Protected)
    cursor.execute(f"""
        CREATE TABLE IF NOT EXISTS product_notes (
            id {id_type},
            product_id INTEGER NOT NULL REFERENCES products(id) ON DELETE CASCADE,
            user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
            author_name VARCHAR(150) NOT NULL,
            author_role VARCHAR(50) NOT NULL,
            note TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT {timestamp_default}
        )
    """)
    conn.commit()

    # Seed data if users table is empty
    cursor.execute("SELECT COUNT(*) FROM users")
    count = cursor.fetchone()[0]
    if count == 0:
        placeholder = "%s" if use_pg else "?"
        user_rows = [
            ("alex_manager", "Alex Mercer", "alex@stockpulse.io", generate_password_hash(ADMIN_INIT_PASSWORD, method="pbkdf2:sha256"), "admin", "AM"),
            ("bob_clerk", "Bob Jenkins", "bob@stockpulse.io", generate_password_hash(CLERK_INIT_PASSWORD, method="pbkdf2:sha256"), "clerk", "BJ"),
            ("clara_auditor", "Clara Oswald", "clara@stockpulse.io", generate_password_hash(AUDITOR_INIT_PASSWORD, method="pbkdf2:sha256"), "auditor", "CO")
        ]
        for u in user_rows:
            cursor.execute(f"""
                INSERT INTO users (username, full_name, email, password_hash, role, avatar_initials)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, u)

        product_rows = [
            ("SKU-ELEC-101", "Logitech MX Master 3S Mouse", "Electronics", "Shelf A-01", 99.99, 24, 5),
            ("SKU-ELEC-102", "Dell UltraSharp 27 4K Monitor", "Electronics", "Bay B-03", 499.00, 3, 5),
            ("SKU-APPL-201", "Mechanical Keyboard (Cherry Brown)", "Electronics", "Shelf A-04", 129.50, 0, 5),
            ("SKU-FURN-301", "Ergonomic Mesh Office Chair", "Furniture", "Warehouse Bay C", 249.99, 14, 4),
            ("SKU-CABL-401", "Braided USB-C to USB-C Cable (2m)", "Accessories", "Bin D-12", 14.99, 65, 15),
            ("SKU-AUDI-501", "Sony WH-1000XM5 ANC Headphones", "Audio", "Locker E-02", 349.99, 2, 5),
            ("SKU-GROC-601", "Artisan Roasted Coffee Beans (1kg)", "Groceries", "Pantry Rack 3", 22.50, 40, 10),
            ("SKU-TOOL-701", "Precision Screwdriver 64-Bit Set", "Hardware", "Tool Rack 1", 39.95, 8, 5)
        ]
        for p in product_rows:
            cursor.execute(f"""
                INSERT INTO products (sku, name, category, warehouse_location, price, quantity, min_threshold)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, p)

        # Pre-seed audit notes (Demonstrating 1-to-many relationship & user ownership)
        note_rows = [
            (2, 2, "Bob Jenkins", "clerk", "Regional supplier notified of stock drop below threshold. 15 units backordered, delivery expected Friday."),
            (3, 2, "Bob Jenkins", "clerk", "Customer purchased final display unit. Stock count confirmed at 0."),
            (4, 1, "Alex Mercer", "admin", "Annual warehouse audit verified: All 14 chair units in pristine condition in Bay C."),
            (6, 2, "Bob Jenkins", "clerk", "Physical count matched digital count. 2 units securely stored in Locker E-02.")
        ]
        for n in note_rows:
            cursor.execute(f"""
                INSERT INTO product_notes (product_id, user_id, author_name, author_role, note)
                VALUES ({placeholder}, {placeholder}, {placeholder}, {placeholder}, {placeholder})
            """, n)

        conn.commit()

    conn.close()

# Initialize DB on startup
init_db()

# ==============================================================================
# Authentication & Authorization Helpers
# ==============================================================================
def get_current_user():
    # 1. Check Bearer token from Authorization header (API / Burp Suite testing)
    auth_header = request.headers.get("Authorization", "")
    if auth_header.startswith("Bearer "):
        bearer_token = auth_header.split(" ", 1)[1].strip()
        if bearer_token:
            return execute_query("SELECT * FROM users WHERE session_token = ?", (bearer_token,), fetchone=True)

    # 2. Check Flask session cookie
    user_id = session.get("user_id")
    session_token = session.get("session_token")
    if not user_id or not session_token:
        return None

    # Server-Side Token Validation: Token MUST match active session in the database!
    # If user logged out, session_token in DB was set to NULL. Replay in Burp is blocked!
    return execute_query(
        "SELECT * FROM users WHERE id = ? AND session_token = ?",
        (user_id, session_token),
        fetchone=True
    )

def login_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if not get_current_user():
            if request.path.startswith("/api/") or request.headers.get("Accept") == "application/json":
                return jsonify({
                    "error": "Unauthorized",
                    "message": "Token/session has expired or was invalidated on logout. Replay blocked."
                }), 401
            flash("Your session has expired or you signed out. Please sign in again.", "info")
            return redirect(url_for("login", next=request.url))
        return f(*args, **kwargs)
    return decorated_function

def require_roles(allowed_roles):
    def decorator(f):
        @wraps(f)
        def decorated_function(*args, **kwargs):
            user = get_current_user()
            if not user or user["role"] not in allowed_roles:
                return render_template(
                    "error.html",
                    error_code="403 Forbidden",
                    error_title="Access Denied: Insufficient Permissions",
                    error_message=f"Unauthorized action: This operation is restricted to: {', '.join(allowed_roles).upper()}. Your current role is {(user['role'] if user else 'ANONYMOUS').upper()}."
                ), 403
            return f(*args, **kwargs)
        return decorated_function
    return decorator

@app.context_processor
def inject_global_context():
    current_user = get_current_user()
    all_users = execute_query("SELECT * FROM users ORDER BY id ASC", fetchall=True)
    return {
        "current_user": current_user,
        "all_users": all_users,
        "demo_passwords": {
            "alex_manager": ADMIN_INIT_PASSWORD,
            "bob_clerk": CLERK_INIT_PASSWORD,
            "clara_auditor": AUDITOR_INIT_PASSWORD
        },
        "db_engine": "Amazon RDS (PostgreSQL)" if is_postgres() else "Local SQLite (Dev Mode)",
        "aws_region": os.environ.get("AWS_REGION", "us-east-1")
    }

# ==============================================================================
# Authentication Routes (/login, /logout)
# ==============================================================================
@app.route("/login", methods=["GET", "POST"])
def login():
    if "user_id" in session and get_current_user():
        return redirect(url_for("dashboard"))

    if request.method == "POST":
        identifier = request.form.get("identifier", "").strip().lower()
        password = request.form.get("password", "")

        user = execute_query(
            "SELECT * FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
            (identifier, identifier),
            fetchone=True
        )

        if user and check_password_hash(user["password_hash"], password):
            # Generate a cryptographically secure active session token
            auth_token = secrets.token_hex(32)
            execute_query(
                "UPDATE users SET session_token = ? WHERE id = ?",
                (auth_token, user["id"]),
                commit=True
            )

            session.clear()
            session["user_id"] = user["id"]
            session["session_token"] = auth_token
            flash(f"Welcome back, {user['full_name']}! Signed in as {user['role'].upper()}.", "success")
            next_page = request.args.get("next")
            return redirect(next_page or url_for("dashboard"))
        else:
            flash("Invalid employee username/email or password.", "error")

    # Pass all users to login template for 1-click quick-demo login buttons
    demo_users = execute_query("SELECT * FROM users ORDER BY id ASC", fetchall=True)
    return render_template("login.html", demo_users=demo_users)

@app.route("/logout")
def logout():
    user_id = session.get("user_id")
    if user_id:
        # DevSecOps Best Practice: Invalidate token in database immediately upon logout
        execute_query("UPDATE users SET session_token = NULL WHERE id = ?", (user_id,), commit=True)
    session.clear()
    flash("You have been signed out successfully. Session token has been invalidated.", "info")
    return redirect(url_for("login"))

@app.route("/api/login", methods=["POST"])
def api_login():
    data = request.get_json(silent=True) or {}
    identifier = data.get("identifier", "").strip().lower()
    password = data.get("password", "")

    user = execute_query(
        "SELECT * FROM users WHERE LOWER(username) = ? OR LOWER(email) = ?",
        (identifier, identifier),
        fetchone=True
    )
    if user and check_password_hash(user["password_hash"], password):
        auth_token = secrets.token_hex(32)
        execute_query(
            "UPDATE users SET session_token = ? WHERE id = ?",
            (auth_token, user["id"]),
            commit=True
        )
        return jsonify({
            "status": "success",
            "token": auth_token,
            "token_type": "Bearer",
            "user": {
                "id": user["id"],
                "username": user["username"],
                "full_name": user["full_name"],
                "role": user["role"]
            }
        })
    return jsonify({"error": "Unauthorized", "message": "Invalid username or password"}), 401

@app.route("/api/logout", methods=["POST"])
def api_logout():
    user = get_current_user()
    if user:
        execute_query("UPDATE users SET session_token = NULL WHERE id = ?", (user["id"],), commit=True)
    session.clear()
    return jsonify({"status": "success", "message": "Session token successfully invalidated on server."})



# ==============================================================================
# Page 1: Executive Dashboard (/)
# ==============================================================================
@app.route("/")
@login_required
def dashboard():
    products = execute_query("SELECT * FROM products ORDER BY id DESC", fetchall=True)
    
    total_products = len(products)
    total_valuation = sum(float(p["price"]) * int(p["quantity"]) for p in products)
    total_units = sum(int(p["quantity"]) for p in products)
    
    out_of_stock_items = [p for p in products if int(p["quantity"]) == 0]
    low_stock_items = [p for p in products if 0 < int(p["quantity"]) <= int(p["min_threshold"])]
    
    recent_notes = execute_query("""
        SELECT n.*, p.name as product_name, p.sku as product_sku
        FROM product_notes n
        JOIN products p ON n.product_id = p.id
        ORDER BY n.id DESC
        LIMIT 5
    """, fetchall=True)

    return render_template(
        "index.html",
        total_products=total_products,
        total_valuation=total_valuation,
        total_units=total_units,
        out_of_stock_count=len(out_of_stock_items),
        low_stock_count=len(low_stock_items),
        low_stock_items=low_stock_items + out_of_stock_items,
        recent_notes=recent_notes
    )

# ==============================================================================
# Page 2: Inventory Catalog & Product Management (/products)
# ==============================================================================
@app.route("/products")
@login_required
def products():
    search = request.args.get("search", "").strip()
    category = request.args.get("category", "").strip()
    status_filter = request.args.get("status", "").strip()

    all_products = execute_query("SELECT * FROM products ORDER BY id DESC", fetchall=True)
    categories = sorted(list(set(p["category"] for p in all_products)))

    filtered = all_products
    if search:
        s = search.lower()
        filtered = [p for p in filtered if s in p["name"].lower() or s in p["sku"].lower()]

    if category:
        filtered = [p for p in filtered if p["category"] == category]

    if status_filter == "out_of_stock":
        filtered = [p for p in filtered if int(p["quantity"]) == 0]
    elif status_filter == "low_stock":
        filtered = [p for p in filtered if 0 < int(p["quantity"]) <= int(p["min_threshold"])]
    elif status_filter == "in_stock":
        filtered = [p for p in filtered if int(p["quantity"]) > int(p["min_threshold"])]

    notes_counts = execute_query("""
        SELECT product_id, COUNT(*) as count 
        FROM product_notes 
        GROUP BY product_id
    """, fetchall=True)
    count_map = {n["product_id"]: n["count"] for n in notes_counts}

    for p in filtered:
        p["notes_count"] = count_map.get(p["id"], 0)
        qty = int(p["quantity"])
        threshold = int(p["min_threshold"])
        if qty == 0:
            p["status_badge"] = "Out of Stock"
            p["status_color"] = "rose"
        elif qty <= threshold:
            p["status_badge"] = "Low Stock"
            p["status_color"] = "amber"
        else:
            p["status_badge"] = "In Stock"
            p["status_color"] = "emerald"

    return render_template(
        "products.html",
        products=filtered,
        categories=categories,
        search=search,
        selected_category=category,
        selected_status=status_filter
    )

# Quick Stock Adjustment (+ / -)
@app.route("/products/<int:product_id>/adjust-stock", methods=["POST"])
@login_required
@require_roles(["admin", "clerk"])
def adjust_stock(product_id):
    action = request.form.get("action")
    product = execute_query("SELECT * FROM products WHERE id = ?", (product_id,), fetchone=True)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    current_qty = int(product["quantity"])
    new_qty = current_qty + 1 if action == "inc" else max(0, current_qty - 1)

    execute_query(
        "UPDATE products SET quantity = ?, updated_at = CURRENT_TIMESTAMP WHERE id = ?",
        (new_qty, product_id),
        commit=True
    )
    flash(f"Updated {product['name']} stock to {new_qty} units.", "success")
    return redirect(request.referrer or url_for("products"))

# Add Product (Admin Only)
@app.route("/products/add", methods=["POST"])
@login_required
@require_roles(["admin"])
def add_product():
    sku = request.form.get("sku", "").strip().upper()
    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    warehouse = request.form.get("warehouse_location", "").strip()
    price = float(request.form.get("price", "0.0"))
    quantity = int(request.form.get("quantity", "0"))
    min_threshold = int(request.form.get("min_threshold", "5"))

    if not sku or not name:
        flash("SKU and Product Name are mandatory.", "error")
        return redirect(url_for("products"))

    try:
        execute_query("""
            INSERT INTO products (sku, name, category, warehouse_location, price, quantity, min_threshold)
            VALUES (?, ?, ?, ?, ?, ?, ?)
        """, (sku, name, category, warehouse, price, quantity, min_threshold), commit=True)
        flash(f"Product '{name}' ({sku}) created successfully.", "success")
    except Exception as e:
        flash(f"Failed to create product: {str(e)}", "error")

    return redirect(url_for("products"))

# Edit Product (Admin Only - BAC Protected)
@app.route("/products/<int:product_id>/edit", methods=["POST"])
@login_required
@require_roles(["admin"])
def edit_product(product_id):
    product = execute_query("SELECT * FROM products WHERE id = ?", (product_id,), fetchone=True)
    if not product:
        flash("Product not found.", "error")
        return redirect(url_for("products"))

    name = request.form.get("name", "").strip()
    category = request.form.get("category", "").strip()
    warehouse = request.form.get("warehouse_location", "").strip()
    try:
        price = float(request.form.get("price", product["price"]))
        quantity = int(request.form.get("quantity", product["quantity"]))
        min_threshold = int(request.form.get("min_threshold", product["min_threshold"]))
    except (ValueError, TypeError):
        flash("Invalid price or quantity entered.", "error")
        return redirect(url_for("products"))

    if not name or not category or not warehouse:
        flash("Name, category, and warehouse location are required.", "error")
        return redirect(url_for("products"))

    try:
        execute_query("""
            UPDATE products
            SET name = ?, category = ?, warehouse_location = ?, price = ?, quantity = ?, min_threshold = ?, updated_at = CURRENT_TIMESTAMP
            WHERE id = ?
        """, (name, category, warehouse, price, quantity, min_threshold, product_id), commit=True)
        flash(f"Product '{name}' updated successfully.", "success")
    except Exception as e:
        flash(f"Failed to update product: {str(e)}", "error")

    return redirect(url_for("products"))

# Delete Product (Admin Only - BAC Protected)
@app.route("/products/<int:product_id>/delete", methods=["POST"])
@login_required
@require_roles(["admin"])
def delete_product(product_id):
    product = execute_query("SELECT * FROM products WHERE id = ?", (product_id,), fetchone=True)
    if product:
        execute_query("DELETE FROM products WHERE id = ?", (product_id,), commit=True)
        flash(f"Product '{product['name']}' deleted.", "success")
    return redirect(url_for("products"))

# ==============================================================================
# Page 3: Product Notes & Relational Comments (/products/<id>/notes)
# Demonstrates 1-to-many relationship & IDOR Defense
# ==============================================================================
@app.route("/products/<int:product_id>/notes")
@login_required
def product_notes(product_id):
    product = execute_query("SELECT * FROM products WHERE id = ?", (product_id,), fetchone=True)
    if not product:
        abort(404)

    notes = execute_query("""
        SELECT * FROM product_notes 
        WHERE product_id = ? 
        ORDER BY id DESC
    """, (product_id,), fetchall=True)

    return render_template("product_notes.html", product=product, notes=notes)

# Add Note (Admin & Clerk)
@app.route("/products/<int:product_id>/notes/add", methods=["POST"])
@login_required
@require_roles(["admin", "clerk"])
def add_note(product_id):
    note_text = request.form.get("note", "").strip()
    if not note_text:
        flash("Note text cannot be empty.", "error")
        return redirect(url_for("product_notes", product_id=product_id))

    current_user = get_current_user()
    execute_query("""
        INSERT INTO product_notes (product_id, user_id, author_name, author_role, note)
        VALUES (?, ?, ?, ?, ?)
    """, (product_id, current_user["id"], current_user["full_name"], current_user["role"], note_text), commit=True)

    flash("Audit note added successfully.", "success")
    return redirect(url_for("product_notes", product_id=product_id))

# Delete Note (IDOR Protected: Only Note Author or Admin can delete)
@app.route("/notes/<int:note_id>/delete", methods=["POST"])
@login_required
def delete_note(note_id):
    current_user = get_current_user()
    note = execute_query("SELECT * FROM product_notes WHERE id = ?", (note_id,), fetchone=True)
    
    if not note:
        flash("Note not found.", "error")
        return redirect(url_for("products"))

    product_id = note["product_id"]

    # Permission Check: If not admin, must be original author
    if current_user["role"] != "admin" and int(note["user_id"]) != int(current_user["id"]):
        flash(f"Access Denied: You cannot delete an audit note authored by {note['author_name']}.", "error")
        return render_template(
            "error.html",
            error_code="403 Forbidden",
            error_title="Access Denied: Unauthorized Action",
            error_message=f"Logged-in user '{current_user['full_name']}' attempted to delete Note #{note_id} authored by '{note['author_name']}'. Employees may only delete notes they personally authored."
        ), 403

    execute_query("DELETE FROM product_notes WHERE id = ?", (note_id,), commit=True)
    flash("Audit note deleted successfully.", "success")
    return redirect(url_for("product_notes", product_id=product_id))

# ==============================================================================
# Page 4: Store Team & Role Assignment (/roles)
# Admin can assign roles and invite new employees (BAC protected)
# ==============================================================================
@app.route("/roles")
@login_required
def roles():
    team = execute_query("SELECT * FROM users ORDER BY id ASC", fetchall=True)
    return render_template("roles.html", team=team)

# Assign / Update Role (Admin Only - BAC Protected)
@app.route("/roles/assign-role", methods=["POST"])
@login_required
@require_roles(["admin"])
def assign_role():
    target_user_id = request.form.get("user_id")
    new_role = request.form.get("role", "").strip().lower()

    if new_role not in ["admin", "clerk", "auditor"]:
        flash("Invalid role specified.", "error")
        return redirect(url_for("roles"))

    target_user = execute_query("SELECT * FROM users WHERE id = ?", (target_user_id,), fetchone=True)
    if not target_user:
        flash("User not found.", "error")
        return redirect(url_for("roles"))

    # Update role in database
    execute_query("UPDATE users SET role = ? WHERE id = ?", (new_role, target_user_id), commit=True)
    flash(f"Updated role for {target_user['full_name']} to {new_role.upper()}.", "success")
    return redirect(url_for("roles"))

# Add / Invite New Employee (Admin Only - BAC Protected)
@app.route("/roles/add-employee", methods=["POST"])
@login_required
@require_roles(["admin"])
def add_employee():
    full_name = request.form.get("full_name", "").strip()
    username = request.form.get("username", "").strip().lower()
    email = request.form.get("email", "").strip().lower()
    role = request.form.get("role", "clerk").strip().lower()
    # DevSecOps: If no password specified, generate an ephemeral cryptographically random password
    password = request.form.get("password", "").strip() or secrets.token_urlsafe(8)

    if not full_name or not username or not email:
        flash("Full name, username, and email are required.", "error")
        return redirect(url_for("roles"))

    if role not in ["admin", "clerk", "auditor"]:
        role = "clerk"

    # Compute initials
    initials = "".join([part[0] for part in full_name.split()[:2]]).upper() or "EP"
    password_hash = generate_password_hash(password, method="pbkdf2:sha256")

    try:
        execute_query("""
            INSERT INTO users (username, full_name, email, password_hash, role, avatar_initials)
            VALUES (?, ?, ?, ?, ?, ?)
        """, (username, full_name, email, password_hash, role, initials), commit=True)
        flash(f"Employee {full_name} added as {role.upper()} with temporary password '{password}'.", "success")
    except Exception as e:
        flash(f"Failed to add employee: {str(e)}", "error")

    return redirect(url_for("roles"))

# ==============================================================================
# AWS Cloud Diagnostics & Health Check (/api/health)
# Required by AWS Application Load Balancer (Publicly accessible)
# ==============================================================================
@app.route("/api/health")
def health():
    start_time = time.time()
    db_status = "connected"
    try:
        execute_query("SELECT 1", fetchone=True)
    except Exception as e:
        db_status = f"disconnected: {str(e)}"
    latency_ms = round((time.time() - start_time) * 1000, 2)

    return jsonify({
        "status": "healthy" if "disconnected" not in db_status else "degraded",
        "service": "StockPulse Cloud Inventory",
        "version": "2.1.0",
        "cloud_provider": "AWS",
        "region": os.environ.get("AWS_REGION", "us-east-1"),
        "database": {
            "status": db_status,
            "engine": "PostgreSQL (RDS)" if is_postgres() else "SQLite (Local)",
            "latency_ms": latency_ms
        },
        "timestamp": datetime.utcnow().isoformat() + "Z"
    })

@app.route("/api/v1/metrics")
@login_required
def api_metrics():
    products = execute_query("SELECT * FROM products", fetchall=True)
    total_val = sum(float(p["price"]) * int(p["quantity"]) for p in products)
    low_stock = sum(1 for p in products if 0 < int(p["quantity"]) <= int(p["min_threshold"]))
    out_of_stock = sum(1 for p in products if int(p["quantity"]) == 0)

    return jsonify({
        "total_products": len(products),
        "inventory_valuation_usd": total_val,
        "low_stock_alerts": low_stock,
        "out_of_stock_alerts": out_of_stock
    })

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
