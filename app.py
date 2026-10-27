import os, sqlite3, hashlib, secrets
from datetime import datetime
from functools import wraps
from flask import Flask, render_template, request, redirect, url_for, session, flash, jsonify, abort

APP_DIR=os.path.dirname(os.path.abspath(__file__))
DB_PATH=os.path.join(APP_DIR,"pos.db")
app=Flask(__name__)
app.secret_key=os.environ.get("SECRET_KEY","change-this-secret-before-production")

def db():
    con=sqlite3.connect(DB_PATH)
    con.row_factory=sqlite3.Row
    con.execute("PRAGMA foreign_keys=ON")
    return con

def pw_hash(password, salt=None):
    salt=salt or secrets.token_hex(16)
    return salt+"$"+hashlib.pbkdf2_hmac("sha256",password.encode(),salt.encode(),180000).hex()

def check_pw(password, stored):
    try:
        salt,_=stored.split("$",1)
        return secrets.compare_digest(pw_hash(password,salt),stored)
    except Exception: return False

def init_db():
    con=db()
    con.executescript("""
    CREATE TABLE IF NOT EXISTS users(id INTEGER PRIMARY KEY, name TEXT NOT NULL, username TEXT UNIQUE NOT NULL, password TEXT NOT NULL, role TEXT NOT NULL CHECK(role IN ('admin','staff')), active INTEGER DEFAULT 1, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS products(id INTEGER PRIMARY KEY, sku TEXT UNIQUE NOT NULL, name TEXT NOT NULL, category TEXT DEFAULT 'General', size TEXT DEFAULT '', color TEXT DEFAULT '', price REAL NOT NULL DEFAULT 0, cost REAL NOT NULL DEFAULT 0, stock INTEGER NOT NULL DEFAULT 0, reorder_level INTEGER NOT NULL DEFAULT 5, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS suppliers(id INTEGER PRIMARY KEY, name TEXT NOT NULL, phone TEXT DEFAULT '', email TEXT DEFAULT '', address TEXT DEFAULT '', balance REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    CREATE TABLE IF NOT EXISTS sales(id INTEGER PRIMARY KEY, invoice TEXT UNIQUE NOT NULL, staff_id INTEGER, subtotal REAL NOT NULL, discount REAL DEFAULT 0, tax REAL DEFAULT 0, total REAL NOT NULL, payment_method TEXT DEFAULT 'Cash', paid REAL DEFAULT 0, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(staff_id) REFERENCES users(id));
    CREATE TABLE IF NOT EXISTS sale_items(id INTEGER PRIMARY KEY, sale_id INTEGER NOT NULL, product_id INTEGER, product_name TEXT NOT NULL, sku TEXT, qty INTEGER NOT NULL, price REAL NOT NULL, line_total REAL NOT NULL, FOREIGN KEY(sale_id) REFERENCES sales(id), FOREIGN KEY(product_id) REFERENCES products(id));
    CREATE TABLE IF NOT EXISTS returns(id INTEGER PRIMARY KEY, sale_id INTEGER, product_id INTEGER, qty INTEGER NOT NULL, amount REAL NOT NULL, reason TEXT DEFAULT '', processed_by INTEGER, created_at TEXT DEFAULT CURRENT_TIMESTAMP, FOREIGN KEY(sale_id) REFERENCES sales(id), FOREIGN KEY(product_id) REFERENCES products(id));
    CREATE TABLE IF NOT EXISTS ledger(id INTEGER PRIMARY KEY, entry_type TEXT NOT NULL, description TEXT NOT NULL, amount REAL NOT NULL, reference TEXT DEFAULT '', created_at TEXT DEFAULT CURRENT_TIMESTAMP);
    """)
    if not con.execute("SELECT id FROM users LIMIT 1").fetchone():
        con.execute("INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)",("Store Administrator","admin",pw_hash("Admin@123"),"admin"))
        con.execute("INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)",("Billing Staff","staff",pw_hash("Staff@123"),"staff"))
    if not con.execute("SELECT id FROM products LIMIT 1").fetchone():
        seed=[
        ("TX-1001","Classic Cotton Shirt","Shirts","M","White",899,520,24,5),
        ("TX-1002","Linen Casual Shirt","Shirts","L","Olive",1299,760,16,4),
        ("TX-1003","Slim Fit Denim","Jeans","32","Indigo",1799,1100,12,3),
        ("TX-1004","Everyday Chinos","Trousers","34","Sand",1499,890,18,4),
        ("TX-1005","Premium Kurta","Ethnic","L","Navy",1599,920,9,3),
        ("TX-1006","Soft Cotton Saree","Sarees","Free","Maroon",2499,1500,7,2),
        ("TX-1007","Printed T-Shirt","T-Shirts","M","Black",599,280,31,8),
        ("TX-1008","Formal Trousers","Trousers","32","Charcoal",1199,690,4,5)]
        con.executemany("INSERT INTO products(sku,name,category,size,color,price,cost,stock,reorder_level) VALUES(?,?,?,?,?,?,?,?,?)",seed)
        con.executemany("INSERT INTO suppliers(name,phone,email,address,balance) VALUES(?,?,?,?,?)",[
        ("Aster Textiles","+91 98765 43210","orders@aster.example","Coimbatore, Tamil Nadu",12500),
        ("Thread & Loom","+91 98765 12345","sales@threadloom.example","Tiruppur, Tamil Nadu",6800)])
    con.commit(); con.close()

def login_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not session.get("user_id"): return redirect(url_for("login",next=request.path))
        return fn(*args,**kwargs)
    return wrapper

def admin_required(fn):
    @wraps(fn)
    def wrapper(*args,**kwargs):
        if not session.get("user_id"): return redirect(url_for("login"))
        if session.get("role")!="admin":
            flash("Admin access is required for that page.","error")
            return redirect(url_for("billing"))
        return fn(*args,**kwargs)
    return wrapper

@app.context_processor
def globals_ctx():
    return {"current_user":session.get("name"),"current_role":session.get("role"),"money":lambda x: "₹{:,.2f}".format(float(x or 0))}

@app.route("/")
def home(): return redirect(url_for("dashboard") if session.get("user_id") else url_for("login"))

@app.route("/login",methods=["GET","POST"])
def login():
    if request.method=="POST":
        con=db(); user=con.execute("SELECT * FROM users WHERE username=? AND active=1",(request.form.get("username","").strip(),)).fetchone(); con.close()
        if user and check_pw(request.form.get("password",""),user["password"]):
            session.clear(); session.update(user_id=user["id"],name=user["name"],role=user["role"],username=user["username"])
            return redirect(url_for("billing") if user["role"]=="staff" else url_for("dashboard"))
        flash("Incorrect username or password.","error")
    return render_template("login.html")

@app.route("/logout")
def logout(): session.clear(); return redirect(url_for("login"))

@app.route("/dashboard")
@admin_required
def dashboard():
    con=db()
    today=datetime.now().strftime("%Y-%m-%d")
    sales=con.execute("SELECT COUNT(*) n,COALESCE(SUM(total),0) total FROM sales WHERE date(created_at)=?",(today,)).fetchone()
    month=con.execute("SELECT COALESCE(SUM(total),0) total FROM sales WHERE strftime('%Y-%m',created_at)=strftime('%Y-%m','now','localtime')").fetchone()["total"]
    products=con.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
    low=con.execute("SELECT * FROM products WHERE stock<=reorder_level ORDER BY stock ASC LIMIT 6").fetchall()
    recent=con.execute("SELECT s.*,u.name staff FROM sales s LEFT JOIN users u ON s.staff_id=u.id ORDER BY s.id DESC LIMIT 6").fetchall()
    chart=con.execute("SELECT date(created_at) day, SUM(total) total FROM sales WHERE created_at>=datetime('now','-6 days') GROUP BY date(created_at) ORDER BY day").fetchall()
    con.close()
    return render_template("dashboard.html",sales=sales,month=month,products=products,low=low,recent=recent,chart=chart)

@app.route("/products",methods=["GET","POST"])
@admin_required
def products():
    con=db()
    if request.method=="POST":
        try:
            data=(request.form["sku"].strip(),request.form["name"].strip(),request.form.get("category","General"),request.form.get("size",""),request.form.get("color",""),float(request.form.get("price",0)),float(request.form.get("cost",0)),int(request.form.get("stock",0)),int(request.form.get("reorder_level",5)))
            pid=request.form.get("id")
            if pid:
                con.execute("UPDATE products SET sku=?,name=?,category=?,size=?,color=?,price=?,cost=?,stock=?,reorder_level=? WHERE id=?",data+(int(pid),))
                flash("Product updated successfully.")
            else:
                con.execute("INSERT INTO products(sku,name,category,size,color,price,cost,stock,reorder_level) VALUES(?,?,?,?,?,?,?,?,?)",data)
                flash("Product added to inventory.")
            con.commit()
        except sqlite3.IntegrityError: flash("SKU must be unique.","error")
        except Exception: flash("Please check the product details.","error")
        con.close(); return redirect(url_for("products"))
    edit=con.execute("SELECT * FROM products WHERE id=?",(request.args.get("edit"),)).fetchone() if request.args.get("edit") else None
    rows=con.execute("SELECT * FROM products WHERE name LIKE ? OR sku LIKE ? ORDER BY id DESC",("%"+request.args.get("q","")+"%","%"+request.args.get("q","")+"%")).fetchall()
    con.close(); return render_template("products.html",products=rows,edit=edit,q=request.args.get("q",""))

@app.route("/products/delete/<int:pid>",methods=["POST"])
@admin_required
def delete_product(pid):
    con=db()
    try: con.execute("DELETE FROM products WHERE id=?",(pid,)); con.commit(); flash("Product deleted.")
    except sqlite3.IntegrityError: flash("This product has sales history and cannot be deleted. Set stock to zero instead.","error")
    con.close(); return redirect(url_for("products"))

@app.route("/staff",methods=["GET","POST"])
@admin_required
def staff():
    con=db()
    if request.method=="POST":
        try:
            uid=request.form.get("id")
            if uid:
                con.execute("UPDATE users SET name=?,username=?,role=?,active=? WHERE id=?",(request.form["name"],request.form["username"],request.form["role"],int(request.form.get("active",1)),int(uid)))
                if request.form.get("password"): con.execute("UPDATE users SET password=? WHERE id=?",(pw_hash(request.form["password"]),int(uid)))
                flash("Staff account updated.")
            else:
                con.execute("INSERT INTO users(name,username,password,role) VALUES(?,?,?,?)",(request.form["name"],request.form["username"],pw_hash(request.form["password"]),request.form["role"]))
                flash("Staff account created.")
            con.commit()
        except sqlite3.IntegrityError: flash("Username already exists.","error")
        except Exception: flash("Please check the staff details.","error")
        con.close(); return redirect(url_for("staff"))
    edit=con.execute("SELECT id,name,username,role,active FROM users WHERE id=?",(request.args.get("edit"),)).fetchone() if request.args.get("edit") else None
    rows=con.execute("SELECT id,name,username,role,active,created_at FROM users ORDER BY id").fetchall(); con.close()
    return render_template("staff.html",staff=rows,edit=edit)

@app.route("/suppliers",methods=["GET","POST"])
@admin_required
def suppliers():
    con=db()
    if request.method=="POST":
        vals=(request.form["name"],request.form.get("phone",""),request.form.get("email",""),request.form.get("address",""),float(request.form.get("balance",0)))
        sid=request.form.get("id")
        if sid: con.execute("UPDATE suppliers SET name=?,phone=?,email=?,address=?,balance=? WHERE id=?",vals+(int(sid),)); flash("Supplier updated.")
        else: con.execute("INSERT INTO suppliers(name,phone,email,address,balance) VALUES(?,?,?,?,?)",vals); flash("Supplier added.")
        con.commit(); con.close(); return redirect(url_for("suppliers"))
    edit=con.execute("SELECT * FROM suppliers WHERE id=?",(request.args.get("edit"),)).fetchone() if request.args.get("edit") else None
    rows=con.execute("SELECT * FROM suppliers ORDER BY id DESC").fetchall(); con.close()
    return render_template("suppliers.html",suppliers=rows,edit=edit)

@app.route("/billing")
@login_required
def billing():
    con=db(); products=con.execute("SELECT * FROM products WHERE stock>0 ORDER BY name").fetchall()
    con.close(); return render_template("billing.html",products=products)

@app.route("/api/products")
@login_required
def api_products():
    con=db(); rows=con.execute("SELECT id,sku,name,category,size,color,price,stock FROM products WHERE stock>0 AND (name LIKE ? OR sku LIKE ?) ORDER BY name LIMIT 30",("%"+request.args.get("q","")+"%","%"+request.args.get("q","")+"%")).fetchall(); con.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/checkout",methods=["POST"])
@login_required
def checkout():
    payload=request.get_json(silent=True) or {}
    items=payload.get("items",[])
    if not items: return jsonify(error="Add at least one item."),400
    con=db()
    try:
        subtotal=0; clean=[]
        for item in items:
            p=con.execute("SELECT * FROM products WHERE id=?",(int(item["id"]),)).fetchone()
            qty=int(item["qty"])
            if not p or qty<1: raise ValueError("Invalid item quantity.")
            if p["stock"]<qty: raise ValueError(f"Not enough stock for {p['name']}. Available: {p['stock']}.")
            line=round(p["price"]*qty,2); subtotal+=line; clean.append((p,qty,line))
        discount=max(0,min(float(payload.get("discount",0)),subtotal))
        tax=round((subtotal-discount)*float(payload.get("tax_rate",0))/100,2)
        total=round(subtotal-discount+tax,2)
        paid=float(payload.get("paid",total))
        if paid+0.001<total: raise ValueError("Payment received is less than the total.")
        method=payload.get("payment_method","Cash")
        invoice="ECH-"+datetime.now().strftime("%y%m%d-%H%M%S")+"-"+secrets.token_hex(2).upper()
        cur=con.execute("INSERT INTO sales(invoice,staff_id,subtotal,discount,tax,total,payment_method,paid) VALUES(?,?,?,?,?,?,?,?)",(invoice,session["user_id"],subtotal,discount,tax,total,method,paid))
        sale_id=cur.lastrowid
        for p,qty,line in clean:
            con.execute("INSERT INTO sale_items(sale_id,product_id,product_name,sku,qty,price,line_total) VALUES(?,?,?,?,?,?,?)",(sale_id,p["id"],p["name"],p["sku"],qty,p["price"],line))
            con.execute("UPDATE products SET stock=stock-? WHERE id=?",(qty,p["id"]))
        con.execute("INSERT INTO ledger(entry_type,description,amount,reference) VALUES('Income',?,?,?)",(f"Sale {invoice}",total,invoice))
        con.commit()
        return jsonify(ok=True,sale_id=sale_id,invoice=invoice,total=total)
    except (ValueError,KeyError,TypeError) as e:
        con.rollback(); return jsonify(error=str(e)),400
    except Exception:
        con.rollback(); return jsonify(error="Checkout failed. Please try again."),500
    finally: con.close()

@app.route("/receipt/<int:sale_id>")
@login_required
def receipt(sale_id):
    con=db(); sale=con.execute("SELECT s.*,u.name staff FROM sales s LEFT JOIN users u ON s.staff_id=u.id WHERE s.id=?",(sale_id,)).fetchone()
    if not sale: con.close(); abort(404)
    items=con.execute("SELECT * FROM sale_items WHERE sale_id=?",(sale_id,)).fetchall(); con.close()
    return render_template("receipt.html",sale=sale,items=items)

@app.route("/transactions")
@admin_required
def transactions():
    con=db(); rows=con.execute("SELECT s.*,u.name staff FROM sales s LEFT JOIN users u ON s.staff_id=u.id ORDER BY s.id DESC LIMIT 200").fetchall()
    total=con.execute("SELECT COALESCE(SUM(total),0) n FROM sales").fetchone()["n"]; con.close()
    return render_template("transactions.html",sales=rows,total=total)

@app.route("/returns",methods=["GET","POST"])
@admin_required
def returns():
    con=db()
    if request.method=="POST":
        try:
            invoice=request.form["invoice"].strip()
            sale=con.execute("SELECT * FROM sales WHERE invoice=?",(invoice,)).fetchone()
            product=con.execute("SELECT * FROM products WHERE id=?",(int(request.form["product_id"]),)).fetchone()
            qty=int(request.form["qty"])
            sold=con.execute("SELECT COALESCE(SUM(qty),0) n,COALESCE(SUM(line_total),0) amount FROM sale_items WHERE sale_id=? AND product_id=?",(sale["id"],product["id"])).fetchone() if sale and product else None
            already=con.execute("SELECT COALESCE(SUM(qty),0) n FROM returns WHERE sale_id=? AND product_id=?",(sale["id"],product["id"])).fetchone()["n"] if sale and product else 0
            if not sale or not product or qty<1 or sold["n"]-already<qty: raise ValueError("Invoice/product not found or return quantity exceeds eligible quantity.")
            amount=round(sold["amount"]/sold["n"]*qty,2)
            con.execute("INSERT INTO returns(sale_id,product_id,qty,amount,reason,processed_by) VALUES(?,?,?,?,?,?)",(sale["id"],product["id"],qty,amount,request.form.get("reason",""),session["user_id"]))
            con.execute("UPDATE products SET stock=stock+? WHERE id=?",(qty,product["id"]))
            con.execute("INSERT INTO ledger(entry_type,description,amount,reference) VALUES('Refund',?,?,?)",(f"Return {invoice} — {product['name']}",-amount,invoice))
            con.commit(); flash(f"Return processed. Refund value {money(amount)}.")
        except Exception as e: con.rollback(); flash(str(e) if isinstance(e,ValueError) else "Could not process return. Check the invoice and product.","error")
        con.close(); return redirect(url_for("returns"))
    rows=con.execute("SELECT r.*,s.invoice,p.name product,u.name staff FROM returns r LEFT JOIN sales s ON r.sale_id=s.id LEFT JOIN products p ON r.product_id=p.id LEFT JOIN users u ON r.processed_by=u.id ORDER BY r.id DESC").fetchall()
    sales=con.execute("SELECT id,invoice FROM sales ORDER BY id DESC LIMIT 100").fetchall(); products=con.execute("SELECT id,name,sku FROM products ORDER BY name").fetchall(); con.close()
    return render_template("returns.html",returns=rows,sales=sales,products=products)

@app.route("/ledger")
@admin_required
def ledger():
    con=db(); rows=con.execute("SELECT * FROM ledger ORDER BY id DESC LIMIT 300").fetchall()
    income=con.execute("SELECT COALESCE(SUM(amount),0) n FROM ledger WHERE amount>0").fetchone()["n"]
    refunds=con.execute("SELECT COALESCE(SUM(amount),0) n FROM ledger WHERE amount<0").fetchone()["n"]
    con.close(); return render_template("ledger.html",entries=rows,income=income,refunds=abs(refunds))

@app.route("/reports")
@admin_required
def reports():
    con=db()
    daily=con.execute("SELECT date(created_at) day,COUNT(*) bills,SUM(total) revenue FROM sales GROUP BY date(created_at) ORDER BY day DESC LIMIT 14").fetchall()
    categories=con.execute("SELECT p.category,SUM(si.qty) units,SUM(si.line_total) revenue FROM sale_items si LEFT JOIN products p ON si.product_id=p.id GROUP BY p.category ORDER BY revenue DESC").fetchall()
    top=con.execute("SELECT product_name,SUM(qty) units,SUM(line_total) revenue FROM sale_items GROUP BY product_name ORDER BY units DESC LIMIT 8").fetchall()
    con.close(); return render_template("reports.html",daily=daily,categories=categories,top=top)

@app.route("/mobile")
@login_required
def mobile():
    if session.get("role")=="staff": return redirect(url_for("billing"))
    return render_template("dashboard.html",mobile_mode=True,**dashboard_data())

def dashboard_data():
    con=db(); today=datetime.now().strftime("%Y-%m-%d")
    sales=con.execute("SELECT COUNT(*) n,COALESCE(SUM(total),0) total FROM sales WHERE date(created_at)=?",(today,)).fetchone()
    month=con.execute("SELECT COALESCE(SUM(total),0) total FROM sales WHERE strftime('%Y-%m',created_at)=strftime('%Y-%m','now','localtime')").fetchone()["total"]
    products=con.execute("SELECT COUNT(*) n FROM products").fetchone()["n"]
    low=con.execute("SELECT * FROM products WHERE stock<=reorder_level ORDER BY stock ASC LIMIT 6").fetchall()
    recent=con.execute("SELECT s.*,u.name staff FROM sales s LEFT JOIN users u ON s.staff_id=u.id ORDER BY s.id DESC LIMIT 6").fetchall()
    chart=con.execute("SELECT date(created_at) day, SUM(total) total FROM sales WHERE created_at>=datetime('now','-6 days') GROUP BY date(created_at) ORDER BY day").fetchall()
    con.close(); return dict(sales=sales,month=month,products=products,low=low,recent=recent,chart=chart)

@app.route("/mobile/<page>")
@admin_required
def mobile_page(page):
    allowed={"products","staff","suppliers","returns","ledger","reports","transactions"}
    if page not in allowed: abort(404)
    # Same fully functional pages; responsive shell automatically adapts to phone widths.
    return redirect(url_for(page, mobile=1))

init_db()

if __name__=="__main__":
    app.run(debug=os.environ.get("FLASK_DEBUG","0")=="1",host="0.0.0.0",port=int(os.environ.get("PORT",5000)))
