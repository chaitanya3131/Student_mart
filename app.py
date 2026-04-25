from flask import Flask, render_template, request, redirect, url_for, send_from_directory, session, flash, jsonify
import sqlite3
import os
import hashlib
import requests
import json
from functools import wraps

app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "studentmart_secret_2025")

# ─────────────────────────────────────────
# PATHS — work correctly on both local and Render
# On Render with persistent disk, files are at /opt/render/project/src/
# ─────────────────────────────────────────
BASE_DIR = os.path.dirname(os.path.abspath(__file__))
UPLOAD_FOLDER = os.path.join(BASE_DIR, "uploads")
DB_PATH = os.path.join(BASE_DIR, "database.db")
os.makedirs(UPLOAD_FOLDER, exist_ok=True)
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

# AI runs in DEMO mode — no API key needed
ANTHROPIC_API_KEY = None

# ─────────────────────────────────────────
# FAST2SMS CONFIG (Free SMS for India)
# Sign up at https://fast2sms.com
# Go to Dev API → copy your API Key
# ─────────────────────────────────────────
FAST2SMS_API_KEY = os.environ.get("FAST2SMS_API_KEY", "")   # Set this in Render environment variables

def send_sms(to_number, message):
    """Send SMS via Fast2SMS — works with any Indian number, no verification needed."""
    if not to_number or not to_number.strip():
        print("[SMS] SKIPPED — no phone number")
        return False, "no_phone"

    # Clean number — remove +91 prefix if present, keep 10 digits
    number = to_number.strip().replace(" ", "").replace("-", "")
    if number.startswith("+91"):
        number = number[3:]
    elif number.startswith("91") and len(number) == 12:
        number = number[2:]

    print(f"[SMS] Sending to: {number}")

    try:
        response = requests.get(
            "https://www.fast2sms.com/dev/bulkV2",
            params={
                "authorization": FAST2SMS_API_KEY,
                "message":       message,
                "language":      "english",
                "route":         "q",
                "numbers":       number,
            },
            headers={"cache-control": "no-cache"},
            timeout=10
        )
        result = response.json()
        print(f"[SMS] Fast2SMS response: {result}")

        if result.get("return") == True:
            print(f"[SMS] ✅ SUCCESS — sent to {number}")
            return True, "ok"
        else:
            err = str(result.get("message", result))
            print(f"[SMS] ❌ FAILED — {err}")
            return False, err
    except Exception as e:
        print(f"[SMS] ❌ EXCEPTION — {e}")
        return False, str(e)


# ─────────────────────────────────────────
# TEST SMS ROUTE
# Open: http://127.0.0.1:5000/test-sms/9876543210
# ─────────────────────────────────────────
@app.route("/test-sms/<phone>")
def test_sms(phone):
    success, reason = send_sms(phone, "StudentMart test! SMS is working correctly on your project.")
    if success:
        return f"""<div style="font-family:sans-serif;padding:40px;max-width:500px">
            <h2 style="color:green">✅ SMS Sent Successfully!</h2>
            <p>SMS was sent to <b>{phone}</b>. Check your phone!</p>
            <p style="color:gray;font-size:13px">Fast2SMS is working correctly.</p>
            <a href="/" style="color:blue">← Back to Home</a></div>"""
    else:
        fix = ""
        if "authorization" in reason.lower() or "invalid" in reason.lower() or "api" in reason.lower():
            fix = "<li>Your <b>Fast2SMS API Key is wrong</b>. Go to <a href='https://fast2sms.com' target='_blank'>fast2sms.com</a> → Login → Dev API → copy the key → paste in app.py line with FAST2SMS_API_KEY</li>"
        elif "balance" in reason.lower() or "credit" in reason.lower():
            fix = "<li>Your Fast2SMS account has <b>no credits</b>. Login at fast2sms.com and recharge (very cheap — Rs.1 per SMS)</li>"
        elif "no_phone" in reason:
            fix = "<li>No phone number was provided</li>"
        return f"""<div style="font-family:sans-serif;padding:40px;max-width:600px">
            <h2 style="color:red">❌ SMS Failed</h2>
            <p><b>Error:</b> {reason}</p>
            <h3>How to fix:</h3><ul>{fix}
            <li>Make sure you pasted the API key correctly in app.py</li>
            <li>Get your key from: <a href='https://fast2sms.com' target='_blank'>fast2sms.com → Dev API</a></li>
            </ul><a href="/" style="color:blue">← Back to Home</a></div>"""


# Flask-Mail (optional)
try:
    from flask_mail import Mail, Message as MailMessage
    app.config["MAIL_SERVER"]         = "smtp.gmail.com"
    app.config["MAIL_PORT"]           = 587
    app.config["MAIL_USE_TLS"]        = True
    app.config["MAIL_USERNAME"]       = os.environ.get("MAIL_USERNAME", "")
    app.config["MAIL_PASSWORD"]       = os.environ.get("MAIL_PASSWORD", "")
    app.config["MAIL_DEFAULT_SENDER"] = f"StudentMart <{os.environ.get('MAIL_USERNAME', '')}>"
    mail = Mail(app)
    MAIL_ENABLED = True
except ImportError:
    MAIL_ENABLED = False


# ─────────────────────────────────────────
# DATABASE SETUP
# ─────────────────────────────────────────
def init_db():
    conn = sqlite3.connect(DB_PATH)
    cur  = conn.cursor()

    cur.execute("""
        CREATE TABLE IF NOT EXISTS products (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            name         TEXT NOT NULL,
            price        INTEGER NOT NULL,
            category     TEXT,
            description  TEXT,
            image        TEXT,
            seller       TEXT,
            contact      TEXT,
            user_id      INTEGER,
            area         TEXT DEFAULT 'Dhule',
            views        INTEGER DEFAULT 0,
            status       TEXT DEFAULT 'Available',
            seller_phone TEXT DEFAULT '',
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS users (
            id       INTEGER PRIMARY KEY AUTOINCREMENT,
            name     TEXT NOT NULL,
            email    TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            area     TEXT DEFAULT 'Dhule',
            college  TEXT,
            phone    TEXT DEFAULT '',
            is_admin INTEGER DEFAULT 0
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS ratings (
            id         INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id INTEGER,
            user_id    INTEGER,
            stars      INTEGER,
            review     TEXT,
            created_at DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    cur.execute("""
        CREATE TABLE IF NOT EXISTS messages (
            id           INTEGER PRIMARY KEY AUTOINCREMENT,
            product_id   INTEGER,
            buyer_name   TEXT,
            buyer_email  TEXT,
            buyer_phone  TEXT,
            message      TEXT,
            created_at   DATETIME DEFAULT CURRENT_TIMESTAMP
        )
    """)

    # Safe migrations — add columns if they don't exist
    for sql in [
        "ALTER TABLE products ADD COLUMN status TEXT DEFAULT 'Available'",
        "ALTER TABLE products ADD COLUMN seller_phone TEXT DEFAULT ''",
        "ALTER TABLE users ADD COLUMN is_admin INTEGER DEFAULT 0",
        "ALTER TABLE users ADD COLUMN phone TEXT DEFAULT ''",
    ]:
        try:
            cur.execute(sql)
        except sqlite3.OperationalError:
            pass

    conn.commit()
    conn.close()

init_db()


# ─────────────────────────────────────────
# HELPERS
# ─────────────────────────────────────────
def hash_password(pw):
    return hashlib.sha256(pw.encode()).hexdigest()

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def current_user():
    if "user_id" in session:
        db  = get_db()
        cur = db.cursor()
        cur.execute("SELECT * FROM users WHERE id=?", (session["user_id"],))
        u = cur.fetchone()
        db.close()
        return u
    return None

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            flash("Please login to continue.")
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def admin_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        user = current_user()
        if not user or not user["is_admin"]:
            flash("Access denied. Admins only.")
            return redirect(url_for("home"))
        return f(*args, **kwargs)
    return decorated


# ─────────────────────────────────────────
# HOME
# ─────────────────────────────────────────
@app.route("/")
def home():
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM products WHERE status != 'Sold' ORDER BY id DESC LIMIT 8")
    recent = cur.fetchall()
    cur.execute("SELECT * FROM products WHERE status != 'Sold' ORDER BY views DESC LIMIT 4")
    popular = cur.fetchall()
    db.close()
    user = current_user()
    return render_template("index.html", recent=recent, popular=popular, user=user)


# ─────────────────────────────────────────
# PRODUCTS
# ─────────────────────────────────────────
@app.route("/products")
def products():
    search   = request.args.get("search", "")
    category = request.args.get("category", "")
    sort     = request.args.get("sort", "newest")
    db       = get_db()
    cur      = db.cursor()
    query    = "SELECT * FROM products WHERE status != 'Sold'"
    params   = []
    if search:
        query += " AND (name LIKE ? OR description LIKE ?)"
        params += ["%" + search + "%", "%" + search + "%"]
    if category:
        query += " AND category=?"
        params.append(category)
    order = {"price_low":"price ASC","price_high":"price DESC","popular":"views DESC"}.get(sort,"id DESC")
    query += f" ORDER BY {order}"
    cur.execute(query, params)
    data = cur.fetchall()
    db.close()
    user = current_user()
    return render_template("products.html", products=data, search=search,
                           category=category, sort=sort, user=user)


# ─────────────────────────────────────────
# PRODUCT DETAIL
# ─────────────────────────────────────────
@app.route("/product/<int:pid>")
def product_detail(pid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("UPDATE products SET views = views + 1 WHERE id=?", (pid,))
    db.commit()
    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    product = cur.fetchone()
    cur.execute("""
        SELECT r.*, u.name as uname FROM ratings r
        LEFT JOIN users u ON r.user_id = u.id
        WHERE r.product_id=? ORDER BY r.created_at DESC
    """, (pid,))
    reviews   = cur.fetchall()
    avg_stars = round(sum(r["stars"] for r in reviews) / len(reviews), 1) if reviews else 0
    cur.execute("SELECT * FROM products WHERE category=? AND id!=? AND status!='Sold' LIMIT 4",
                (product["category"] if product else "", pid))
    related = cur.fetchall()
    db.close()
    user = current_user()
    if not product:
        return redirect(url_for("products"))
    return render_template("product_detail.html", product=product, reviews=reviews,
                           avg_stars=avg_stars, related=related, user=user)


# ─────────────────────────────────────────
# CONTACT SELLER — SMS + email + DB save
# ─────────────────────────────────────────
@app.route("/contact/<int:pid>", methods=["POST"])
def contact_seller(pid):
    buyer_name    = request.form.get("buyer_name", "").strip()
    buyer_email   = request.form.get("buyer_email", "").strip()
    buyer_phone   = request.form.get("buyer_phone", "").strip()
    buyer_message = request.form.get("buyer_message", "").strip()

    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM products WHERE id=?", (pid,))
    product = cur.fetchone()

    if not product:
        db.close()
        flash("Product not found.")
        return redirect(url_for("products"))

    # Save message to DB always
    cur.execute("""
        INSERT INTO messages (product_id, buyer_name, buyer_email, buyer_phone, message)
        VALUES (?,?,?,?,?)
    """, (pid, buyer_name, buyer_email, buyer_phone, buyer_message))
    db.commit()
    db.close()

    # Get seller phone — check product first, fallback to buyer_phone field in form
    cols = product.keys()
    seller_phone = product["seller_phone"] if "seller_phone" in cols else ""
    seller_email = product["contact"] or ""

    print(f"[CONTACT] Product: {product['name']} | Seller phone: '{seller_phone}' | Seller email: '{seller_email}'")

    sms_sent   = False
    email_sent = False
    sms_error  = ""

    # ── SMS ──────────────────────────────────────────────────────
    if seller_phone and seller_phone.strip():
        sms_body = (
            f"[StudentMart] New buyer alert!\n"
            f"Product: {product['name']} (Rs.{product['price']})\n"
            f"Buyer: {buyer_name}\n"
            f"Email: {buyer_email}"
            + (f"\nPhone: {buyer_phone}" if buyer_phone else "") +
            f"\nMsg: {buyer_message[:100]}"
        )
        sms_sent, sms_error = send_sms(seller_phone, sms_body)
    else:
        print("[CONTACT] No seller_phone stored — SMS skipped. Seller must re-list product with phone number.")

    # ── Email ─────────────────────────────────────────────────────
    if MAIL_ENABLED and seller_email and "@" in seller_email:
        try:
            msg = MailMessage(
                subject=f"[StudentMart] {buyer_name} wants to buy '{product['name']}'",
                recipients=[seller_email]
            )
            msg.body = f"""Hello {product['seller']},

A student wants to buy your item on StudentMart!

Product : {product['name']}
Price   : Rs.{product['price']}

Buyer Name  : {buyer_name}
Buyer Email : {buyer_email}
Buyer Phone : {buyer_phone or 'Not provided'}

Message: "{buyer_message}"

Reply to: {buyer_email}
— StudentMart"""
            mail.send(msg)
            email_sent = True
        except Exception as e:
            print(f"[Mail Error] {e}")

    # ── Result flash ──────────────────────────────────────────────
    if sms_sent:
        flash(f"✅ SMS sent to seller {product['seller']}! They will contact you soon.")
    elif seller_phone and sms_error:
        flash(f"⚠️ Message saved but SMS failed ({sms_error}). Seller contact: {seller_email or seller_phone}")
    elif not seller_phone:
        flash(f"✅ Message saved! Seller has not added a phone number yet. Contact them at: {seller_email}")
    else:
        flash(f"✅ Message saved! Contact seller at: {seller_email}")

    return redirect(url_for("product_detail", pid=pid))


# ─────────────────────────────────────────
# RATE PRODUCT
# ─────────────────────────────────────────
@app.route("/rate/<int:pid>", methods=["POST"])
@login_required
def rate_product(pid):
    stars  = int(request.form.get("stars", 5))
    review = request.form.get("review", "")
    db  = get_db()
    cur = db.cursor()
    cur.execute("INSERT INTO ratings (product_id, user_id, stars, review) VALUES (?,?,?,?)",
                (pid, session["user_id"], stars, review))
    db.commit()
    db.close()
    return redirect(url_for("product_detail", pid=pid))


# ─────────────────────────────────────────
# SELL
# ─────────────────────────────────────────
@app.route("/sell", methods=["GET", "POST"])
@login_required
def sell():
    user = current_user()
    if request.method == "POST":
        name         = request.form.get("name", "")
        price        = request.form.get("price", 0)
        category     = request.form.get("category", "")
        description  = request.form.get("description", "")
        contact      = request.form.get("contact", "")
        seller_phone = request.form.get("seller_phone", "").strip()
        area         = request.form.get("area", user["area"] if user else "Dhule")
        image        = request.files.get("image")
        filename     = ""
        if image and image.filename != "":
            filename = image.filename
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        db  = get_db()
        cur = db.cursor()
        cur.execute(
            "INSERT INTO products (name,price,category,description,image,seller,contact,user_id,area,status,seller_phone) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            (name, price, category, description, filename, user["name"], contact,
             session["user_id"], area, "Available", seller_phone)
        )
        db.commit()
        db.close()
        flash("🎉 Item listed successfully!")
        return redirect(url_for("my_listings"))
    return render_template("sell.html", user=user)


# ─────────────────────────────────────────
# EDIT
# ─────────────────────────────────────────
@app.route("/edit/<int:pid>", methods=["GET", "POST"])
@login_required
def edit_product(pid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM products WHERE id=? AND user_id=?", (pid, session["user_id"]))
    product = cur.fetchone()
    if not product:
        db.close()
        return redirect(url_for("my_listings"))
    if request.method == "POST":
        name         = request.form.get("name")
        price        = request.form.get("price")
        category     = request.form.get("category")
        description  = request.form.get("description")
        contact      = request.form.get("contact")
        area         = request.form.get("area")
        status       = request.form.get("status", "Available")
        seller_phone = request.form.get("seller_phone", "").strip()
        image        = request.files.get("image")
        filename     = product["image"]
        if image and image.filename != "":
            filename = image.filename
            image.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))
        cur.execute("""
            UPDATE products SET name=?,price=?,category=?,description=?,contact=?,area=?,image=?,status=?,seller_phone=?
            WHERE id=? AND user_id=?
        """, (name, price, category, description, contact, area, filename, status, seller_phone, pid, session["user_id"]))
        db.commit()
        db.close()
        flash("✅ Listing updated!")
        return redirect(url_for("my_listings"))
    db.close()
    user = current_user()
    return render_template("edit_product.html", product=product, user=user)


# ─────────────────────────────────────────
# DELETE
# ─────────────────────────────────────────
@app.route("/delete/<int:pid>")
@login_required
def delete_product(pid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM products WHERE id=? AND user_id=?", (pid, session["user_id"]))
    db.commit()
    db.close()
    flash("Listing deleted.")
    return redirect(url_for("my_listings"))


# ─────────────────────────────────────────
# MY LISTINGS
# ─────────────────────────────────────────
@app.route("/my-listings")
@login_required
def my_listings():
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM products WHERE user_id=? ORDER BY id DESC", (session["user_id"],))
    listings = cur.fetchall()
    db.close()
    user = current_user()
    return render_template("my_listings.html", listings=listings, user=user)


# ─────────────────────────────────────────
# DASHBOARD
# ─────────────────────────────────────────
@app.route("/dashboard")
@login_required
def dashboard():
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products WHERE status='Sold'")
    total_sold = cur.fetchone()[0]
    cur.execute("SELECT category, COUNT(*) as cnt FROM products GROUP BY category ORDER BY cnt DESC LIMIT 1")
    row = cur.fetchone()
    popular_category = row["category"] if row else "N/A"
    cur.execute("SELECT category, COUNT(*) as cnt FROM products GROUP BY category ORDER BY cnt DESC")
    categories   = cur.fetchall()
    cat_labels   = [r["category"] or "Other" for r in categories]
    cat_counts   = [r["cnt"] for r in categories]
    cur.execute("SELECT status, COUNT(*) as cnt FROM products GROUP BY status")
    statuses      = cur.fetchall()
    status_labels = [r["status"] for r in statuses]
    status_counts = [r["cnt"] for r in statuses]
    cur.execute("SELECT * FROM products ORDER BY id DESC LIMIT 5")
    recent_products = cur.fetchall()
    cur.execute("""
        SELECT u.name, COUNT(p.id) as listings
        FROM users u LEFT JOIN products p ON u.id = p.user_id
        GROUP BY u.id ORDER BY listings DESC LIMIT 5
    """)
    top_sellers = cur.fetchall()
    db.close()
    user = current_user()
    return render_template("dashboard.html",
        user=user, total_users=total_users, total_products=total_products,
        total_sold=total_sold, popular_category=popular_category,
        cat_labels=json.dumps(cat_labels), cat_counts=json.dumps(cat_counts),
        status_labels=json.dumps(status_labels), status_counts=json.dumps(status_counts),
        recent_products=recent_products, top_sellers=top_sellers)


# ─────────────────────────────────────────
# ADMIN
# ─────────────────────────────────────────
@app.route("/admin")
@login_required
@admin_required
def admin_dashboard():
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM users ORDER BY id DESC")
    all_users = cur.fetchall()
    cur.execute("SELECT * FROM products ORDER BY id DESC")
    all_products = cur.fetchall()
    cur.execute("SELECT COUNT(*) FROM users")
    total_users = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products")
    total_products = cur.fetchone()[0]
    cur.execute("SELECT COUNT(*) FROM products WHERE status='Sold'")
    total_sold = cur.fetchone()[0]
    cur.execute("SELECT m.*, p.name as pname FROM messages m LEFT JOIN products p ON m.product_id=p.id ORDER BY m.created_at DESC LIMIT 20")
    all_messages = cur.fetchall()
    db.close()
    user = current_user()
    return render_template("admin_dashboard.html",
        user=user, all_users=all_users, all_products=all_products,
        total_users=total_users, total_products=total_products,
        total_sold=total_sold, all_messages=all_messages)

@app.route("/admin/delete-user/<int:uid>")
@login_required
@admin_required
def admin_delete_user(uid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM products WHERE user_id=?", (uid,))
    cur.execute("DELETE FROM users WHERE id=?", (uid,))
    db.commit()
    db.close()
    flash(f"User #{uid} deleted.")
    return redirect(url_for("admin_dashboard"))

@app.route("/admin/delete-product/<int:pid>")
@login_required
@admin_required
def admin_delete_product(pid):
    db  = get_db()
    cur = db.cursor()
    cur.execute("DELETE FROM products WHERE id=?", (pid,))
    db.commit()
    db.close()
    flash(f"Product #{pid} deleted.")
    return redirect(url_for("admin_dashboard"))


# ─────────────────────────────────────────
# TEST AI ROUTE
# Open: http://127.0.0.1:5000/test-ai
# ─────────────────────────────────────────
@app.route("/test-ai")
def test_ai():
    return """<div style="font-family:sans-serif;padding:40px;max-width:600px">
        <h2 style="color:green">✅ AI is Running in Demo Mode!</h2>
        <p>StudentMart AI recommendations are powered by <b>built-in demo data</b> — no API key required.</p>
        <p>Go to <a href='/recommendations'>AI Recommendations</a> to see it in action.</p>
        </div>"""


# ─────────────────────────────────────────
# AI RECOMMENDATIONS (DEMO MODE — no API key needed)
# ─────────────────────────────────────────
DEMO_AI_DATA = {
    "area_insight": "Students in Nashik/Dhule area are very active on StudentMart! Engineering and tech products are in high demand, especially during exam season. Great deals are available on study materials and electronics.",
    "recommendations": [
        {
            "name": "Scientific Calculator Casio fx-991",
            "reason": "Essential for every engineering student — works for all semesters and competitive exams like GATE.",
            "tip": "Check if it supports matrix calculations. Great value at this price!"
        },
        {
            "name": "HP Laptop 15 Core i5",
            "reason": "Powerful enough for coding, CAD, and projects. 8GB RAM + 512GB SSD is ideal for students.",
            "tip": "Inspect battery health before buying. Ask seller for a live demo."
        },
        {
            "name": "GATE 2024 Study Material",
            "reason": "Comprehensive notes save weeks of preparation time. Previous year papers are gold for GATE aspirants.",
            "tip": "Start GATE prep from 3rd year — this set gives you a head start!"
        },
        {
            "name": "Physics HC Verma Part 1 & 2",
            "reason": "A must-have for JEE and university physics. Concept clarity + practice problems in one book.",
            "tip": "Pair with NCERT for best results. This seller's copy looks lightly used."
        },
        {
            "name": "Portable Bluetooth Speaker",
            "reason": "Currently ON SALE! Great for hostel life, study music, and group activities.",
            "tip": "boAt Stone 350 has 10-hour battery life — perfect for long study sessions."
        }
    ],
    "categories_trending": ["Electronics", "Books", "Sports", "Stationery"],
    "budget_advice": "Set a budget before browsing! Most essential student items (books, stationery, calculators) are available under Rs.500 on StudentMart. For bigger purchases like laptops, compare with new prices and check product condition carefully."
}

@app.route("/recommendations")
def recommendations():
    user = current_user()
    area = request.args.get("area", user["area"] if user else "Nashik")
    db  = get_db()
    cur = db.cursor()
    cur.execute("SELECT * FROM products WHERE status != 'Sold' ORDER BY views DESC LIMIT 30")
    all_products = cur.fetchall()
    db.close()

    # Use demo AI data — no API key required
    ai_data  = DEMO_AI_DATA
    ai_error = None

    matched_products = []
    db  = get_db()
    cur = db.cursor()
    for rec in ai_data["recommendations"]:
        cur.execute("SELECT * FROM products WHERE name LIKE ? LIMIT 1", ("%" + rec["name"][:20] + "%",))
        p = cur.fetchone()
        if p:
            matched_products.append({"product": p, "reason": rec["reason"], "tip": rec["tip"]})
    db.close()

    return render_template("recommendations.html", ai_data=ai_data,
                           matched_products=matched_products, ai_error=ai_error,
                           area=area, user=user)


# ─────────────────────────────────────────
# AUTH
# ─────────────────────────────────────────
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        name    = request.form.get("name")
        email   = request.form.get("email")
        pw      = hash_password(request.form.get("password"))
        area    = request.form.get("area", "Dhule")
        college = request.form.get("college", "")
        phone   = request.form.get("phone", "")
        db  = get_db()
        cur = db.cursor()
        try:
            cur.execute("INSERT INTO users (name,email,password,area,college,phone) VALUES (?,?,?,?,?,?)",
                        (name, email, pw, area, college, phone))
            db.commit()
            cur.execute("SELECT * FROM users WHERE email=?", (email,))
            user = cur.fetchone()
            session["user_id"] = user["id"]
            db.close()
            flash(f"Welcome to StudentMart, {name}! 🎉")
            return redirect(url_for("home"))
        except sqlite3.IntegrityError:
            db.close()
            flash("Email already registered. Please login.")
            return redirect(url_for("login"))
    return render_template("register.html")

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email")
        pw    = hash_password(request.form.get("password"))
        db    = get_db()
        cur   = db.cursor()
        cur.execute("SELECT * FROM users WHERE email=? AND password=?", (email, pw))
        user  = cur.fetchone()
        db.close()
        if user:
            session["user_id"] = user["id"]
            flash(f"Welcome back, {user['name']}! 👋")
            return redirect(url_for("home"))
        else:
            flash("Wrong email or password.")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))

@app.route("/uploads/<filename>")
def uploaded_file(filename):
    return send_from_directory(app.config["UPLOAD_FOLDER"], filename)

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
