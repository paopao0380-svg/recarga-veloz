from flask import Flask, render_template, request, redirect, url_for, session, flash, make_response
from flask_login import LoginManager, UserMixin, login_user, login_required, logout_user, current_user
from werkzeug.utils import secure_filename
from datetime import datetime, timedelta
import sqlite3
import os
import uuid
import csv
import io

app = Flask(__name__)
app.secret_key = "recarga_veloz_secreto_2026"

# Configuración para subir imágenes
UPLOAD_FOLDER = os.path.join("static", "img", "productos")
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif", "webp"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER
os.makedirs(UPLOAD_FOLDER, exist_ok=True)

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

login_manager = LoginManager()
login_manager.init_app(app)
login_manager.login_view = "login"

# -----------------------------
# Base de datos
# -----------------------------
def get_db():
    conn = sqlite3.connect("recarga_veloz.db")
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    conn = get_db()
    cursor = conn.cursor()

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            usuario TEXT UNIQUE,
            password TEXT,
            rol TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS categorias (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS productos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nombre TEXT,
            precio REAL,
            imagen TEXT,
            categoria_id INTEGER,
            stock INTEGER DEFAULT 0,
            stock_minimo INTEGER DEFAULT 5,
            activo INTEGER DEFAULT 1
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            numero_orden TEXT,
            fecha TEXT,
            estado TEXT DEFAULT 'Pendiente',
            total REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS detalle_pedidos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            pedido_id INTEGER,
            producto_id INTEGER,
            cantidad INTEGER,
            precio_unitario REAL
        )
    """)

    cursor.execute("""
        CREATE TABLE IF NOT EXISTS gastos (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            descripcion TEXT,
            monto REAL,
            fecha TEXT,
            categoria TEXT
        )
    """)

    # Datos iniciales
    cursor.execute("SELECT COUNT(*) FROM categorias")
    if cursor.fetchone()[0] == 0:
        cursor.execute("INSERT INTO categorias (nombre) VALUES ('Sólidos'), ('Bebidas'), ('Postres')")

        cursor.execute("""
            INSERT INTO productos (nombre, precio, imagen, categoria_id, stock, stock_minimo) VALUES 
            ('Pollo a la Plancha', 4.50, 'https://images.unsplash.com/photo-1532550907401-a532f4bfec1f?w=400', 1, 20, 5),
            ('Quinoa Bowl', 4.75, 'https://images.unsplash.com/photo-1512621776951-a57141f2eefd?w=400', 1, 15, 5),
            ('Pescado al Horno', 5.25, 'https://images.unsplash.com/photo-1467003909585-2f8a72700288?w=400', 1, 12, 5),
            ('Wrap de Vegetales', 4.25, 'https://images.unsplash.com/photo-1626700051175-6818013e1d4f?w=400', 1, 18, 5),
            ('Jugo Natural', 2.50, 'https://images.unsplash.com/photo-1622597467836-f3285f2131b8?w=400', 2, 30, 8),
            ('Smoothie de Frutas', 3.00, 'https://images.unsplash.com/photo-1505252585461-04db1eb84625?w=400', 2, 25, 8),
            ('Agua de Coco', 2.00, 'https://images.unsplash.com/photo-1556679343-c7306c1976bc?w=400', 2, 40, 10),
            ('Yogurt con Granola', 2.75, 'https://images.unsplash.com/photo-1488477181946-6428a0291777?w=400', 3, 18, 5),
            ('Ensalada de Frutas', 3.25, 'https://images.unsplash.com/photo-1564093497595-593b96bf6d7a?w=400', 3, 15, 5)
        """)

        cursor.execute("INSERT INTO usuarios (nombre, usuario, password, rol) VALUES ('Administrador', 'admin', 'admin123', 'admin')")
        cursor.execute("INSERT INTO usuarios (nombre, usuario, password, rol) VALUES ('Cajero Bar', 'cajero', 'cajero123', 'cajero')")
        cursor.execute("INSERT INTO usuarios (nombre, usuario, password, rol) VALUES ('Contador', 'contador', 'contador123', 'contador')")

    conn.commit()
    conn.close()

class User(UserMixin):
    def __init__(self, id, nombre, usuario, rol):
        self.id = id
        self.nombre = nombre
        self.usuario = usuario
        self.rol = rol

@login_manager.user_loader
def load_user(user_id):
    conn = get_db()
    user = conn.execute("SELECT * FROM usuarios WHERE id = ?", (user_id,)).fetchone()
    conn.close()
    if user:
        return User(user["id"], user["nombre"], user["usuario"], user["rol"])
    return None

# -----------------------------
# Rutas públicas (Estudiante)
# -----------------------------
@app.route("/")
def index():
    return render_template("index.html")

@app.route("/categoria/<nombre>")
def categoria(nombre):
    conn = get_db()
    cat = conn.execute("SELECT id FROM categorias WHERE nombre = ?", (nombre,)).fetchone()
    productos = []
    if cat:
        productos = conn.execute(
            "SELECT * FROM productos WHERE categoria_id = ? AND activo = 1 AND stock > 0",
            (cat["id"],)
        ).fetchall()
    conn.close()
    return render_template("productos.html", categoria=nombre, productos=productos)

@app.route("/agregar/<int:producto_id>")
def agregar(producto_id):
    if "carrito" not in session:
        session["carrito"] = {}
    carrito = session["carrito"]
    carrito[str(producto_id)] = carrito.get(str(producto_id), 0) + 1
    session["carrito"] = carrito
    flash("Producto agregado al carrito. Puedes cambiar la cantidad o seguir comprando.", "success")
    return redirect(url_for("carrito"))

@app.route("/carrito")
def carrito():
    conn = get_db()
    items = []
    total = 0
    if "carrito" in session:
        for pid, cantidad in session["carrito"].items():
            prod = conn.execute("SELECT * FROM productos WHERE id = ?", (pid,)).fetchone()
            if prod:
                subtotal = prod["precio"] * cantidad
                total += subtotal
                items.append({
                    "id": prod["id"],
                    "nombre": prod["nombre"],
                    "precio": prod["precio"],
                    "cantidad": cantidad,
                    "subtotal": subtotal,
                    "imagen": prod["imagen"]
                })
    conn.close()
    return render_template("carrito.html", items=items, total=total)

@app.route("/actualizar-cantidad/<int:producto_id>/<accion>")
def actualizar_cantidad(producto_id, accion):
    if "carrito" not in session:
        return redirect(url_for("carrito"))
    carrito = session["carrito"]
    key = str(producto_id)
    if key in carrito:
        if accion == "sumar":
            carrito[key] += 1
        elif accion == "restar":
            carrito[key] -= 1
            if carrito[key] <= 0:
                del carrito[key]
    session["carrito"] = carrito
    return redirect(url_for("carrito"))

@app.route("/eliminar/<int:producto_id>")
def eliminar(producto_id):
    if "carrito" in session:
        carrito = session["carrito"]
        key = str(producto_id)
        if key in carrito:
            del carrito[key]
        session["carrito"] = carrito
    return redirect(url_for("carrito"))

@app.route("/confirmar", methods=["POST"])
def confirmar():
    if "carrito" not in session or not session["carrito"]:
        return redirect(url_for("index"))
    conn = get_db()
    ultimo = conn.execute("SELECT COUNT(*) FROM pedidos").fetchone()[0]
    numero_orden = f"RV-{ultimo + 1:04d}"
    total = 0
    for pid, cantidad in session["carrito"].items():
        prod = conn.execute("SELECT precio FROM productos WHERE id = ?", (pid,)).fetchone()
        total += prod["precio"] * cantidad
    conn.execute(
        "INSERT INTO pedidos (numero_orden, fecha, estado, total) VALUES (?, ?, ?, ?)",
        (numero_orden, datetime.now().strftime("%Y-%m-%d %H:%M"), "Pendiente", total)
    )
    pedido_id = conn.execute("SELECT last_insert_rowid()").fetchone()[0]
    for pid, cantidad in session["carrito"].items():
        prod = conn.execute("SELECT precio FROM productos WHERE id = ?", (pid,)).fetchone()
        conn.execute(
            "INSERT INTO detalle_pedidos (pedido_id, producto_id, cantidad, precio_unitario) VALUES (?, ?, ?, ?)",
            (pedido_id, pid, cantidad, prod["precio"])
        )
        conn.execute("UPDATE productos SET stock = stock - ? WHERE id = ?", (cantidad, pid))
    conn.commit()
    conn.close()
    session.pop("carrito", None)
    return render_template("confirmacion.html", numero_orden=numero_orden)

# -----------------------------
# Login
# -----------------------------
@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        usuario = request.form.get("usuario")
        password = request.form.get("password")
        conn = get_db()
        user = conn.execute(
            "SELECT * FROM usuarios WHERE usuario = ? AND password = ?",
            (usuario, password)
        ).fetchone()
        conn.close()
        if user:
            user_obj = User(user["id"], user["nombre"], user["usuario"], user["rol"])
            login_user(user_obj)
            if user["rol"] == "cajero":
                return redirect(url_for("pedidos_bar"))
            elif user["rol"] == "admin":
                return redirect(url_for("admin_panel"))
            elif user["rol"] == "contador":
                return redirect(url_for("dashboard_contable"))
            return redirect(url_for("index"))
        flash("Usuario o contraseña incorrectos", "error")
    return render_template("login.html")

@app.route("/logout")
@login_required
def logout():
    logout_user()
    return redirect(url_for("index"))

# -----------------------------
# Panel del Bar (Cajero)
# -----------------------------
@app.route("/pedidos-bar")
@login_required
def pedidos_bar():
    if current_user.rol not in ["cajero", "admin"]:
        return redirect(url_for("index"))
    conn = get_db()
    pedidos = conn.execute("""
        SELECT p.*, GROUP_CONCAT(pr.nombre || ' x' || d.cantidad, ', ') as productos
        FROM pedidos p
        LEFT JOIN detalle_pedidos d ON p.id = d.pedido_id
        LEFT JOIN productos pr ON d.producto_id = pr.id
        GROUP BY p.id
        ORDER BY p.id DESC
        LIMIT 40
    """).fetchall()
    conn.close()
    return render_template("pedidos_bar.html", pedidos=pedidos)

@app.route("/cambiar-estado/<int:pedido_id>/<estado>")
@login_required
def cambiar_estado(pedido_id, estado):
    if current_user.rol not in ["cajero", "admin"]:
        return redirect(url_for("index"))
    conn = get_db()
    conn.execute("UPDATE pedidos SET estado = ? WHERE id = ?", (estado, pedido_id))
    conn.commit()
    conn.close()
    return redirect(url_for("pedidos_bar"))

@app.route("/recibo/<int:pedido_id>")
@login_required
def recibo(pedido_id):
    """Comprobante de pago imprimible para el cajero"""
    if current_user.rol not in ["cajero", "admin"]:
        return redirect(url_for("index"))
    conn = get_db()
    pedido = conn.execute("SELECT * FROM pedidos WHERE id = ?", (pedido_id,)).fetchone()
    if not pedido:
        conn.close()
        flash("Pedido no encontrado", "error")
        return redirect(url_for("pedidos_bar"))
    detalles = conn.execute("""
        SELECT d.cantidad, d.precio_unitario, pr.nombre, c.nombre as categoria
        FROM detalle_pedidos d
        JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        WHERE d.pedido_id = ?
    """, (pedido_id,)).fetchall()
    conn.close()
    return render_template("recibo.html", pedido=pedido, detalles=detalles)

# -----------------------------
# Panel de Administración
# -----------------------------
@app.route("/admin")
@login_required
def admin_panel():
    if current_user.rol != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    productos = conn.execute("""
        SELECT p.*, c.nombre as categoria 
        FROM productos p 
        LEFT JOIN categorias c ON p.categoria_id = c.id
        ORDER BY p.categoria_id, p.nombre
    """).fetchall()
    conn.close()
    return render_template("admin.html", productos=productos)

@app.route("/admin/producto/nuevo", methods=["GET", "POST"])
@login_required
def admin_nuevo_producto():
    if current_user.rol != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    categorias = conn.execute("SELECT * FROM categorias").fetchall()
    if request.method == "POST":
        nombre = request.form.get("nombre")
        precio = float(request.form.get("precio", 0))
        categoria_id = int(request.form.get("categoria_id"))
        stock = int(request.form.get("stock", 0))
        stock_minimo = int(request.form.get("stock_minimo", 5))
        
        # Manejo de imagen
        imagen = "https://via.placeholder.com/400"
        if "imagen_archivo" in request.files:
            archivo = request.files["imagen_archivo"]
            if archivo and archivo.filename and allowed_file(archivo.filename):
                ext = archivo.filename.rsplit(".", 1)[1].lower()
                nombre_archivo = f"{uuid.uuid4().hex}.{ext}"
                ruta = os.path.join(app.config["UPLOAD_FOLDER"], nombre_archivo)
                archivo.save(ruta)
                imagen = f"/static/img/productos/{nombre_archivo}"
        elif request.form.get("imagen"):
            imagen = request.form.get("imagen")
        
        conn.execute("""
            INSERT INTO productos (nombre, precio, imagen, categoria_id, stock, stock_minimo, activo)
            VALUES (?, ?, ?, ?, ?, ?, 1)
        """, (nombre, precio, imagen, categoria_id, stock, stock_minimo))
        conn.commit()
        conn.close()
        flash("Producto agregado correctamente", "success")
        return redirect(url_for("admin_panel"))
    conn.close()
    return render_template("admin_producto.html", categorias=categorias, producto=None)

@app.route("/admin/producto/editar/<int:id>", methods=["GET", "POST"])
@login_required
def admin_editar_producto(id):
    if current_user.rol != "admin":
        return redirect(url_for("index"))
    conn = get_db()
    producto = conn.execute("SELECT * FROM productos WHERE id = ?", (id,)).fetchone()
    categorias = conn.execute("SELECT * FROM categorias").fetchall()
    if request.method == "POST":
        nombre = request.form.get("nombre")
        precio = float(request.form.get("precio", 0))
        categoria_id = int(request.form.get("categoria_id"))
        stock = int(request.form.get("stock", 0))
        stock_minimo = int(request.form.get("stock_minimo", 5))
        activo = 1 if request.form.get("activo") else 0
        
        # Mantener imagen actual si no se sube una nueva
        imagen = producto["imagen"]
        if "imagen_archivo" in request.files:
            archivo = request.files["imagen_archivo"]
            if archivo and archivo.filename and allowed_file(archivo.filename):
                ext = archivo.filename.rsplit(".", 1)[1].lower()
                nombre_archivo = f"{uuid.uuid4().hex}.{ext}"
                ruta = os.path.join(app.config["UPLOAD_FOLDER"], nombre_archivo)
                archivo.save(ruta)
                imagen = f"/static/img/productos/{nombre_archivo}"
        elif request.form.get("imagen"):
            imagen = request.form.get("imagen")
        
        conn.execute("""
            UPDATE productos SET nombre=?, precio=?, imagen=?, categoria_id=?, stock=?, stock_minimo=?, activo=?
            WHERE id=?
        """, (nombre, precio, imagen, categoria_id, stock, stock_minimo, activo, id))
        conn.commit()
        conn.close()
        flash("Producto actualizado", "success")
        return redirect(url_for("admin_panel"))
    conn.close()
    return render_template("admin_producto.html", categorias=categorias, producto=producto)

@app.route("/admin/stock/<int:id>", methods=["POST"])
@login_required
def admin_ajustar_stock(id):
    if current_user.rol != "admin":
        return redirect(url_for("index"))
    cantidad = int(request.form.get("cantidad", 0))
    conn = get_db()
    conn.execute("UPDATE productos SET stock = stock + ? WHERE id = ?", (cantidad, id))
    conn.commit()
    conn.close()
    flash("Stock actualizado", "success")
    return redirect(url_for("admin_panel"))

# -----------------------------
# Dashboard Contable
# -----------------------------
@app.route("/contable")
@login_required
def dashboard_contable():
    if current_user.rol not in ["contador", "admin"]:
        return redirect(url_for("index"))
    conn = get_db()
    
    hoy = datetime.now().strftime("%Y-%m-%d")
    ventas_hoy = conn.execute(
        "SELECT COALESCE(SUM(total), 0) as total, COUNT(*) as cantidad FROM pedidos WHERE fecha LIKE ?",
        (hoy + "%",)
    ).fetchone()
    
    gastos_hoy = conn.execute(
        "SELECT COALESCE(SUM(monto), 0) as total FROM gastos WHERE fecha LIKE ?",
        (hoy + "%",)
    ).fetchone()
    
    # Últimos pedidos CON productos y categorías
    ultimos_pedidos = conn.execute("""
        SELECT p.*,
               GROUP_CONCAT(pr.nombre || ' x' || d.cantidad, ', ') as productos,
               GROUP_CONCAT(DISTINCT c.nombre, ', ') as categorias
        FROM pedidos p
        LEFT JOIN detalle_pedidos d ON p.id = d.pedido_id
        LEFT JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        GROUP BY p.id
        ORDER BY p.id DESC
        LIMIT 15
    """).fetchall()
    
    ultimos_gastos = conn.execute(
        "SELECT * FROM gastos ORDER BY id DESC LIMIT 10"
    ).fetchall()
    
    stock_bajo = conn.execute(
        "SELECT * FROM productos WHERE stock <= stock_minimo AND activo = 1"
    ).fetchall()
    
    # Top productos (para gráfico)
    top_productos = conn.execute("""
        SELECT pr.nombre, c.nombre as categoria, SUM(d.cantidad) as total_vendido
        FROM detalle_pedidos d
        JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        GROUP BY pr.id
        ORDER BY total_vendido DESC
        LIMIT 8
    """).fetchall()
    
    conn.close()
    utilidad = ventas_hoy["total"] - gastos_hoy["total"]
    
    return render_template("contable.html",
        ventas_hoy=ventas_hoy,
        gastos_hoy=gastos_hoy,
        utilidad=utilidad,
        ultimos_pedidos=ultimos_pedidos,
        ultimos_gastos=ultimos_gastos,
        stock_bajo=stock_bajo,
        top_productos=top_productos
    )

@app.route("/contable/gasto", methods=["GET", "POST"])
@login_required
def registrar_gasto():
    if current_user.rol not in ["contador", "admin"]:
        return redirect(url_for("index"))
    if request.method == "POST":
        descripcion = request.form.get("descripcion")
        monto = float(request.form.get("monto", 0))
        categoria = request.form.get("categoria")
        conn = get_db()
        conn.execute(
            "INSERT INTO gastos (descripcion, monto, fecha, categoria) VALUES (?, ?, ?, ?)",
            (descripcion, monto, datetime.now().strftime("%Y-%m-%d %H:%M"), categoria)
        )
        conn.commit()
        conn.close()
        flash("Gasto registrado", "success")
        return redirect(url_for("dashboard_contable"))
    return render_template("registrar_gasto.html")

@app.route("/contable/reportes", methods=["GET", "POST"])
@login_required
def reportes_contable():
    """Reportes por rango de fechas: semanal, mensual o personalizado"""
    if current_user.rol not in ["contador", "admin"]:
        return redirect(url_for("index"))
    
    hoy = datetime.now().date()
    periodo = request.values.get("periodo", "")
    
    # Periodos rápidos
    if periodo == "semana":
        fecha_desde = (hoy - timedelta(days=7)).strftime("%Y-%m-%d")
        fecha_hasta = hoy.strftime("%Y-%m-%d")
    elif periodo == "mes":
        fecha_desde = hoy.replace(day=1).strftime("%Y-%m-%d")
        fecha_hasta = hoy.strftime("%Y-%m-%d")
    else:
        # Calendario personalizado o valores por defecto
        fecha_desde = request.values.get("fecha_desde") or request.values.get("desde") or (hoy - timedelta(days=7)).strftime("%Y-%m-%d")
        fecha_hasta = request.values.get("fecha_hasta") or request.values.get("hasta") or hoy.strftime("%Y-%m-%d")
    
    conn = get_db()
    
    ingresos = conn.execute("""
        SELECT COALESCE(SUM(total), 0) as total, COUNT(*) as cantidad
        FROM pedidos WHERE date(fecha) BETWEEN ? AND ?
    """, (fecha_desde, fecha_hasta)).fetchone()
    
    egresos = conn.execute("""
        SELECT COALESCE(SUM(monto), 0) as total, COUNT(*) as cantidad
        FROM gastos WHERE date(fecha) BETWEEN ? AND ?
    """, (fecha_desde, fecha_hasta)).fetchone()
    
    pedidos = conn.execute("""
        SELECT p.*,
               GROUP_CONCAT(pr.nombre || ' x' || d.cantidad, ', ') as productos,
               GROUP_CONCAT(DISTINCT c.nombre, ', ') as categorias
        FROM pedidos p
        LEFT JOIN detalle_pedidos d ON p.id = d.pedido_id
        LEFT JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        WHERE date(p.fecha) BETWEEN ? AND ?
        GROUP BY p.id
        ORDER BY p.fecha DESC
    """, (fecha_desde, fecha_hasta)).fetchall()
    
    gastos_lista = conn.execute("""
        SELECT * FROM gastos WHERE date(fecha) BETWEEN ? AND ? ORDER BY fecha DESC
    """, (fecha_desde, fecha_hasta)).fetchall()
    
    top_productos = conn.execute("""
        SELECT pr.nombre, c.nombre as categoria, SUM(d.cantidad) as total_vendido,
               SUM(d.cantidad * d.precio_unitario) as monto
        FROM detalle_pedidos d
        JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        JOIN pedidos p ON d.pedido_id = p.id
        WHERE date(p.fecha) BETWEEN ? AND ?
        GROUP BY pr.id
        ORDER BY total_vendido DESC
        LIMIT 10
    """, (fecha_desde, fecha_hasta)).fetchall()
    
    por_categoria = conn.execute("""
        SELECT c.nombre as categoria, SUM(d.cantidad) as unidades,
               SUM(d.cantidad * d.precio_unitario) as monto
        FROM detalle_pedidos d
        JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        JOIN pedidos p ON d.pedido_id = p.id
        WHERE date(p.fecha) BETWEEN ? AND ?
        GROUP BY c.id
        ORDER BY monto DESC
    """, (fecha_desde, fecha_hasta)).fetchall()
    
    conn.close()
    
    utilidad = ingresos["total"] - egresos["total"]
    
    return render_template("reportes.html",
        fecha_desde=fecha_desde,
        fecha_hasta=fecha_hasta,
        periodo=periodo,
        ingresos=ingresos,
        egresos=egresos,
        utilidad=utilidad,
        pedidos=pedidos,
        gastos_lista=gastos_lista,
        top_productos=top_productos,
        por_categoria=por_categoria
    )

@app.route("/contable/reportes/excel")
@login_required
def reportes_excel():
    """Descargar reporte en Excel (CSV compatible con Excel)"""
    if current_user.rol not in ["contador", "admin"]:
        return redirect(url_for("index"))
    
    fecha_desde = request.args.get("desde", (datetime.now().date() - timedelta(days=7)).strftime("%Y-%m-%d"))
    fecha_hasta = request.args.get("hasta", datetime.now().date().strftime("%Y-%m-%d"))
    
    conn = get_db()
    
    output = io.StringIO()
    writer = csv.writer(output, delimiter=';')
    
    writer.writerow(["RECARGA VELOZ - REPORTE CONTABLE"])
    writer.writerow(["Periodo", fecha_desde, "a", fecha_hasta])
    writer.writerow([])
    
    ingresos = conn.execute(
        "SELECT COALESCE(SUM(total),0), COUNT(*) FROM pedidos WHERE date(fecha) BETWEEN ? AND ?",
        (fecha_desde, fecha_hasta)
    ).fetchone()
    egresos = conn.execute(
        "SELECT COALESCE(SUM(monto),0), COUNT(*) FROM gastos WHERE date(fecha) BETWEEN ? AND ?",
        (fecha_desde, fecha_hasta)
    ).fetchone()
    
    writer.writerow(["RESUMEN"])
    writer.writerow(["Ingresos (ventas)", f"{ingresos[0]:.2f}"])
    writer.writerow(["Cantidad de pedidos", ingresos[1]])
    writer.writerow(["Egresos (gastos)", f"{egresos[0]:.2f}"])
    writer.writerow(["Cantidad de gastos", egresos[1]])
    writer.writerow(["Utilidad", f"{ingresos[0]-egresos[0]:.2f}"])
    writer.writerow([])
    
    writer.writerow(["PEDIDOS / INGRESOS"])
    writer.writerow(["Orden", "Fecha", "Total", "Estado", "Productos", "Categorias"])
    for p in conn.execute("""
        SELECT p.numero_orden, p.fecha, p.total, p.estado,
               GROUP_CONCAT(pr.nombre || ' x' || d.cantidad, ', '),
               GROUP_CONCAT(DISTINCT c.nombre, ', ')
        FROM pedidos p
        LEFT JOIN detalle_pedidos d ON p.id = d.pedido_id
        LEFT JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        WHERE date(p.fecha) BETWEEN ? AND ?
        GROUP BY p.id ORDER BY p.fecha
    """, (fecha_desde, fecha_hasta)):
        writer.writerow(list(p))
    
    writer.writerow([])
    writer.writerow(["GASTOS / EGRESOS"])
    writer.writerow(["Descripcion", "Categoria", "Monto", "Fecha"])
    for g in conn.execute(
        "SELECT descripcion, categoria, monto, fecha FROM gastos WHERE date(fecha) BETWEEN ? AND ? ORDER BY fecha",
        (fecha_desde, fecha_hasta)
    ):
        writer.writerow(list(g))
    
    writer.writerow([])
    writer.writerow(["PRODUCTOS MAS VENDIDOS"])
    writer.writerow(["Producto", "Categoria", "Unidades", "Monto"])
    for t in conn.execute("""
        SELECT pr.nombre, c.nombre, SUM(d.cantidad), SUM(d.cantidad * d.precio_unitario)
        FROM detalle_pedidos d
        JOIN productos pr ON d.producto_id = pr.id
        LEFT JOIN categorias c ON pr.categoria_id = c.id
        JOIN pedidos p ON d.pedido_id = p.id
        WHERE date(p.fecha) BETWEEN ? AND ?
        GROUP BY pr.id ORDER BY SUM(d.cantidad) DESC
    """, (fecha_desde, fecha_hasta)):
        writer.writerow(list(t))
    
    conn.close()
    
    output.seek(0)
    # BOM para que Excel abra bien los acentos
    data = "﻿" + output.getvalue()
    resp = make_response(data.encode("utf-8"))
    resp.headers["Content-Type"] = "text/csv; charset=utf-8"
    resp.headers["Content-Disposition"] = f"attachment; filename=reporte_recarga_veloz_{fecha_desde}_{fecha_hasta}.csv"
    return resp

# -----------------------------

@app.route("/sw.js")
def service_worker():
    return app.send_static_file("js/sw.js")

@app.route("/manifest.json")
def manifest():
    return app.send_static_file("manifest.json")

# Inicializar BD al arrancar (local y en la nube)
with app.app_context():
    init_db()

if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5000))
    app.run(host="0.0.0.0", port=port, debug=False)
