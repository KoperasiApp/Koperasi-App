from flask import Flask, render_template, request, redirect, session
import sqlite3
from datetime import datetime

app = Flask(__name__)
app.secret_key = "koperasi_app"

# ================= DB =================
def db():
    conn = sqlite3.connect("koperasi.db")
    conn.row_factory = sqlite3.Row
    return conn

# ================= INIT DB =================
with db() as conn:
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

    # tambah kolom satuan (aman)
    try:
        conn.execute("ALTER TABLE produk ADD COLUMN satuan TEXT")
    except:
        pass

    conn.execute("""
    CREATE TABLE IF NOT EXISTS transaksi (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        total INTEGER,
        profit INTEGER,
        waktu TEXT
    )
    """)
    conn.commit()

# ================= AUTO ADMIN =================
@app.before_request
def auto_admin():
    session["user"] = "admin"
    session["role"] = "admin"
    if "cart" not in session:
        session["cart"] = []

# ================= DASHBOARD + SEARCH =================
@app.route("/")
def index():
    q = request.args.get("q")

    with db() as conn:
        if q:
            produk = conn.execute(
                "SELECT * FROM produk WHERE nama LIKE ?",
                ("%" + q + "%",)
            ).fetchall()
        else:
            produk = conn.execute("SELECT * FROM produk").fetchall()

    return render_template("index.html", produk=produk)

# ================= TAMBAH PRODUK =================
@app.route("/add", methods=["POST"])
def add():
    with db() as conn:
        conn.execute("""
        INSERT INTO produk (nama,beli,jual,stok,expired,satuan)
        VALUES (?,?,?,?,?,?)
        """, (
            request.form["nama"],
            request.form["beli"],
            request.form["jual"],
            request.form["stok"],
            request.form["expired"],
            request.form["satuan"]
        ))
        conn.commit()
    return redirect("/")

# ================= EDIT =================
@app.route("/edit/<int:id>", methods=["GET","POST"])
def edit(id):
    with db() as conn:
        if request.method == "POST":
            conn.execute("""
            UPDATE produk 
            SET nama=?, beli=?, jual=?, stok=?, expired=?, satuan=?
            WHERE id=?
            """, (
                request.form["nama"],
                request.form["beli"],
                request.form["jual"],
                request.form["stok"],
                request.form["expired"],
                request.form["satuan"],
                id
            ))
            conn.commit()
            return redirect("/")

        produk = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()

    return render_template("edit.html", p=produk)

# ================= HAPUS =================
@app.route("/hapus_produk/<int:id>")
def hapus_produk(id):
    with db() as conn:
        conn.execute("DELETE FROM produk WHERE id=?", (id,))
        conn.commit()
    return redirect("/")

# ================= TAMBAH STOK =================
@app.route("/tambah_stok/<int:id>")
def tambah_stok(id):
    with db() as conn:
        conn.execute("UPDATE produk SET stok = stok + 1 WHERE id=?", (id,))
        conn.commit()
    return redirect("/")

# ================= KASIR =================
@app.route("/kasir")
def kasir():
    with db() as conn:
        produk = conn.execute("SELECT * FROM produk").fetchall()
    return render_template("kasir.html", produk=produk, cart=session["cart"])

# ================= ADD CART =================
@app.route("/add_cart/<int:id>")
def add_cart(id):
    with db() as conn:
        p = conn.execute("SELECT * FROM produk WHERE id=?", (id,)).fetchone()

    if not p or p["stok"] <= 0:
        return redirect("/kasir")

    cart = session["cart"]

    for item in cart:
        if item["id"] == p["id"]:
            item["qty"] += 1
            break
    else:
        cart.append({
            "id": p["id"],
            "nama": p["nama"],
            "beli": p["beli"],
            "jual": p["jual"],
            "satuan": p["satuan"],
            "qty": 1
        })

    session["cart"] = cart

    with db() as conn:
        conn.execute("UPDATE produk SET stok = stok - 1 WHERE id=?", (id,))
        conn.commit()

    return redirect("/kasir")

# ================= CHECKOUT =================
@app.route("/checkout")
def checkout():
    cart = session["cart"]

    total = sum(i["jual"] * i["qty"] for i in cart)
    profit = sum((i["jual"] - i["beli"]) * i["qty"] for i in cart)

    with db() as conn:
        conn.execute("""
        INSERT INTO transaksi (total,profit,waktu)
        VALUES (?,?,?)
        """, (total, profit, datetime.now().strftime("%Y-%m-%d %H:%M:%S")))
        conn.commit()

    session["cart"] = []

    return render_template("struk.html", data=cart, total=total, profit=profit)

# ================= RUN =================
if __name__ == "__main__":
    app.run(debug=True)