from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime
from werkzeug.security import generate_password_hash, check_password_hash
from functools import wraps

app = Flask(__name__)
app.secret_key = "koperasi_app"


# ================= DATABASE =================
def db():
    conn = sqlite3.connect("koperasi.db")
    conn.row_factory = sqlite3.Row
    return conn


# ================= INIT DB (AUTO FIX) =================
with db() as conn:
    conn.execute("""
    CREATE TABLE IF NOT EXISTS users (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        username TEXT UNIQUE,
        password TEXT,
        role TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS produk (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nama TEXT,
        beli INTEGER,
        jual INTEGER,
        stok INTEGER,
        expired TEXT
    )
    """)

    conn.execute("""
    CREATE TABLE IF NOT EXISTS transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total INTEGER,
        profit INTEGER,
        waktu TEXT
    )
    """)

    # FIX: expired column (ANTI ERROR)
    try:
        conn.execute("ALTER TABLE produk ADD COLUMN expired TEXT")
    except:
        pass

    conn.commit()


# ================= LOGIN REQUIRED =================
def login_required(role=None):
    def wrap(func):
        @wraps(func)
        def inner(*args, **kwargs):
            if "user" not in session:
                return redirect("/login")

            if role and session.get("role") != role:
                return "Tidak punya akses"

            return func(*args, **kwargs)
        return inner
    return wrap


# ================= REGISTER =================
@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form["username"]
        password = generate_password_hash(request.form["password"])
        role = request.form["role"]

        try:
            with db() as conn:
                conn.execute(
                    "INSERT INTO users (username,password,role) VALUES (?,?,?)",
                    (username, password, role)
                )
                conn.commit()
        except:
            return "Username sudah dipakai"

        return redirect("/login")

    return render_template("register.html")


# ================= LOGIN =================
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        u = request.form["username"]
        p = request.form["password"]

        with db() as conn:
            user = conn.execute(
                "SELECT * FROM users WHERE username=?",
                (u,)
            ).fetchone()

        if user and check_password_hash(user["password"], p):
            session["user"] = user["username"]
            session["role"] = user["role"]
            session["cart"] = []
            return redirect("/")

        return render_template("login.html", error="Username atau password salah ❌")

    return render_template("login.html")


# ================= LOGOUT =================
@app.route("/logout")
def logout():
    session.clear()
    return redirect("/login")


# ================= DASHBOARD =================
@app.route("/")
@login_required()
def index():
    with db() as conn:
        produk = conn.execute("SELECT * FROM produk").fetchall()

    return render_template("index.html", produk=produk)


# ================= ADD PRODUK (FIX EXPIRY INPUT) =================
@app.route("/add", methods=["POST"])
@login_required("admin")
def add():
    nama = request.form.get("nama")
    beli = int(request.form.get("beli") or 0)
    jual = int(request.form.get("jual") or 0)
    stok = int(request.form.get("stok") or 0)
    expired = request.form.get("expired")

    if not expired:
        return "Tanggal expired wajib diisi ❌"

    with db() as conn:
        conn.execute("""
            INSERT INTO produk (nama,beli,jual,stok,expired)
            VALUES (?,?,?,?,?)
        """, (nama, beli, jual, stok, expired))
        conn.commit()

    return redirect("/")


# ================= KASIR =================
@app.route("/kasir")
@login_required()
def kasir():
    with db() as conn:
        produk = conn.execute("SELECT * FROM produk").fetchall()

    cart = session.get("cart", [])
    return render_template("kasir.html", produk=produk, cart=cart)


# ================= ADD CART (FIXED STABLE) =================
@app.route("/add_cart/<int:id>")
@login_required()
def add_cart(id):
    with db() as conn:
        p = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()

    if not p:
        return redirect("/kasir")

    if (p["stok"] or 0) <= 0:
        return "Stok habis ❌"

    # cek expired
    if p["expired"]:
        try:
            exp = datetime.strptime(p["expired"], "%Y-%m-%d").date()
            if exp < datetime.now().date():
                return "Produk sudah expired ❌"
        except:
            pass

    cart = session.get("cart", [])

    found = False
    for item in cart:
        if item["id"] == p["id"]:
            item["qty"] += 1
            found = True
            break

    if not found:
        cart.append({
            "id": p["id"],
            "nama": p["nama"],
            "beli": int(p["beli"]),
            "jual": int(p["jual"]),
            "qty": 1
        })

    session["cart"] = cart

    with db() as conn:
        conn.execute("UPDATE produk SET stok = stok - 1 WHERE id=?", (id,))
        conn.commit()

    return redirect("/kasir")

@app.route("/remove_cart/<int:id>")
@login_required()
def remove_cart(id):
    cart = session.get("cart", [])

    for item in cart:
        if item["id"] == id:
            item["qty"] -= 1

            if item["qty"] <= 0:
                cart.remove(item)

            break

    session["cart"] = cart
    return redirect("/kasir")

# ================= CHECKOUT =================
@app.route("/checkout")
@login_required()
def checkout():
    cart = session.get("cart", [])

    if not cart:
        return redirect("/kasir")

    total = 0
    profit = 0

    for item in cart:
        total += item["jual"] * item["qty"]
        profit += (item["jual"] - item["beli"]) * item["qty"]

    with db() as conn:
        conn.execute("""
            INSERT INTO transaksi (total,profit,waktu)
            VALUES (?,?,?)
        """, (
            total,
            profit,
            datetime.now().strftime("%Y-%m-%d %H:%M:%S")
        ))
        conn.commit()

    session["cart"] = []

    return render_template("struk.html", data=cart, total=total, profit=profit)


# ================= PROFIT =================
@app.route("/profit")
@login_required("admin")
def profit():
    with db() as conn:
        total = conn.execute("SELECT SUM(profit) FROM transaksi").fetchone()[0]

    return render_template("profit.html", total=total or 0)


# ================= LAPORAN =================
@app.route("/laporan/harian")
@login_required("admin")
def laporan_harian():
    today = datetime.now().strftime("%Y-%m-%d")

    with db() as conn:
        data = conn.execute(
            "SELECT * FROM transaksi WHERE waktu LIKE ?",
            (today + "%",)
        ).fetchall()

    return render_template("laporan.html", data=data)


@app.route("/laporan/bulanan")
@login_required("admin")
def laporan_bulanan():
    month = datetime.now().strftime("%Y-%m")

    with db() as conn:
        data = conn.execute(
            "SELECT * FROM transaksi WHERE waktu LIKE ?",
            (month + "%",)
        ).fetchall()

    return render_template("laporan.html", data=data)

@app.route("/dashboard/grafik")
@login_required("admin")
def grafik():
    with db() as conn:
        data = conn.execute("""
            SELECT waktu, total 
            FROM transaksi 
            ORDER BY id ASC
        """).fetchall()

    labels = []
    values = []

    for d in data:
        labels.append(d["waktu"])
        values.append(d["total"])

    return render_template("grafik.html", labels=labels, values=values)


# ================= RUN =================
if __name__ == "__main__":
    app.run(host="0.0.0.0", port=5000)