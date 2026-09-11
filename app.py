from flask import Flask, jsonify, request, send_from_directory, session, send_file
from flask_cors import CORS
from database import get_conn, init_db
from auth import verify_user, create_user, init_default_admin, login_required, require_role
from excel_io import export_riai_excel, export_proveedores_excel, import_riai_excel, import_proveedores_excel
from pdf_generator import generate_riai_pdf
from storage_r2 import upload_base64_image
import os

app = Flask(__name__, static_folder=os.path.join(os.path.dirname(__file__), "static"))
app.secret_key = os.environ.get("SECRET_KEY", "cnh-riai-secret-2026")
app.config['MAX_CONTENT_LENGTH'] = 50 * 1024 * 1024
CORS(app, supports_credentials=True)

with app.app_context():
    init_db()
    init_default_admin()

# ── STATIC ────────────────────────────────────────────────────────────────
@app.route("/")
def index():
    return send_from_directory("static", "index.html")

@app.route("/login.html")
def login_page():
    return send_from_directory("static", "login.html")

# ── AUTH ──────────────────────────────────────────────────────────────────
@app.route("/api/login", methods=["POST"])
def login():
    d = request.json
    user = verify_user(d.get("username", ""), d.get("password", ""))
    if user:
        session["user_id"] = user["id"]
        session["username"] = user["username"]
        session["rol"] = user["rol"]
        session.permanent = True
        return jsonify({"status": "ok", "username": user["username"], "rol": user["rol"]})
    return jsonify({"error": "Usuario o contraseña incorrectos"}), 401

@app.route("/api/logout", methods=["POST"])
@login_required
def logout():
    session.clear()
    return jsonify({"status": "ok"})

@app.route("/api/me")
def me():
    if "user_id" in session:
        return jsonify({"username": session["username"], "rol": session["rol"]})
    return jsonify({"error": "No autenticado"}), 401

# ── USUARIOS ──────────────────────────────────────────────────────────────
@app.route("/api/usuarios", methods=["GET"])
@require_role("admin")
def list_usuarios():
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, username, rol, creado_en FROM usuarios")
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/usuarios", methods=["POST"])
@require_role("admin")
def add_usuario():
    d = request.json
    ok = create_user(d.get("username"), d.get("password"), d.get("rol", "operador"))
    if ok:
        return jsonify({"status": "ok"}), 201
    return jsonify({"error": "No se pudo crear (¿usuario duplicado?)"}), 400

@app.route("/api/usuarios/<int:id>", methods=["DELETE"])
@require_role("admin")
def delete_usuario(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM usuarios WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/usuarios/cambiar-password", methods=["POST"])
@login_required
def cambiar_password():
    d = request.json
    nueva = d.get("password", "")
    if len(nueva) < 6:
        return jsonify({"error": "La contraseña debe tener al menos 6 caracteres"}), 400
    from werkzeug.security import generate_password_hash
    conn = get_conn()
    c = conn.cursor()
    c.execute("UPDATE usuarios SET password_hash=%s WHERE id=%s",
              (generate_password_hash(nueva), session["user_id"]))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ── PROVEEDORES ───────────────────────────────────────────────────────────
@app.route("/api/proveedores")
@login_required
def get_proveedores():
    q = request.args.get("q", "").lower()
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM proveedores WHERE LOWER(nombre) LIKE %s OR codigo LIKE %s", (f"%{q}%", f"%{q}%"))
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

# ── PIEZAS ────────────────────────────────────────────────────────────────
@app.route("/api/piezas/<numero>")
@login_required
def get_pieza(numero):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM piezas WHERE numero_pieza=%s", (numero,))
    row = c.fetchone()
    conn.close()
    return jsonify(dict(row)) if row else (jsonify({}), 200)

# ── RIAI ──────────────────────────────────────────────────────────────────
RIAI_FIELDS = [
    "fecha","idioma","unidad_long","unidad_peso",
    "proveedor_codigo","proveedor_nombre","proveedor_direccion",
    "proveedor_contacto","proveedor_email","proveedor_telefono",
    "numero_pieza","descripcion","largo","ancho","alto","peso","moq","proyecto",
    "emb_identico","colocacion",
    "p1_tipo","p1_retornable","p1_material","p1_descripcion",
    "p1_largo","p1_ancho","p1_alto","p1_peso_emb","p1_capacidad","p1_peso_bruto",
    "p1_cajas_capa","p1_capas",
    "p2_tipo","p2_retornable","p2_material","p2_descripcion",
    "p2_largo","p2_ancho","p2_alto","p2_peso_emb","p2_capacidad","p2_peso_bruto",
    "accesorios","img_caja","img_abierta","img_embalada","img_paletizado",
    "ap_elaborado_nombre","ap_elaborado_fecha",
    "ap_revisado_nombre","ap_revisado_fecha",
    "ap_aprobado_nombre","ap_aprobado_fecha",
    "estado",
]

@app.route("/api/riai")
@login_required
def list_riai():
    q = request.args.get("q", "").lower()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT id, fecha, numero_pieza, descripcion,
               proveedor_nombre, estado, creado_en,
               p1_capacidad, p2_capacidad, emb_identico
        FROM riai
        WHERE LOWER(numero_pieza) LIKE %s
           OR LOWER(descripcion)  LIKE %s
           OR LOWER(proveedor_nombre) LIKE %s
        ORDER BY id DESC
    """, (f"%{q}%", f"%{q}%", f"%{q}%"))
    rows = c.fetchall()
    conn.close()
    return jsonify([dict(r) for r in rows])

@app.route("/api/riai/<int:id>")
@login_required
def get_riai(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM riai WHERE id=%s", (id,))
    row = c.fetchone()
    conn.close()
    return jsonify(dict(row)) if row else ("Not found", 404)

def _process_riai_images(d):
    """Sube a R2 las imágenes que vengan en base64 y reemplaza el campo con la URL."""
    for campo, prefix in [("img_caja","riai/caja"),("img_abierta","riai/abierta"),
                            ("img_embalada","riai/embalada"),("img_paletizado","riai/paletizado")]:
        val = d.get(campo)
        if val and val.startswith("data:"):
            url = upload_base64_image(val, prefix=prefix)
            d[campo] = url
    return d

@app.route("/api/riai", methods=["POST"])
@require_role("admin", "operador")
def create_riai():
    d = request.json
    d = _process_riai_images(d)
    values = [d.get(f) for f in RIAI_FIELDS]
    cols = ", ".join(RIAI_FIELDS)
    placeholders = ", ".join(["%s"] * len(RIAI_FIELDS))
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"INSERT INTO riai ({cols}) VALUES ({placeholders}) RETURNING id", values)
    new_id = c.fetchone()["id"]
    conn.commit()
    conn.close()
    return jsonify({"id": new_id, "status": "ok"}), 201

@app.route("/api/riai/<int:id>", methods=["PUT"])
@require_role("admin", "operador")
def update_riai(id):
    d = request.json
    d = _process_riai_images(d)
    set_clause = ", ".join([f"{f}=%s" for f in RIAI_FIELDS])
    values = [d.get(f) for f in RIAI_FIELDS] + [id]
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"""
        UPDATE riai SET {set_clause}, actualizado_en = to_char(now(), 'YYYY-MM-DD HH24:MI:SS')
        WHERE id=%s
    """, values)
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/riai/<int:id>", methods=["DELETE"])
@require_role("admin")
def delete_riai(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM riai WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ── PDF ───────────────────────────────────────────────────────────────────
@app.route("/api/riai/<int:id>/pdf")
@login_required
def riai_pdf(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM riai WHERE id=%s", (id,))
    row = c.fetchone()
    conn.close()
    if not row:
        return jsonify({"error": "RIAI no encontrado"}), 404
    d = dict(row)
    lang = request.args.get("lang", d.get("idioma") or "es")
    buf = generate_riai_pdf(d, lang=lang)
    filename = f"RIAI_{d.get('numero_pieza','sin_pn')}.pdf"
    return send_file(buf, as_attachment=True, download_name=filename, mimetype="application/pdf")

# ── EXCEL ─────────────────────────────────────────────────────────────────
@app.route("/api/export/riai")
@login_required
def export_riai():
    buf = export_riai_excel()
    return send_file(buf, as_attachment=True, download_name="RIAIs_export.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/api/export/proveedores")
@login_required
def export_proveedores():
    buf = export_proveedores_excel()
    return send_file(buf, as_attachment=True, download_name="Proveedores_export.xlsx",
                     mimetype="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet")

@app.route("/api/import/riai", methods=["POST"])
@require_role("admin", "operador")
def import_riai():
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files["file"]
    inserted, errors = import_riai_excel(file.stream)
    return jsonify({"status": "ok", "inserted": inserted, "errors": errors})

@app.route("/api/import/proveedores", methods=["POST"])
@require_role("admin", "operador")
def import_proveedores():
    if "file" not in request.files:
        return jsonify({"error": "No se envió ningún archivo"}), 400
    file = request.files["file"]
    inserted, errors = import_proveedores_excel(file.stream)
    return jsonify({"status": "ok", "inserted": inserted, "errors": errors})

@app.route("/api/export/imagenes")
@login_required
def export_imagenes():
    """Con R2, las imágenes ya son URLs — este endpoint arma un listado en vez de un ZIP con binarios."""
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT id, numero_pieza, img_caja, img_abierta, img_embalada, img_paletizado FROM riai")
    riai_rows = c.fetchall()
    c.execute("""SELECT cl.id, cl.numero_pieza, cl.img_pieza, c.img_embalaje
                 FROM control_lineas cl JOIN control c ON cl.control_id = c.id""")
    control_rows = c.fetchall()
    conn.close()

    lines = ["PN,Tipo,Campo,URL"]
    for r in riai_rows:
        r = dict(r)
        for campo in ["img_caja","img_abierta","img_embalada","img_paletizado"]:
            if r.get(campo):
                lines.append(f'{r.get("numero_pieza","")},RIAI,{campo},{r[campo]}')
    for r in control_rows:
        r = dict(r)
        if r.get("img_pieza"):
            lines.append(f'{r.get("numero_pieza","")},Control,img_pieza,{r["img_pieza"]}')
        if r.get("img_embalaje"):
            lines.append(f'{r.get("numero_pieza","")},Control,img_embalaje,{r["img_embalaje"]}')

    from io import BytesIO
    buf = BytesIO("\n".join(lines).encode("utf-8"))
    return send_file(buf, as_attachment=True, download_name="urls_imagenes.csv", mimetype="text/csv")

# ── CONTROL ───────────────────────────────────────────────────────────────
CONTROL_FIELDS = [
    "fecha","proveedor_nombre","proveedor_codigo","emb_identico",
    "emb_tipo","emb_tipo_otro","emb_largo","emb_ancho","emb_alto",
    "img_cerrada","img_abierta","img_etiqueta","saturacion","notas",
]
LINEA_FIELDS = ["numero_pieza","cantidad","tipo","largo","ancho","alto","img_foto1","img_foto2","saturacion","orden"]

@app.route("/api/control")
@login_required
def list_control():
    q = request.args.get("q", "").lower()
    conn = get_conn()
    c = conn.cursor()
    c.execute("""
        SELECT DISTINCT c.id, c.fecha, c.proveedor_nombre, c.emb_tipo,
               c.saturacion, c.creado_en
        FROM control c
        LEFT JOIN control_lineas cl ON cl.control_id = c.id
        WHERE LOWER(c.proveedor_nombre) LIKE %s
           OR LOWER(cl.numero_pieza) LIKE %s
        ORDER BY c.id DESC
    """, (f"%{q}%", f"%{q}%"))
    rows = [dict(r) for r in c.fetchall()]
    for r in rows:
        c.execute("SELECT numero_pieza, cantidad FROM control_lineas WHERE control_id=%s ORDER BY orden", (r["id"],))
        r["lineas"] = [dict(x) for x in c.fetchall()]
    conn.close()
    return jsonify(rows)

@app.route("/api/control/<int:id>")
@login_required
def get_control(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("SELECT * FROM control WHERE id=%s", (id,))
    row = c.fetchone()
    if not row:
        conn.close()
        return ("Not found", 404)
    d = dict(row)
    c.execute("SELECT * FROM control_lineas WHERE control_id=%s ORDER BY orden", (id,))
    d["lineas"] = [dict(x) for x in c.fetchall()]
    conn.close()
    return jsonify(d)

def _process_control_images(d):
    for campo, prefix in [("img_cerrada","control/cerrada"),("img_abierta","control/abierta"),("img_etiqueta","control/etiqueta")]:
        val = d.get(campo)
        if val and val.startswith("data:"):
            d[campo] = upload_base64_image(val, prefix=prefix)
    return d

def _process_linea_images(l):
    for campo, prefix in [("img_foto1","control/pieza1"),("img_foto2","control/pieza2")]:
        val = l.get(campo)
        if val and val.startswith("data:"):
            l[campo] = upload_base64_image(val, prefix=prefix)
    return l

@app.route("/api/control", methods=["POST"])
@require_role("admin", "operador")
def create_control():
    d = request.json
    lineas = d.get("lineas", [])
    d = _process_control_images(d)

    values = [d.get(f) for f in CONTROL_FIELDS]
    cols = ", ".join(CONTROL_FIELDS)
    placeholders = ", ".join(["%s"] * len(CONTROL_FIELDS))
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"INSERT INTO control ({cols}) VALUES ({placeholders}) RETURNING id", values)
    control_id = c.fetchone()["id"]

    for i, linea in enumerate(lineas):
        linea = _process_linea_images(linea)
        linea["orden"] = i
        lvalues = [linea.get(f) for f in LINEA_FIELDS] + [control_id]
        lcols = ", ".join(LINEA_FIELDS) + ", control_id"
        lplaceholders = ", ".join(["%s"] * (len(LINEA_FIELDS) + 1))
        c.execute(f"INSERT INTO control_lineas ({lcols}) VALUES ({lplaceholders})", lvalues)

    conn.commit()
    conn.close()
    return jsonify({"id": control_id, "status": "ok"}), 201

@app.route("/api/control/<int:id>", methods=["PUT"])
@require_role("admin", "operador")
def update_control(id):
    d = request.json
    lineas = d.get("lineas", [])
    d = _process_control_images(d)

    set_clause = ", ".join([f"{f}=%s" for f in CONTROL_FIELDS])
    values = [d.get(f) for f in CONTROL_FIELDS] + [id]
    conn = get_conn()
    c = conn.cursor()
    c.execute(f"UPDATE control SET {set_clause} WHERE id=%s", values)

    c.execute("DELETE FROM control_lineas WHERE control_id=%s", (id,))
    for i, linea in enumerate(lineas):
        linea = _process_linea_images(linea)
        linea["orden"] = i
        lvalues = [linea.get(f) for f in LINEA_FIELDS] + [id]
        lcols = ", ".join(LINEA_FIELDS) + ", control_id"
        lplaceholders = ", ".join(["%s"] * (len(LINEA_FIELDS) + 1))
        c.execute(f"INSERT INTO control_lineas ({lcols}) VALUES ({lplaceholders})", lvalues)

    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

@app.route("/api/control/<int:id>", methods=["DELETE"])
@require_role("admin")
def delete_control(id):
    conn = get_conn()
    c = conn.cursor()
    c.execute("DELETE FROM control WHERE id=%s", (id,))
    conn.commit()
    conn.close()
    return jsonify({"status": "ok"})

# ── ANÁLISIS DE SATURACIÓN (placeholder simple, sin IA pesada) ──────────
@app.route("/api/analizar-saturacion", methods=["POST"])
@login_required
def analizar_saturacion():
    return jsonify({"error": "Análisis de saturación con IA deshabilitado temporalmente"}), 501

# ── RUN ───────────────────────────────────────────────────────────────────
if __name__ == "__main__":
    print("✅ Base de datos lista")
    print("🚀 Servidor corriendo en http://localhost:5000")
    app.run(debug=True, host="0.0.0.0", port=5000)
