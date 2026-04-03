import os, json, base64, re, requests
from datetime import datetime
from flask import Flask, render_template, request, redirect, url_for, session, jsonify, flash
from flask_sqlalchemy import SQLAlchemy
from werkzeug.security import generate_password_hash, check_password_hash
from werkzeug.utils import secure_filename
from functools import wraps
import pytesseract
from PIL import Image
import fitz  # PyMuPDF

app = Flask(__name__)
app.secret_key = "docextract-secret-2024"
app.config["SQLALCHEMY_DATABASE_URI"] = "sqlite:///docextract.db"
app.config["SQLALCHEMY_TRACK_MODIFICATIONS"] = False
app.config["UPLOAD_FOLDER"] = "uploads"
app.config["MAX_CONTENT_LENGTH"] = 10 * 1024 * 1024  # 10MB
ALLOWED_EXTENSIONS = {"pdf", "png", "jpg", "jpeg", "webp"}

OLLAMA_URL = "http://localhost:11434/api/generate"
OLLAMA_MODEL = "llama3"

db = SQLAlchemy(app)

# ─── MODELS ────────────────────────────────────────────────────────────────────

class User(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    username = db.Column(db.String(80), unique=True, nullable=False)
    email = db.Column(db.String(120), unique=True, nullable=False)
    password_hash = db.Column(db.String(256), nullable=False)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)
    extractions = db.relationship("Extraction", backref="user", lazy=True, cascade="all, delete-orphan")

class Extraction(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.Integer, db.ForeignKey("user.id"), nullable=False)
    filename = db.Column(db.String(255))
    doc_type = db.Column(db.String(50))
    result_json = db.Column(db.Text)
    raw_text = db.Column(db.Text)
    created_at = db.Column(db.DateTime, default=datetime.utcnow)

with app.app_context():
    db.create_all()

# ─── HELPERS ───────────────────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if "user_id" not in session:
            return redirect(url_for("login"))
        return f(*args, **kwargs)
    return decorated

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

def extract_text_from_file(filepath):
    ext = filepath.rsplit(".", 1)[1].lower()
    text = ""
    if ext == "pdf":
        doc = fitz.open(filepath)
        for page in doc:
            text += page.get_text()
        doc.close()
        if len(text.strip()) < 50:
            # Fallback: render PDF pages as images and OCR
            doc = fitz.open(filepath)
            for page in doc:
                pix = page.get_pixmap(dpi=200)
                img_path = filepath + f"_page{page.number}.png"
                pix.save(img_path)
                text += pytesseract.image_to_string(Image.open(img_path), lang="spa+eng")
                os.remove(img_path)
            doc.close()
    else:
        img = Image.open(filepath)
        text = pytesseract.image_to_string(img, lang="spa+eng")
    return text.strip()

def ollama_extract(text, doc_type, custom_fields=""):
    schemas = {
        "factura": "Número de factura, Fecha, Emisor, NIF/CIF emisor, Cliente, NIF/CIF cliente, Dirección cliente, Concepto/descripción, Base imponible, IVA (%), IVA (importe), Total, Forma de pago, Número de cuenta/IBAN",
        "contrato": "Partes contratantes, Fecha de firma, Fecha de inicio, Fecha de fin, Objeto del contrato, Importe/precio, Duración, Cláusulas principales, Obligaciones, Penalizaciones, Jurisdicción",
        "albaran": "Número de albarán, Fecha, Proveedor, NIF proveedor, Destinatario, Dirección de entrega, Artículos/productos, Cantidades, Unidades, Precio unitario, Total, Transportista, Matrícula",
        "dni": "Nombre, Primer apellido, Segundo apellido, DNI/NIE, Fecha de nacimiento, Lugar de nacimiento, Fecha de expedición, Fecha de expiración, Sexo, Nacionalidad",
        "presupuesto": "Número de presupuesto, Fecha, Válido hasta, Empresa emisora, NIF emisor, Cliente, NIF cliente, Partidas/conceptos, Cantidades, Precios unitarios, Subtotal, IVA, Descuento, Total, Condiciones de pago",
        "ticket": "Establecimiento, NIF establecimiento, Dirección, Fecha, Hora, Artículos comprados, Cantidades, Precios, Subtotal, IVA, Total, Forma de pago, Número de ticket",
        "nomina": "Empresa, NIF empresa, Trabajador, DNI trabajador, Número SS trabajador, Categoría profesional, Mes/periodo, Salario bruto, Retenciones IRPF, Cotizaciones SS, Salario neto, Complementos, Horas extras",
        "libre": custom_fields or "todos los datos relevantes que encuentres en el documento",
    }
    fields = schemas.get(doc_type, schemas["libre"])
    prompt = f"""Eres un sistema experto en extracción de datos de documentos empresariales españoles.

Analiza el siguiente texto extraído de un documento y extrae exactamente estos campos:
{fields}

TEXTO DEL DOCUMENTO:
\"\"\"
{text[:4000]}
\"\"\"

INSTRUCCIONES CRÍTICAS:
- Responde ÚNICAMENTE con un objeto JSON válido, sin texto adicional, sin explicaciones, sin bloques de código.
- Las claves del JSON deben ser exactamente los nombres de los campos solicitados.
- Si un campo no aparece en el documento, usa null como valor.
- Para importes, incluye el símbolo de moneda si está presente.
- No inventes datos que no estén en el texto.
- El JSON debe estar bien formado y ser parseable directamente.

JSON:"""

    try:
        resp = requests.post(OLLAMA_URL, json={
            "model": OLLAMA_MODEL,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": 0.1, "num_predict": 1500}
        }, timeout=120)
        resp.raise_for_status()
        raw = resp.json().get("response", "")
        # Extract JSON from response
        match = re.search(r'\{[\s\S]*\}', raw)
        if match:
            return json.loads(match.group())
        return {"error": "No se pudo parsear la respuesta de la IA", "raw": raw[:500]}
    except requests.exceptions.ConnectionError:
        return {"error": "No se puede conectar con Ollama. Asegúrate de que está corriendo en localhost:11434"}
    except Exception as e:
        return {"error": str(e)}

# ─── AUTH ROUTES ───────────────────────────────────────────────────────────────

@app.route("/")
def index():
    if "user_id" in session:
        return redirect(url_for("dashboard"))
    return redirect(url_for("login"))

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = User.query.filter_by(email=email).first()
        if user and check_password_hash(user.password_hash, password):
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard"))
        flash("Email o contraseña incorrectos", "error")
    return render_template("auth.html", mode="login")

@app.route("/register", methods=["GET", "POST"])
def register():
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        confirm = request.form.get("confirm", "")
        if len(username) < 3:
            flash("El nombre de usuario debe tener al menos 3 caracteres", "error")
        elif len(password) < 6:
            flash("La contraseña debe tener al menos 6 caracteres", "error")
        elif password != confirm:
            flash("Las contraseñas no coinciden", "error")
        elif User.query.filter_by(email=email).first():
            flash("Este email ya está registrado", "error")
        elif User.query.filter_by(username=username).first():
            flash("Este nombre de usuario ya existe", "error")
        else:
            user = User(username=username, email=email, password_hash=generate_password_hash(password))
            db.session.add(user)
            db.session.commit()
            session["user_id"] = user.id
            session["username"] = user.username
            return redirect(url_for("dashboard"))
    return render_template("auth.html", mode="register")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("login"))

# ─── APP ROUTES ────────────────────────────────────────────────────────────────

@app.route("/dashboard")
@login_required
def dashboard():
    user = User.query.get(session["user_id"])
    extractions = Extraction.query.filter_by(user_id=user.id).order_by(Extraction.created_at.desc()).all()
    total = len(extractions)
    doc_types = {}
    for e in extractions:
        doc_types[e.doc_type] = doc_types.get(e.doc_type, 0) + 1
    return render_template("dashboard.html", user=user, extractions=extractions, total=total, doc_types=doc_types)

@app.route("/extract", methods=["POST"])
@login_required
def extract():
    if "file" not in request.files:
        return jsonify({"error": "No se recibió ningún archivo"}), 400
    file = request.files["file"]
    doc_type = request.form.get("doc_type", "libre")
    custom_fields = request.form.get("custom_fields", "")
    if not file or not allowed_file(file.filename):
        return jsonify({"error": "Formato no permitido. Usa PDF, JPG, PNG o WebP"}), 400
    filename = secure_filename(file.filename)
    ts = datetime.now().strftime("%Y%m%d_%H%M%S_")
    safe_name = ts + filename
    filepath = os.path.join(app.config["UPLOAD_FOLDER"], safe_name)
    file.save(filepath)
    try:
        raw_text = extract_text_from_file(filepath)
        if len(raw_text.strip()) < 10:
            return jsonify({"error": "No se pudo extraer texto del documento. Comprueba que no esté en blanco o sea ilegible"}), 400
        result = ollama_extract(raw_text, doc_type, custom_fields)
        extraction = Extraction(
            user_id=session["user_id"],
            filename=filename,
            doc_type=doc_type,
            result_json=json.dumps(result, ensure_ascii=False),
            raw_text=raw_text[:5000]
        )
        db.session.add(extraction)
        db.session.commit()
        return jsonify({"ok": True, "data": result, "id": extraction.id, "raw_preview": raw_text[:300]})
    except Exception as e:
        return jsonify({"error": str(e)}), 500
    finally:
        if os.path.exists(filepath):
            os.remove(filepath)

@app.route("/extraction/<int:extraction_id>")
@login_required
def view_extraction(extraction_id):
    extraction = Extraction.query.filter_by(id=extraction_id, user_id=session["user_id"]).first_or_404()
    data = json.loads(extraction.result_json)
    return render_template("detail.html", extraction=extraction, data=data)

@app.route("/extraction/<int:extraction_id>/delete", methods=["POST"])
@login_required
def delete_extraction(extraction_id):
    extraction = Extraction.query.filter_by(id=extraction_id, user_id=session["user_id"]).first_or_404()
    db.session.delete(extraction)
    db.session.commit()
    return redirect(url_for("dashboard"))

@app.route("/extraction/<int:extraction_id>/export/<fmt>")
@login_required
def export_extraction(extraction_id, fmt):
    from flask import Response
    extraction = Extraction.query.filter_by(id=extraction_id, user_id=session["user_id"]).first_or_404()
    data = json.loads(extraction.result_json)
    if fmt == "json":
        return Response(json.dumps(data, ensure_ascii=False, indent=2), mimetype="application/json",
                        headers={"Content-Disposition": f"attachment; filename=extraccion_{extraction_id}.json"})
    elif fmt == "csv":
        import csv, io
        si = io.StringIO()
        writer = csv.writer(si)
        writer.writerow(["Campo", "Valor"])
        for k, v in data.items():
            writer.writerow([k, v or ""])
        return Response(si.getvalue(), mimetype="text/csv",
                        headers={"Content-Disposition": f"attachment; filename=extraccion_{extraction_id}.csv"})
    return redirect(url_for("view_extraction", extraction_id=extraction_id))

@app.route("/profile", methods=["GET", "POST"])
@login_required
def profile():
    user = User.query.get(session["user_id"])
    if request.method == "POST":
        action = request.form.get("action")
        if action == "change_password":
            current = request.form.get("current_password")
            new_pw = request.form.get("new_password")
            confirm = request.form.get("confirm_password")
            if not check_password_hash(user.password_hash, current):
                flash("Contraseña actual incorrecta", "error")
            elif len(new_pw) < 6:
                flash("La nueva contraseña debe tener al menos 6 caracteres", "error")
            elif new_pw != confirm:
                flash("Las contraseñas no coinciden", "error")
            else:
                user.password_hash = generate_password_hash(new_pw)
                db.session.commit()
                flash("Contraseña actualizada correctamente", "success")
        elif action == "delete_account":
            db.session.delete(user)
            db.session.commit()
            session.clear()
            return redirect(url_for("login"))
    return render_template("profile.html", user=user)

if __name__ == "__main__":
    os.makedirs("uploads", exist_ok=True)
    app.run(debug=True, port=5000)
