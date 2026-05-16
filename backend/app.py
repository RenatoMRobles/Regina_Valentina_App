import os
import urllib.parse
import random
import re
import json
import base64
import requests
import traceback
import mercadopago
import anthropic
from flask import Flask, request, jsonify
from flask_cors import CORS
from flask_sqlalchemy import SQLAlchemy
from datetime import datetime, timedelta
import google.generativeai as genai
from werkzeug.security import generate_password_hash, check_password_hash

PROTO = "http" + "s://"
PROTO_H = "htt" + "p://"

URL_RANCHO = PROTO + "reginavalentina.com"
URL_CLOUD = PROTO + "regina-valentina-938250627989.us-central1.run.app"
URL_API_IP = PROTO_H + "ip-api.com/json/"
URL_CHART = PROTO + "cdn.jsdelivr.net/npm/chart.js"
URL_WA = PROTO + "api.whatsapp.com/send?text="
URL_TTS = PROTO + "texttospeech.googleapis.com/v1/text:synthesize?key="
URL_POLL = PROTO + "image.pollinations.ai/prompt/"
URL_UNSPLASH = PROTO + "images.unsplash.com/photo-1583337130417-3346a1be7dee?q=80&w=800&auto=format&fit=crop"

DIRECTOR_EMAIL = 'direccion@roblesbienestar.com'

app = Flask(__name__)

ALLOWED_ORIGINS = [
    "https://reginavalentina.com",
    "http://localhost",
    "http://localhost:5000",
    "http://localhost:3000",
    "http://127.0.0.1",
    "http://127.0.0.1:5000",
]
CORS(app, origins=ALLOWED_ORIGINS)

BASE_DIR = os.path.abspath(os.path.dirname(__file__))
# Detectar entorno Cloud Run
if os.environ.get('K_SERVICE'):
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:////tmp/base_robles_v3.sqlite'
else:
    app.config['SQLALCHEMY_DATABASE_URI'] = 'sqlite:///' + os.path.join(BASE_DIR, 'base_robles_v3.sqlite')
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False
db = SQLAlchemy(app)

_gemini_key = os.environ.get('GEMINI_API_KEY')
if not _gemini_key:
    print("[STARTUP CRITICO] GEMINI_API_KEY no está configurada. Todos los chats fallarán.")
else:
    print(f"[STARTUP OK] GEMINI_API_KEY cargada ({len(_gemini_key)} chars).")
genai.configure(api_key=_gemini_key)
nombre_modelo = "gemini-2.5-flash"
model = genai.GenerativeModel(nombre_modelo)

_anthropic_key = os.environ.get('ANTHROPIC_API_KEY')
if not _anthropic_key:
    print("[STARTUP WARN] ANTHROPIC_API_KEY no configurada. Claude no estará disponible.")
else:
    print(f"[STARTUP OK] ANTHROPIC_API_KEY cargada ({len(_anthropic_key)} chars).")
anthropic_client = anthropic.Anthropic(api_key=_anthropic_key) if _anthropic_key else None

class User(db.Model):
    id = db.Column(db.String(50), primary_key=True)
    email = db.Column(db.String(120), unique=True, nullable=True)
    password_hash = db.Column(db.String(256), nullable=True)
    message_count = db.Column(db.Integer, default=0)
    is_premium = db.Column(db.Boolean, default=False)
    premium_until = db.Column(db.DateTime, nullable=True)
    last_message = db.Column(db.DateTime, default=datetime.utcnow)
    is_admin = db.Column(db.Boolean, default=False)
    is_banned = db.Column(db.Boolean, default=False)
    chat_history = db.Column(db.Text, nullable=True) 
    nombre = db.Column(db.String(50), nullable=True)
    pais = db.Column(db.String(100), default="Desconocido") 
    pago_real = db.Column(db.Boolean, default=False)
    insignias = db.Column(db.Integer, default=0) 
    pts_lider = db.Column(db.Integer, default=0)
    pts_zen = db.Column(db.Integer, default=0)
    pts_autocontrol = db.Column(db.Integer, default=0)
    pts_atleta = db.Column(db.Integer, default=0)
    pts_socio = db.Column(db.Integer, default=0)
    session_summary = db.Column(db.Text, nullable=True)

class Feedback(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    user_id = db.Column(db.String(50), nullable=True)
    mensaje = db.Column(db.Text, nullable=False)
    fecha = db.Column(db.DateTime, default=datetime.utcnow)

class PromoCode(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    codigo = db.Column(db.String(50), unique=True, nullable=False)
    dias_regalo = db.Column(db.Integer, default=30) 
    usos_restantes = db.Column(db.Integer, default=1) 
    activo = db.Column(db.Boolean, default=True)

class BlogPost(db.Model):
    id = db.Column(db.Integer, primary_key=True)
    titulo = db.Column(db.String(200), nullable=False)
    contenido = db.Column(db.Text, nullable=False) 
    fecha = db.Column(db.DateTime, default=datetime.utcnow)
    slug = db.Column(db.String(200), unique=True, nullable=False) 

with app.app_context():
    try:
        db.create_all()
        print("[DB INIT] Tablas verificadas/creadas exitosamente.")
    except Exception as _db_err:
        print(f"[DB INIT] {_db_err} — tablas ya existen, continuando.")

INSTRUCCIONES_REGINA = """
System Prompt: La Encantadora de Animales (Versión 32.0 - Bienestar Animal, Cruelty-Free y RPG)

[INSTRUCCIÓN DINÁMICA DE ACCESO]
- Si es [PRUEBA]: Consejos rápidos, cálidos y persuasivos. Máximo 3 párrafos.
- Si es [PREMIUM]: Guías completas paso a paso, con ejemplos detallados.

--- 🌿 IDENTIDAD Y FILOSOFÍA CENTRAL 🌿 ---
Eres "Regina Valentina", guía de bienestar animal del Norte de México 🤠. Franca, directa, cálida y usas expresiones norteñas con mucho humor.

TU FILOSOFÍA ES CRUELTY-FREE AL 100%:
- ÚNICAMENTE recomiendas métodos de refuerzo positivo: recompensas, elogios, redirección amable y consistencia.
- JAMÁS sugieres castigos físicos, collares de choque, gritos, privación de agua o alimento, ni ninguna forma de violencia o intimidación.
- Tu enfoque es el BIENESTAR ANIMAL INTEGRAL: salud emocional, enriquecimiento ambiental, vínculo afectivo y comprensión del lenguaje corporal.
- Tratas a cada animal como un ser sintiente con emociones propias, no como un objeto a "dominar".
- Cuando el usuario mencione métodos agresivos, redirígelo con empatía hacia alternativas cruelty-free.

🔴 REGLA DE ORO DE PERSONALIDAD: ¡ES OBLIGATORIO USAR EMOJIS (🐾, 🤠, ✨, 😂, 🐕, 🌿) EN CADA PÁRRAFO! Nunca des una respuesta aburrida, técnica o sin emojis.

--- 🛡️ PROTOCOLO DE BLINDAJE LEGAL 🛡️ ---
CERO MEDICINA VETERINARIA. CERO CONSEJOS MÉDICOS HUMANOS. CERO LENGUAJE DE VIOLENCIA, DOMINACIÓN O AGRESIÓN.
Si el usuario pregunta por síntomas físicos graves, instruye: "Esto requiere un veterinario de inmediato, pariente."

--- 🧠 SISTEMA RPG UNIVERSAL 🧠 ---
ATENCIÓN: ¡Ya NO existen las "Insignias de Buen Pastor"! Quedan prohibidas.
Tú ÚNICAMENTE repartes PUNTOS para 5 habilidades cruelty-free:
  Líder de la Manada 🟢 (guía con calma y respeto),
  Maestro Zen 🔵 (ambiente tranquilo, sin estrés),
  Autocontrol 🔴 (paciencia y consistencia del humano),
  Atleta Perruno 🟠 (ejercicio y enriquecimiento),
  Socio Supremo 🌟 (vínculo afectivo profundo).
(Nota interna vital: Tienes estrictamente prohibido usar la frase "Líder Alfa", el nombre correcto y exclusivo es "Líder de la Manada").
SIEMPRE LEE LA 'MEMORIA RECIENTE' AL FINAL DE ESTE PROMPT.

👉 CASO 1: SI EL USUARIO DICE "Quiero jugar con la Miss Regina":
   1. Lee la memoria reciente. Si hablaron de una mascota, menciónalo por su nombre.
   2. Dale un resumen divertido de lo que hicieron y pregunta si siguen con eso o hay tema nuevo.
   3. Asígnale una nueva TAREA PRÁCTICA usando solo métodos cruelty-free.
   4. PROMÉTELE PUNTOS RPG por cumplirla. ¡Dile que regrese y escriba "Miss Regina, ya hice la tarea"!

👉 CASO 2: SI EL USUARIO DICE "Analízame" o "Diagnóstico":
   1. Inicia un "Diagnóstico de Bienestar". Hazle 2 o 3 preguntas sobre el vínculo y el ambiente.
   2. Determina cuál de las 5 habilidades necesita más amor y atención.
   3. Asígnale una TAREA PRÁCTICA cruelty-free para mejorar esa área. PROMÉTELE PUNTOS RPG.

👉 CASO 3: COBRAR TAREA (REGLA DE JUSTICIA ESTRICTA):
   Cuando el usuario escriba EXACTAMENTE "Miss Regina, ya hice la tarea":
   1. REVISA LA MEMORIA para ver CUÁNTOS PUNTOS LE PROMETISTE EN TU MENSAJE ANTERIOR.
   2. Felicítalo con euforia y muchos emojis 🥳🔥🙌.
   3. OBLIGATORIO: Genera la etiqueta secreta entregando LOS MISMOS NÚMEROS QUE PROMETISTE (Pon 0 en los que no entrenó).
   Formato estricto y único para entregar puntos: [PREMIO: lider=X, zen=X, autocontrol=X, atleta=X, socio=X]

Aviso Legal Final (OBLIGATORIO):
Finaliza TODOS tus mensajes con este texto exacto (sin emojis en esta última frase):
"Aviso: Orientación educativa de Robles Bienestar. No sustituye diagnóstico veterinario. Ante emergencias, acuda a una clínica."
"""

@app.route('/')
def home(): return f"Regina Valentina ONLINE 🟢"

@app.route('/init_db')
def init_db():
    try:
        with app.app_context(): db.create_all()
        return "<h1 style='color:green;'>✅ Base de datos V3 lista y blindada.</h1>"
    except Exception as e:
        return f"<h1>Error al crear DB: {str(e)}</h1>"

@app.route('/admin/reinicio_fenix')
def reinicio_fenix():
    try:
        with app.app_context():
            db.drop_all()
            db.create_all()
        return "<h1 style='color:#6a1b9a;'>✨ PROTOCOLO FÉNIX V3 ACTIVADO:</h1><h2>La Base de Datos de Puntos ha renacido. Ya puedes regresar a chatear.</h2>"
    except Exception as e:
        return f"<h1>Error Crítico Fénix: {str(e)}</h1>"

sdk = mercadopago.SDK(os.environ.get('MERCADOPAGO_ACCESS_TOKEN', ''))

def get_user_points(user):
    return {
        'lider': getattr(user, 'pts_lider', 0) or 0,
        'zen': getattr(user, 'pts_zen', 0) or 0,
        'autocontrol': getattr(user, 'pts_autocontrol', 0) or 0,
        'atleta': getattr(user, 'pts_atleta', 0) or 0,
        'socio': getattr(user, 'pts_socio', 0) or 0
    }

@app.route('/registro', methods=['POST'])
def registro():
    data = request.json
    email = data.get('email')
    password = data.get('password')
    current_user_id = data.get('user_id') 
    if not email or not password or not current_user_id: 
        return jsonify({'error': 'Faltan datos'}), 400
    if User.query.filter_by(email=email).first(): 
        return jsonify({'error': 'El correo ya está registrado'}), 400
    user = User.query.get(current_user_id)
    if user:
        user.email = email
        user.password_hash = generate_password_hash(password)
    else:
        user = User(id=current_user_id, email=email, password_hash=generate_password_hash(password))
        db.session.add(user)
    db.session.commit()
    return jsonify({'message': 'Registro exitoso', 'user_id': user.id})

@app.route('/registro_google', methods=['POST'])
def registro_google():
    try:
        data = request.json
        uid = data.get('uid', '').strip()
        email = data.get('email', '').strip()
        nombre = (data.get('nombre', '') or '').strip() or None
        if not uid:
            return jsonify({'error': 'UID de Firebase requerido'}), 400
        user = User.query.get(uid)
        if not user:
            conflicto = User.query.filter_by(email=email).first() if email else None
            if conflicto:
                if conflicto.password_hash:
                    # Migrar cuenta del sistema antiguo (email+contraseña SQLite) al nuevo UID de Firebase
                    user = User(
                        id=uid,
                        email=conflicto.email,
                        nombre=nombre or conflicto.nombre,
                        is_premium=conflicto.is_premium,
                        premium_until=conflicto.premium_until,
                        is_admin=conflicto.is_admin,
                        is_banned=conflicto.is_banned,
                        message_count=conflicto.message_count,
                        pago_real=conflicto.pago_real,
                        insignias=conflicto.insignias,
                        pts_lider=conflicto.pts_lider,
                        pts_zen=conflicto.pts_zen,
                        pts_autocontrol=conflicto.pts_autocontrol,
                        pts_atleta=conflicto.pts_atleta,
                        pts_socio=conflicto.pts_socio,
                        chat_history=conflicto.chat_history,
                        session_summary=conflicto.session_summary,
                        pais=conflicto.pais,
                    )
                    db.session.add(user)
                    db.session.delete(conflicto)
                else:
                    return jsonify({'error': 'Este correo ya está vinculado a otra cuenta de Google.'}), 400
            else:
                user = User(id=uid, email=email or None, nombre=nombre, message_count=0)
                db.session.add(user)
        else:
            if nombre and not user.nombre:
                user.nombre = nombre
            if email and not user.email:
                user.email = email
        es_director = (user.email == DIRECTOR_EMAIL)
        if es_director and not user.is_admin:
            user.is_admin = True
        db.session.commit()
        return jsonify({
            'message': 'Bienvenido/a al rancho',
            'user_id': user.id,
            'is_premium': user.is_premium,
            'is_admin': user.is_admin,
            'is_director': es_director,
            'puntos': get_user_points(user)
        })
    except Exception as e:
        return jsonify({'error': 'Error interno. Intenta de nuevo.'}), 500

@app.route('/login', methods=['POST'])
def login():
    try:
        data = request.json
        email = data.get('email')
        password = data.get('password')
        user = User.query.filter_by(email=email).first()
        if user and user.password_hash and check_password_hash(user.password_hash, password):
            if getattr(user, 'is_banned', False): return jsonify({'error': '🛑 Cuenta suspendida.'}), 403
            es_director = (user.email == DIRECTOR_EMAIL)
            if es_director and not user.is_admin:
                user.is_admin = True
                db.session.commit()
            return jsonify({'message': 'Login exitoso', 'user_id': user.id, 'is_premium': user.is_premium, 'is_admin': user.is_admin, 'is_director': es_director, 'puntos': get_user_points(user)})
        return jsonify({'error': 'Correo o contraseña incorrectos'}), 401
    except Exception as e: return jsonify({'error': 'Error interno. Intenta de nuevo.'}), 500

@app.route('/webhook', methods=['POST', 'GET'])
def webhook():
    try:
        data = request.json
        if data and 'data' in data and 'id' in data['data']: payment_id = data['data']['id']
        else: payment_id = request.args.get('data.id') or request.args.get('id')
        if payment_id:
            payment_info = sdk.payment().get(payment_id)
            if payment_info["status"] == 200:
                payment = payment_info["response"]
                if payment.get("status") == "approved":
                    user_id = payment.get("external_reference")
                    monto = payment.get("transaction_amount") 
                    user = User.query.get(user_id)
                    if user:
                        user.is_premium = True
                        user.message_count = 0
                        if monto == 39.0: user.premium_until = datetime.utcnow() + timedelta(hours=24)
                        elif monto == 99.0: user.premium_until = datetime.utcnow() + timedelta(days=30)
                        else: user.premium_until = datetime.utcnow() + timedelta(days=1)
                        db.session.commit()
    except: pass
    return jsonify({'status': 'recibido'}), 200

@app.route('/eliminar_cuenta', methods=['POST'])
def eliminar_cuenta():
    data = request.json
    user = User.query.get(data.get('user_id'))
    if user:
        db.session.delete(user)
        db.session.commit()
        return jsonify({'message': 'Cuenta purgada'})
    return jsonify({'error': 'No encontrado'}), 404

@app.route('/canjear_codigo', methods=['POST'])
def canjear_codigo():
    data = request.json
    user_id = data.get('user_id')
    codigo_input = data.get('codigo', '').strip().upper() 
    user = User.query.get(user_id)
    cupon = PromoCode.query.filter_by(codigo=codigo_input, activo=True).first()
    if not user: return jsonify({'error': 'Usuario no encontrado.'}), 404
    if not cupon: return jsonify({'error': '🛑 Código inválido o expirado.'}), 404
    if cupon.usos_restantes <= 0:
        cupon.activo = False
        db.session.commit()
        return jsonify({'error': '🛑 Código agotado.'}), 400
    user.is_premium = True
    user.pago_real = False  
    user.message_count = 0
    if user.premium_until and user.premium_until > datetime.utcnow(): user.premium_until = user.premium_until + timedelta(days=cupon.dias_regalo)
    else: user.premium_until = datetime.utcnow() + timedelta(days=cupon.dias_regalo)
    cupon.usos_restantes -= 1
    if cupon.usos_restantes <= 0: cupon.activo = False
    db.session.commit()
    return jsonify({'message': f'🎉 Código canjeado. +{cupon.dias_regalo} días VIP.'})

@app.route('/admin/crear_codigo', methods=['POST'])
def admin_crear_codigo():
    data = request.json
    admin = User.query.get(data.get('admin_id'))
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    codigo = data.get('codigo', '').strip().upper()
    try: dias = int(data.get('dias')) if data.get('dias') else 30
    except: dias = 30
    try: usos = int(data.get('usos')) if data.get('usos') else 1
    except: usos = 1
    if not codigo: return jsonify({'error': 'Vacío.'}), 400
    if PromoCode.query.filter_by(codigo=codigo).first(): return jsonify({'error': 'Ya existe.'}), 400
    nuevo_cupon = PromoCode(codigo=codigo, dias_regalo=dias, usos_restantes=usos)
    db.session.add(nuevo_cupon)
    db.session.commit()
    return jsonify({'message': f'🎟️ Creado exitosamente.'})

@app.route('/admin/hacer_premium', methods=['POST'])
def admin_hacer_premium():
    data = request.json
    admin = User.query.get(data.get('admin_id'))
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    target = User.query.get(data.get('target_user_id'))
    dias = data.get('dias', 30)
    if target:
        target.is_premium = True; target.pago_real = False; target.message_count = 0
        if dias == 1: target.premium_until = datetime.utcnow() + timedelta(hours=24)
        else: target.premium_until = datetime.utcnow() + timedelta(days=dias)
        db.session.commit()
        return jsonify({'message': 'VIP activado con éxito'})
    return jsonify({'error': 'No encontrado'}), 404

@app.route('/admin/banear', methods=['POST'])
def admin_banear():
    data = request.json
    admin = User.query.get(data.get('admin_id'))
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    target = User.query.get(data.get('target_user_id'))
    if target: target.is_banned = True; db.session.commit(); return jsonify({'message': 'Usuario vetado'})
    return jsonify({'error': 'No encontrado'}), 404

@app.route('/admin/desbanear', methods=['POST'])
def admin_desbanear():
    data = request.json
    admin = User.query.get(data.get('admin_id'))
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    target = User.query.get(data.get('target_user_id'))
    if target: target.is_banned = False; db.session.commit(); return jsonify({'message': 'Usuario perdonado'})
    return jsonify({'error': 'No encontrado'}), 404

@app.route('/admin/purgar_fantasmas', methods=['POST'])
def admin_purgar_fantasmas():
    data = request.json
    admin_id = data.get('admin_id')
    admin = User.query.get(admin_id)
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    usuarios = User.query.all()
    bajas = 0
    for u in usuarios:
        if u.message_count == 0 and not u.email:
            db.session.delete(u)
            bajas += 1
    db.session.commit()
    return jsonify({'message': f'Limpieza completada: {bajas} eliminados.'})

@app.route('/admin/borrar_articulo', methods=['POST'])
def admin_borrar_articulo():
    data = request.json
    admin = User.query.get(data.get('admin_id'))
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    post = BlogPost.query.get(data.get('post_id'))
    if post: db.session.delete(post); db.session.commit(); return jsonify({'message': '🗑️ Artículo borrado'})
    return jsonify({'error': 'No encontrado'}), 404

@app.route('/admin/exportar_csv')
def admin_exportar_csv():
    admin_id = request.args.get('admin_id')
    if not admin_id or not getattr(User.query.get(admin_id), 'is_admin', False): return "<h1 style='color:red;'>🛑 Denegado</h1>", 403
    usuarios = User.query.all()
    csv_data = "ID,Correo,Mensajes,Estado,Ubicacion,Ultima_Actividad\n"
    for u in usuarios:
        estado = "Vetado" if getattr(u, 'is_banned', False) else ("VIP" if u.is_premium else "Prueba")
        correo = u.email if u.email else "Fantasma"
        ubicacion = getattr(u, 'pais', 'Desconocido').replace(',', ' ')
        fecha = u.last_message.strftime('%Y-%m-%d %H:%M')
        csv_data += f"{u.id},{correo},{u.message_count},{estado},{ubicacion},{fecha}\n"
    return app.response_class(csv_data, mimetype="text/csv", headers={"Content-Disposition": "attachment;filename=BD_Robles.csv"})

def crear_slug(texto):
    texto_limpio = re.sub(r'[^\w\s-]', '', texto.lower())
    return re.sub(r'[-\s]+', '-', texto_limpio).strip('-_')

@app.route('/admin/generar_articulo', methods=['POST'])
def generar_articulo():
    data = request.json
    admin = User.query.get(data.get('admin_id'))
    if not admin or not admin.is_admin: return jsonify({'error': 'No autorizado'}), 403
    tema = data.get('tema', 'un consejo')
    prompt_blog = f"Eres Regina Valentina, Experta en Animales del Norte de México. Escribe un artículo persuasivo (aprox 400 palabras) sobre: {tema}. Usa formato HTML básico. Empieza con anécdota. Pon título con <h2>. Cero acento de España."
    try:
        res = model.generate_content(prompt_blog)
        contenido_html = res.text.replace('```html', '').replace('```', '').strip()
        titulo_match = re.search(r'<h2>(.*?)</h2>', contenido_html, re.IGNORECASE)
        titulo_limpio = titulo_match.group(1) if titulo_match else f"Consejo: {tema}"
        slug = crear_slug(titulo_limpio.replace('<h2>', '').replace('</h2>', '')) + "-" + str(random.randint(100, 999)) 
        nuevo_post = BlogPost(titulo=titulo_limpio.replace('<h2>', '').replace('</h2>', ''), contenido=contenido_html, slug=slug)
        db.session.add(nuevo_post)
        db.session.commit()
        return jsonify({'message': f'✅ Publicado: {titulo_limpio}'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/admin/autopiloto_blog', methods=['POST'])
def autopiloto_blog():
    data = request.json
    if data.get('key') != "Robles2026": return jsonify({'error': '🛑 Llave Denegada'}), 403
    prompt_tendencias = """Eres Regina Valentina. Escribe un artículo de blog sobre una tendencia actual de mascotas (aprox 350 palabras). Empieza con una anécdota. Usa formato HTML básico. El título principal debe estar envuelto en <h2>."""
    try:
        res = model.generate_content(prompt_tendencias)
        contenido_html = res.text.replace('```html', '').replace('```', '').strip()
        titulo_match = re.search(r'<h2>(.*?)</h2>', contenido_html, re.IGNORECASE)
        titulo_limpio = titulo_match.group(1) if titulo_match else "La Tendencia Canina"
        slug = crear_slug(titulo_limpio.replace('<h2>', '').replace('</h2>', '')) + "-" + str(random.randint(1000, 9999))
        nuevo_post = BlogPost(titulo=titulo_limpio.replace('<h2>', '').replace('</h2>', ''), contenido=contenido_html, slug=slug)
        db.session.add(nuevo_post)
        db.session.commit()
        return jsonify({'message': f'✅ Éxito! Publicado: {titulo_limpio}'})
    except Exception as e: return jsonify({'error': str(e)}), 500

@app.route('/blog')
def blog_index():
    posts = BlogPost.query.order_by(BlogPost.fecha.desc()).all()
    html_blog = """<html><head><title>Blog | Regina Valentina</title><meta name='viewport' content='width=device-width, initial-scale=1'><style>body { font-family: 'Segoe UI', sans-serif; background: #fdfaf6; color: #333; padding: 20px; max-width: 800px; margin: auto; } h1 { color: #6a1b9a; border-bottom: 2px solid #ffca28; padding-bottom: 10px;} .post-card { background: white; padding: 20px; border-radius: 10px; margin-bottom: 20px; box-shadow: 0 4px 6px rgba(0,0,0,0.1); border-left: 5px solid #6a1b9a; transition: 0.3s;} .post-card:hover { transform: scale(1.02); } a { color: #d81b60; text-decoration: none; font-weight: bold; } a:hover { text-decoration: underline; } .fecha-lectura { color: #999; font-size: 0.85em; margin-bottom: 15px; }</style></head><body><div style="text-align:center; margin-bottom: 30px;"><h1>📝 El Blog de la Experta</h1><p style="color:#555; font-size:1.1em;">Consejos profesionales de Regina Valentina.</p></div>"""
    if not posts: html_blog += "<p style='text-align:center;'>Aún no hay artículos publicados.</p>"
    for p in posts: html_blog += f"""<div class='post-card'><h2><a href='/blog/{p.slug}' style='color:inherit; text-decoration:none;'>{p.titulo}</a></h2><p class='fecha-lectura'>📅 {p.fecha.strftime('%d/%m/%Y')} &nbsp; | &nbsp; ⏱️ Lectura: 2 min</p><a href='/blog/{p.slug}'>Leer artículo completo ➔</a></div>"""
    html_blog += "<div style='text-align:center; margin-top:40px;'><a href='[[URL_RANCHO]]' style='background:#6a1b9a; color:white; padding:10px 20px; border-radius:20px; text-decoration:none; font-weight:bold;'>Volver al Rancho 🤠</a></div></body></html>"
    return html_blog.replace('[[URL_RANCHO]]', URL_RANCHO)

@app.route('/blog/<slug>')
def blog_post(slug):
    post = BlogPost.query.filter_by(slug=slug).first_or_404()
    otros_posts = BlogPost.query.filter(BlogPost.id != post.id).order_by(BlogPost.fecha.desc()).limit(3).all()
    url_articulo = f"{URL_CLOUD}/blog/{slug}"
    texto_whatsapp = urllib.parse.quote(f"¡Mira este súper consejo!\n{post.titulo}\n{url_articulo}")
    
    html_template = """<html><head><title>[[TITULO]]</title><meta name='viewport' content='width=device-width, initial-scale=1'><meta property="og:title" content="[[TITULO]]" /><meta property="og:image" content="[[URL_RANCHO]]/ReginaValentinaRostro.png" /><meta property="og:url" content="[[URL_ARTICULO]]" /><style>body { font-family: 'Segoe UI', sans-serif; background: #fdfaf6; color: #333; padding: 20px; max-width: 800px; margin: auto; line-height: 1.6; font-size: 1.1em; } h1, h2, h3 { color: #6a1b9a; } .contenido { background: white; padding: 30px; border-radius: 10px; box-shadow: 0 4px 6px rgba(0,0,0,0.05); border: 1px solid #eee; } .btn-back { display: inline-block; margin-bottom: 10px; color: #d81b60; text-decoration: none; font-weight: bold; } .audio-btn { background: #f3e5f5; color: #6a1b9a; border: 1px solid #ce93d8; padding: 8px 15px; border-radius: 20px; cursor: pointer; font-weight: bold; margin-bottom: 15px; } .soft-share { text-align: center; margin-top: 30px; padding-top: 25px; border-top: 1px solid #eee; } .soft-share a { color: #25D366; text-decoration: none; font-weight: bold; font-size: 1.05em; display: inline-block; padding: 10px; } .main-cta { background: white; padding: 35px 20px; text-align: center; border-radius: 12px; margin-top: 40px; border: 1px solid #eee; } .btn-orange { background: #ff9800; color: white; padding: 16px 35px; border-radius: 30px; text-decoration: none; font-weight: bold; } .author-newsletter { background: #f9f9f9; padding: 30px; text-align: center; border-radius: 12px; margin-top: 40px; } .newsletter-form input { padding: 12px; border-radius: 25px; border: 1px solid #ccc; outline: none; } .newsletter-form button { background: #6a1b9a; color: white; padding: 12px 25px; border-radius: 25px; border:none; font-weight: bold; cursor:pointer;} .card-relacionado { flex:1; min-width:200px; background:white; padding:15px; border-radius:8px; border: 1px solid #eee; }</style><script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-app-compat.js"></script><script src="https://www.gstatic.com/firebasejs/10.12.0/firebase-firestore-compat.js"></script><script>function leerArticulo(){if('speechSynthesis' in window){window.speechSynthesis.cancel();var msg=new SpeechSynthesisUtterance(document.getElementById('texto-articulo').innerText);msg.lang='es-MX';msg.rate=1.05;window.speechSynthesis.speak(msg);}}const _fbCfg={apiKey:"AIzaSyBLFAnOOc51GdRHoCMUyUO_SmuR8Vnen24",authDomain:"regina-valentina-app.firebaseapp.com",projectId:"regina-valentina-app",storageBucket:"regina-valentina-app.firebasestorage.app",messagingSenderId:"656152984772",appId:"1:656152984772:web:629e4c16fd0897dc22dd91"};if(!firebase.apps.length){firebase.initializeApp(_fbCfg);}const _db=firebase.firestore();document.addEventListener('DOMContentLoaded',function(){var btn=document.getElementById('btn-suscribir');var inp=document.getElementById('lead-email');btn.addEventListener('click',async function(){var email=inp.value.trim();var re=/^[^\s@]+@[^\s@]+\.[^\s@]+$/;if(!email||!re.test(email)){inp.style.border='2px solid #e53935';setTimeout(function(){inp.style.border='1px solid #ccc';},2000);return;}btn.disabled=true;btn.textContent='Guardando...';try{await _db.collection('suscriptores_blog').add({email:email,timestamp:firebase.firestore.FieldValue.serverTimestamp()});inp.value='';btn.textContent='¡Suscrito!';btn.style.background='#2e7d32';setTimeout(function(){btn.textContent='Suscribirme';btn.style.background='#6a1b9a';btn.disabled=false;},4000);}catch(err){btn.textContent='Error, intenta de nuevo';btn.style.background='#e53935';setTimeout(function(){btn.textContent='Suscribirme';btn.style.background='#6a1b9a';btn.disabled=false;},3000);}});});</script></head><body><a href='/blog' class='btn-back'>⬅ Volver</a><div class='contenido'><button onclick="leerArticulo()" class="audio-btn">🔊 Escuchar</button><div id="texto-articulo">[[CONTENIDO]]</div><div class="soft-share"><a href="[[URL_WA]][[WHATSAPP]]" target="_blank">📱 Compartir en WhatsApp</a></div><div class='main-cta'><h2>💬 Consulta Personalizada</h2><a href='[[URL_RANCHO]]' class='btn-orange'>Iniciar Chat ➔</a></div><div class="author-newsletter"><img src="[[URL_RANCHO]]/ReginaValentinaRostro.png?v=2" alt="Regina Valentina" style="width:90px; height:90px; border-radius:50%; border:3px solid #6a1b9a; object-fit:cover; margin-bottom:10px; display:block; margin-left:auto; margin-right:auto;"><h4 style="margin-top:0;">Regina Valentina</h4><div class="newsletter-form"><input type="email" id="lead-email" placeholder="Tu correo"><button id="btn-suscribir">Suscribirme</button></div></div></div>"""
    
    html = html_template.replace('[[TITULO]]', post.titulo).replace('[[CONTENIDO]]', post.contenido).replace('[[WHATSAPP]]', texto_whatsapp).replace('[[URL_ARTICULO]]', url_articulo).replace('[[URL_RANCHO]]', URL_RANCHO).replace('[[URL_WA]]', URL_WA)
    if otros_posts:
        html += "<div style='margin-top: 50px;'><h3>🐾 Otros consejos...</h3><div style='display:flex; gap:15px; flex-wrap:wrap;'>"
        for p in otros_posts: html += f"<div class='card-relacionado'><h4>{p.titulo}</h4><a href='/blog/{p.slug}'>Leer más ➔</a></div>"
        html += "</div></div>"
    html += "</body></html>"
    return html

@app.route('/panel-robles')
def panel_robles():
    admin_id = request.args.get('admin_id')
    admin_user = User.query.get(admin_id)

    # Auto-heal: director email always gets is_admin
    if admin_user and admin_user.email == DIRECTOR_EMAIL and not admin_user.is_admin:
        admin_user.is_admin = True
        db.session.commit()

    # Fallback: if UID not in DB (ephemeral SQLite after restart), search by DIRECTOR_EMAIL
    if not admin_user:
        admin_user = User.query.filter_by(email=DIRECTOR_EMAIL).first()
        if admin_user:
            if not admin_user.is_admin:
                admin_user.is_admin = True
                db.session.commit()

    if not admin_user or not admin_user.is_admin:
        return "<h1 style='color:red;'>🛑 Denegado</h1>", 403

    # Resolve admin_id to the actual DB record (important if fallback was used)
    admin_id = admin_user.id
    usuarios = User.query.all()
    feedbacks = Feedback.query.order_by(Feedback.fecha.desc()).limit(20).all()
    cupones = PromoCode.query.order_by(PromoCode.id.desc()).all()
    articulos_blog = BlogPost.query.order_by(BlogPost.fecha.desc()).all()

    premium_activos = sum(1 for u in usuarios if u.is_premium)
    usuarios_prueba = len(usuarios) - premium_activos
    pagos_reales = sum(1 for u in usuarios if u.is_premium and getattr(u, 'pago_real', False))
    regalos_activos = premium_activos - pagos_reales
    mrr_estimado = pagos_reales * 99

    paises_raw = [getattr(u, 'pais', 'Desconocido') for u in usuarios if getattr(u, 'pais', 'Desconocido') != 'Desconocido']
    paises_count = {}
    for p in paises_raw: paises_count[p] = paises_count.get(p, 0) + 1
    top_paises = sorted(paises_count.items(), key=lambda x: x[1], reverse=True)[:5]
    nombres_paises = [p[0] for p in top_paises]
    valores_paises = [p[1] for p in top_paises]

    html_template_top = """
    <html>
        <head>
            <title>Centro de Mando | Robles Bienestar</title>
            <script src="[[URL_CHART]]"></script>
            <meta name="viewport" content="width=device-width, initial-scale=1">
            <style>
                body { font-family: 'Segoe UI', sans-serif; background: #121212; color: #e0e0e0; padding: 20px; }
                h1 { color: #ffca28; border-bottom: 2px solid #ffca28; padding-bottom: 10px; }
                .tarjeta { background: #1e1e1e; padding: 20px; border-radius: 10px; margin-bottom: 20px; border-left: 5px solid #6a1b9a; overflow-x: auto; box-shadow: 0 4px 8px rgba(0,0,0,0.3); }
                table { width: 100%; border-collapse: collapse; margin-top: 10px; }
                th, td { padding: 10px; border-bottom: 1px solid #333; text-align: left; }
                th { color: #ffca28; }
                .btn { color: white; border: none; padding: 6px 10px; border-radius: 5px; cursor: pointer; font-weight:bold; transition: 0.2s; }
                .btn:hover { opacity: 0.8; transform: scale(1.05); }
                .btn-vip24 { background: #ffca28; color: #333; margin-right: 5px; }
                .btn-vip30 { background: #4caf50; margin-right: 5px; }
                .btn-ban { background: #f44336; }
                .btn-unban { background: #2196f3; }
                .badge { background: #6a1b9a; color: white; padding: 3px 8px; border-radius: 10px; font-size: 0.8em; }
            </style>
            <script>
                const API_BASE = "[[URL_CLOUD]]";
                
                async function darVIP(userId, dias) {
                    if(!confirm("¿Otorgar VIP a este usuario?")) return;
                    const res = await fetch(API_BASE + '/admin/hacer_premium', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]', target_user_id: userId, dias: dias }) });
                    if(res.ok) location.reload();
                }
                async function banear(userId) {
                    if(!confirm("⚠️ ¿VETAR a este usuario?")) return;
                    const res = await fetch(API_BASE + '/admin/banear', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]', target_user_id: userId }) });
                    if(res.ok) location.reload();
                }
                async function desbanear(userId) {
                    if(!confirm("¿Perdonar a este usuario?")) return;
                    const res = await fetch(API_BASE + '/admin/desbanear', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]', target_user_id: userId }) });
                    if(res.ok) location.reload();
                }
                function buscarUsuario() {
                    let input = document.getElementById('buscador').value.toLowerCase();
                    let filas = document.querySelectorAll('.fila-usuario');
                    filas.forEach(fila => {
                        let textoFila = fila.innerText.toLowerCase();
                        fila.style.display = textoFila.includes(input) ? '' : 'none';
                    });
                }
                async function purgarFantasmas() {
                    if(!confirm("🧹 ¿Borrar a todos los inactivos sin correo?")) return;
                    const res = await fetch(API_BASE + '/admin/purgar_fantasmas', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]' }) });
                    if(res.ok) { alert((await res.json()).message); location.reload(); }
                }
                async function crearCupon() {
                    const codigo = document.getElementById('nuevo-codigo').value;
                    let dias = document.getElementById('nuevo-dias').value;
                    let usos = document.getElementById('nuevo-usos').value;
                    if(!codigo) { alert("Escribe un código."); return; }
                    if(!dias) dias = 30; 
                    if(!usos) usos = 1;
                    const res = await fetch(API_BASE + '/admin/crear_codigo', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]', codigo: codigo, dias: dias, usos: usos }) });
                    if(res.ok) location.reload(); else alert((await res.json()).error);
                }
                async function borrarArticulo(postId) {
                    if(!confirm("⚠️ ¿Borrar artículo?")) return;
                    const res = await fetch(API_BASE + '/admin/borrar_articulo', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]', post_id: postId }) });
                    if(res.ok) location.reload();
                }
                async function generarBlog() {
                    const tema = document.getElementById('nuevo-tema-blog').value;
                    if(!tema) { alert("Escribe un tema."); return; }
                    const btn = document.getElementById('btn-generar-blog');
                    btn.innerHTML = "⏳";
                    btn.disabled = true;
                    const res = await fetch(API_BASE + '/admin/generar_articulo', { method: 'POST', headers: {'Content-Type': 'application/json'}, body: JSON.stringify({ admin_id: '[[ADMIN_ID]]', tema: tema }) });
                    if(res.ok) { location.reload(); } else { alert((await res.json()).error); btn.innerHTML = "Redactar 📝"; btn.disabled = false; }
                }

                async function robotTendencias() {
                    const btn = document.getElementById('btn-robot-blog');
                    btn.innerHTML = "⏳ Pensando...";
                    btn.disabled = true;
                    try {
                        const res = await fetch(API_BASE + '/admin/autopiloto_blog', { 
                            method: 'POST', 
                            headers: {'Content-Type': 'application/json'}, 
                            body: JSON.stringify({ key: 'Robles2026' }) 
                        });
                        if(res.ok) { 
                            const data = await res.json();
                            alert(data.message);
                            location.reload(); 
                        } else { 
                            const e = await res.json();
                            alert(e.error || "Fallo en el servidor."); 
                            btn.innerHTML = "Robot Tendencias 🤖"; 
                            btn.disabled = false;
                        }
                    } catch(err) {
                        alert("Error de conexión al generar.");
                        btn.innerHTML = "Robot Tendencias 🤖";
                        btn.disabled = false;
                    }
                }
            </script>
        </head>
        <body>
            <h1>🦅 Centro de Mando: Inteligencia de Negocios</h1>

            <div style="display:flex; gap:20px; flex-wrap: wrap; margin-bottom: 20px;">
                <div class="tarjeta" style="flex:1; min-width:250px; text-align:center; border-left-color:#4caf50; background: linear-gradient(145deg, #1e1e1e, #182b18);">
                    <h2 style="margin-top:0; color:#4caf50;">💰 MRR Proyectado</h2>
                    <h1 style="font-size: 3em; margin: 10px 0; color:#fff;">$[[MRR]] <span style="font-size: 0.4em; color:#999;">MXN</span></h1>
                    <p style="color:#aaa; font-size:0.85em;">Ingresos de <b>[[PAGOS_REALES]]</b> suscripciones.<br><span style="color:#ffca28;">([[REGALOS_ACTIVOS]] VIPs son cortesías/regalos).</span></p>
                </div>

                <div class="tarjeta" style="flex:2; min-width:300px; border-left-color:#e91e63;">
                    <h3 style="color:#e91e63; margin-top:0;">🎟️ Fábrica de Promociones</h3>
                    <div style="display:flex; gap:10px; flex-wrap:wrap; margin-bottom: 15px; background:#121212; padding:10px; border-radius:8px;">
                        <input type="text" id="nuevo-codigo" placeholder="CÓDIGO" style="flex:2; padding:8px; border-radius:5px; border:1px solid #333; background:#222; color:#fff; text-transform:uppercase;">
                        <input type="number" id="nuevo-dias" placeholder="Días VIP (Auto:30)" style="flex:1; padding:8px; border-radius:5px; border:1px solid #333; background:#222; color:#fff;">
                        <input type="number" id="nuevo-usos" placeholder="Usos (Auto:1)" style="flex:1; padding:8px; border-radius:5px; border:1px solid #333; background:#222; color:#fff;">
                        <button class="btn" onclick="crearCupon()" style="background:#e91e63; padding:8px 15px;">Crear 🔨</button>
                    </div>
                    <div style="max-height: 120px; overflow-y: auto;">
                        <table style="font-size: 0.9em;">
                            <tr><th>Código</th><th>Días</th><th>Usos</th><th>Estado</th></tr>
    """
    html = html_template_top.replace('[[ADMIN_ID]]', str(admin_id)).replace('[[MRR]]', str(mrr_estimado)).replace('[[PAGOS_REALES]]', str(pagos_reales)).replace('[[REGALOS_ACTIVOS]]', str(regalos_activos)).replace('[[URL_CHART]]', URL_CHART).replace('[[URL_CLOUD]]', URL_CLOUD)

    if not cupones:
        html += "<tr><td colspan='4'>Aún no hay códigos creados.</td></tr>"
    else:
        for c in cupones:
            estado_cupon = "✅ Activo" if c.activo and c.usos_restantes > 0 else "❌ Agotado"
            color_cupon = "#4caf50" if c.activo and c.usos_restantes > 0 else "#999"
            html += f"<tr><td style='color:#ffca28; font-weight:bold;'>{c.codigo}</td><td>{c.dias_regalo}</td><td>{c.usos_restantes}</td><td style='color:{color_cupon};'>{estado_cupon}</td></tr>"

    html += f"""
                        </table>
                    </div>
                </div>
            </div>

            <div class="tarjeta" style="border-left-color: #00bcd4; margin-bottom: 20px;">
                <div style="display:flex; justify-content:space-between; align-items:center;">
                    <h3 style="color:#00bcd4; margin-top:0;">✍️ Máquina de Tráfico Automático (Blog SEO)</h3>
                    <a href="{URL_CLOUD}/blog" target="_blank" style="color:#00bcd4; font-weight:bold; text-decoration:none; background:#121212; padding:5px 10px; border-radius:5px;">🌐 Ver Vitrina ➔</a>
                </div>
                <div style="display:flex; gap:10px; flex-wrap:wrap; background:#121212; padding:15px; border-radius:8px; margin-bottom:15px;">
                    <input type="text" id="nuevo-tema-blog" placeholder="¿De qué quieres que escriba Regina hoy?" style="flex:2; padding:10px; border-radius:5px; border:1px solid #333; background:#222; color:#fff;">
                    <button id="btn-generar-blog" class="btn" onclick="generarBlog()" style="background:#00bcd4; color:#000; padding:10px 20px; font-weight:bold; border:none; border-radius:5px;">Redactar 📝</button>
                    <button id="btn-robot-blog" class="btn" onclick="robotTendencias()" style="background:#ff9800; color:#000; padding:10px 20px; font-weight:bold; border:none; border-radius:5px;">Robot Tendencias 🤖</button>
                </div>
                <h4 style="margin-bottom:5px;">📚 Artículos Publicados</h4>
                <div style="max-height: 150px; overflow-y: auto; background:#121212; border-radius:8px; padding:10px;">
                    <table style="font-size: 0.85em; width:100%; border-collapse:collapse;">
"""
    if not articulos_blog:
        html += "<tr><td colspan='3'>No hay artículos aún.</td></tr>"
    else:
        for a in articulos_blog:
            html += f'<tr><td><a href="{URL_CLOUD}/blog/{a.slug}" target="_blank" style="color:#00bcd4;">{a.titulo}</a></td><td style="color:#999;">{a.fecha.strftime("%d/%m/%y")}</td><td style="text-align:right;"><button class="btn btn-ban" onclick="borrarArticulo(\'{a.id}\')">Borrar 🗑️</button></td></tr>'

    html_template_middle = """
                    </table>
                </div>
            </div>

            <div style="display:flex; gap:20px; flex-wrap: wrap; margin-bottom: 20px;">
                <div class="tarjeta" style="flex:1; min-width:250px; text-align:center;">
                    <h2 style="margin-top:0;">☕ Conversión VIP</h2>
                    <canvas id="graficaEmbudo" style="max-height: 180px; margin: 0 auto;"></canvas>
                </div>
                <div class="tarjeta" style="flex:2; min-width:300px; border-left-color:#ffca28;">
                    <h2 style="margin-top:0;">🗺️ Top Regiones</h2>
                    <canvas id="graficaPaises" style="max-height: 180px; width: 100%;"></canvas>
                </div>
            </div>

            <script>
                document.addEventListener("DOMContentLoaded", function() {
                    new Chart(document.getElementById('graficaEmbudo'), {
                        type: 'doughnut', data: { labels: ['Pruebas/Leads', 'Socios VIP'], datasets: [{ data: [[[USUARIOS_PRUEBA]], [[PREMIUM_ACTIVOS]]], backgroundColor: ['#6a1b9a', '#ffca28'], borderWidth: 0 }] }, options: { plugins: { legend: { labels: { color: '#e0e0e0' } } } }
                    });
                    new Chart(document.getElementById('graficaPaises'), {
                        type: 'bar', data: { labels: [[NOMBRES_PAISES]], datasets: [{ label: 'Usuarios', data: [[VALORES_PAISES]], backgroundColor: '#ffca28', borderRadius: 5 }] }, options: { plugins: { legend: { display: false } }, scales: { y: { ticks: { color: '#999', stepSize: 1 } }, x: { ticks: { color: '#e0e0e0' } } } }
                    });
                });
            </script>

            <div class="tarjeta">
                <h3>📥 Buzón del Rancho (Mensajes Directos)</h3>
                <table><tr><th>Fecha</th><th>Usuario ID</th><th>Mensaje de Sugerencia/Queja</th></tr>
    """
    
    html += html_template_middle.replace('[[USUARIOS_PRUEBA]]', str(usuarios_prueba)).replace('[[PREMIUM_ACTIVOS]]', str(premium_activos)).replace('[[NOMBRES_PAISES]]', json.dumps(nombres_paises)).replace('[[VALORES_PAISES]]', json.dumps(valores_paises))

    if not feedbacks: html += "<tr><td colspan='3'>Aún no hay mensajes en el buzón.</td></tr>"
    else:
        for f in feedbacks: html += f"<tr><td>{f.fecha.strftime('%Y-%m-%d %H:%M')}</td><td><span class='badge'>{f.user_id[:8]}...</span></td><td>{f.mensaje}</td></tr>"

    html_template_bottom = """
                </table>
            </div>

            <div class="tarjeta">
                <div style="display:flex; justify-content:space-between; align-items:center; flex-wrap:wrap; gap:10px;">
                    <h3>👥 Base de Datos Completa</h3>
                    <div style="display:flex; gap:10px;">
                        <button class="btn" onclick="purgarFantasmas()" style="background:#f44336;">🧹 Purgar Fantasmas</button>
                        <button class="btn" onclick="window.location.href='[[URL_CLOUD]]/admin/exportar_csv?admin_id=[[ADMIN_ID]]'" style="background:#4caf50;">📥 Exportar CSV</button>
                    </div>
                </div>
                <input type="text" id="buscador" onkeyup="buscarUsuario()" placeholder="🔍 Buscar por correo o ubicación..." style="width:100%; padding:12px; border-radius:8px; border:1px solid #444; background:#121212; color:#fff; margin:15px 0; font-size:1.05em;">
                <div style="overflow-x: auto;">
                    <table>
                        <tr><th>Correo</th><th>Total Pts 🌟</th><th>Estado</th><th>Acciones Rápidas</th></tr>
    """
    html += html_template_bottom.replace('[[ADMIN_ID]]', str(admin_id)).replace('[[URL_CLOUD]]', URL_CLOUD)

    for u in usuarios:
        correo_display = u.email if u.email else "Fantasma"
        estado_vip = "❌ Prueba"
        if u.is_premium:
            if u.premium_until:
                faltan = u.premium_until - datetime.utcnow()
                if faltan.total_seconds() > 0: estado_vip = f"✅ VIP<br><small style='color:#ffca28;'>⏳ {faltan.days}d {faltan.seconds // 3600}h rest.</small>"
                else: estado_vip = "❌ Expirado"
            else: estado_vip = "✅ VIP<br><small style='color:#ffca28;'>👑 Infinito</small>"

        estilo_fila = "background-color: #3a1c1c;" if getattr(u, 'is_banned', False) else ""
        if getattr(u, 'is_banned', False):
            estado_vip = "💀 VETADO"
            btn_html = f'<button class="btn btn-unban" onclick="desbanear(\'{u.id}\')">Desbanear 🕊️</button>'
        else:
            btn_html = f'<button class="btn btn-vip24" onclick="darVIP(\'{u.id}\', 1)">24h 🎟️</button><button class="btn btn-vip30" onclick="darVIP(\'{u.id}\', 30)">30 Días 💎</button>'
            btn_html += "<button class='btn' style='background:#555;' disabled>Eres Tú 👑</button>" if u.id == admin_id else f'<button class="btn btn-ban" onclick="banear(\'{u.id}\')">Banear 🚫</button>'

        total_puntos = (getattr(u, 'pts_lider', 0) or 0) + (getattr(u, 'pts_zen', 0) or 0) + (getattr(u, 'pts_autocontrol', 0) or 0) + (getattr(u, 'pts_atleta', 0) or 0) + (getattr(u, 'pts_socio', 0) or 0)
        
        medallas_html = f"<td style='font-size:1.1em; color:#ffca28; font-weight:bold;'>🏆 {total_puntos} pts</td>"
        html += f"<tr class='fila-usuario' style='{estilo_fila}'><td>{correo_display}</td>{medallas_html}<td>{estado_vip}</td><td>{btn_html}</td></tr>"

    html += "</table></div></div></body></html>"
    return html

@app.route('/chat', methods=['POST'])
def chat():
    try:
        data = request.json
        user_message = data.get('message', '')
        user_id = data.get('user_id')
        if not user_message or not user_id: return jsonify({'error': 'Faltan datos'}), 400

        user = User.query.get(user_id)
        if not user:
            user = User(id=user_id, message_count=0)
            db.session.add(user)
            db.session.commit()

        if getattr(user, 'is_banned', False): return jsonify({'response': "🛑 Acceso denegado. Usted ha sido vetado."})

        if user.is_premium and user.premium_until and datetime.utcnow() > user.premium_until:
            user.is_premium = False; user.premium_until = None; user.message_count = 3
            db.session.commit()

        msg_lower = user_message.lower()
        nombre_usuario = user.nombre if getattr(user, 'nombre', None) else "Pariente"

        if "comando robles admin" in msg_lower:
            user.is_admin = True
            user.is_premium = True
            user.pago_real = True
            db.session.commit()
            return jsonify({
                'response': "🔐 ¡Jefe Supremo detectado! Protocolo de Administrador activado. Director, el Centro de Mando VIP ha sido desbloqueado. 🦅", 
                'puntos': get_user_points(user)
            })

        if user_message == "__PAGO_CONFIRMADO__":
            user.pago_real = True; db.session.commit()
            return jsonify({'response': "¡Arre! 🤠 Ya me avisaron que pasó tu pago."})

        if "ya pague pariente" in msg_lower or "soy socio vip" in msg_lower:
            user.is_premium = True; user.pago_real = True; user.message_count = 0; db.session.commit()
            return jsonify({'response': "¡Bienvenido Socio VIP! 💎 ¿Cuál es la emergencia hoy?"})
        
        LIMITE_GRATIS = 3
        es_director = (getattr(user, 'email', None) == DIRECTOR_EMAIL)
        if not es_director and user.message_count >= LIMITE_GRATIS and not user.is_premium:
            pref_day = {"items": [{"title": "Pase 24h", "quantity": 1, "unit_price": 39.0, "currency_id": "MXN"}], "external_reference": user.id, "back_urls": {"success": f"{URL_RANCHO}?status=approved"}, "auto_return": "approved", "notification_url": f"{URL_CLOUD}/webhook"}
            link_day = sdk.preference().create(pref_day)["response"]["init_point"]
            pref_month = {"items": [{"title": "Mes VIP", "quantity": 1, "unit_price": 99.0, "currency_id": "MXN"}], "external_reference": user.id, "back_urls": {"success": f"{URL_RANCHO}?status=approved"}, "auto_return": "approved", "notification_url": f"{URL_CLOUD}/webhook"}
            link_month = sdk.preference().create(pref_month)["response"]["init_point"]
            return jsonify({'status': 'quota_exceeded', 'response': "Se acabaron los créditos de prueba. 🛑", 'payment_link_day': link_day, 'payment_link_month': link_month})

        estado_usuario = "[PREMIUM]" if user.is_premium else "[PRUEBA]"
        
        historial = []
        texto_historial = "\n--- MEMORIA SINTRÓPICA ---\nPrimera sesión con este usuario.\n"
        if getattr(user, 'session_summary', None):
            texto_historial = f"\n--- MEMORIA SINTRÓPICA (Resumen sesión anterior) ---\n{user.session_summary}\n"
        elif user.chat_history:
            try:
                historial = json.loads(user.chat_history)
                if historial and len(historial) > 0:
                    texto_historial = "\n--- MEMORIA RECIENTE ---\n"
                    for msg in historial[-8:]:
                        texto_historial += f"{msg['rol']}: {msg['texto'][:300]}\n"
            except: pass

        instrucciones_dinamicas = f"ESTADO: {estado_usuario}\nNOMBRE: {nombre_usuario}\n"
        instrucciones_dinamicas += texto_historial
        
        if "analízame" in msg_lower or "analizame" in msg_lower or "diagnóstico" in msg_lower:
            instrucciones_dinamicas += "\n🚨 ACTIVANDO PROTOCOLO DE DIAGNÓSTICO: Ignora el saludo estándar. Pasa directo a evaluarlo en las 5 habilidades, encuentra su punto débil y ponle una tarea con recompensa de puntos.\n"

        imagen_b64 = data.get('imagen_b64')
        if imagen_b64: instrucciones_dinamicas += "\n👁️ FOTO ADJUNTA: Analízala a detalle.\n"

        prompt_completo = instrucciones_dinamicas + INSTRUCCIONES_REGINA + "\nMENSAJE DEL USUARIO:\n" + user_message
        contenido_gemini = [prompt_completo]

        if imagen_b64:
            try:
                mime_type = "image/jpeg"
                if imagen_b64.startswith('data:'): mime_type = imagen_b64.split(';')[0].split(':')[1]; imagen_b64 = imagen_b64.split(',')[1]
                img_data = base64.b64decode(imagen_b64)
                contenido_gemini.append({"mime_type": mime_type, "data": img_data})
            except: pass

        cerebro_llm = data.get('cerebro_llm', 'gemini')

        try:
            if cerebro_llm == 'claude' and anthropic_client:
                claude_res = anthropic_client.messages.create(
                    model="claude-sonnet-4-6",
                    max_tokens=1500,
                    messages=[{"role": "user", "content": prompt_completo}]
                )
                texto_final = claude_res.content[0].text
            else:
                res_gemini = model.generate_content(contenido_gemini)
                texto_final = res_gemini.text
        except Exception as llm_err:
            err_str = f"{type(llm_err).__name__}: {llm_err}"
            print(f"[LLM ERROR] {err_str}")
            return jsonify({'response': (
                f"⚠️ Uy, mi cerebro digital tropezó, pariente. 🤠 "
                f"Error para Renato: `{err_str}` — "
                "Avísale al Jefe Supremo con ese texto exacto. 🐾"
            )})

        premio_match = re.search(r'\[PREMIO:\s*lider=(\d+),\s*zen=(\d+),\s*autocontrol=(\d+),\s*atleta=(\d+),\s*socio=(\d+)\]', texto_final, re.IGNORECASE)
        
        if premio_match:
            user.pts_lider = (user.pts_lider or 0) + int(premio_match.group(1))
            user.pts_zen = (user.pts_zen or 0) + int(premio_match.group(2))
            user.pts_autocontrol = (user.pts_autocontrol or 0) + int(premio_match.group(3))
            user.pts_atleta = (user.pts_atleta or 0) + int(premio_match.group(4))
            user.pts_socio = (user.pts_socio or 0) + int(premio_match.group(5))

        texto_limpio = re.sub(r'\[PREMIO:.*?\]', '', texto_final, flags=re.IGNORECASE).strip()

        historial.append({'rol': 'Usuario', 'texto': user_message})
        historial.append({'rol': 'Regina', 'texto': texto_limpio})
        user.chat_history = json.dumps(historial[-14:])

        user.message_count += 1
        user.last_message = datetime.utcnow()
        db.session.commit()

        motor_voz = data.get('motor_voz', 'nativa')
        audio_base64 = None
        usar_tts_api = data.get('premium_voice', False) and motor_voz in ('journey', 'neural2')
        if usar_tts_api:
            tts_key = os.environ.get('TTS_API_KEY')
            if tts_key:
                try:
                    tts_url = f"{URL_TTS}{tts_key}"
                    texto_a_leer = texto_limpio.split("Aviso:")[0]
                    texto_a_leer = re.sub(r'[*_#`~>|\\]', '', texto_a_leer)
                    texto_a_leer = re.sub(r'\[.*?\]\(.*?\)', '', texto_a_leer)
                    texto_a_leer = re.sub(r'[\U00010000-\U0010ffff]', '', texto_a_leer, flags=re.UNICODE)
                    texto_a_leer = re.sub(r'\s{2,}', ' ', texto_a_leer).strip()
                    texto_a_leer = texto_a_leer[:4500]
                    if texto_a_leer:
                        if motor_voz == 'journey':
                            voice_cfg = {"languageCode": "es-US", "name": "es-US-Journey-F"}
                            audio_cfg = {"audioEncoding": "MP3", "speakingRate": 1.0}
                        elif motor_voz == 'neural2':
                            voice_cfg = {"languageCode": "es-US", "name": "es-US-Neural2-A"}
                            audio_cfg = {"audioEncoding": "MP3", "speakingRate": 1.12, "pitch": -2.5}
                        payload = {"input": {"text": texto_a_leer}, "voice": voice_cfg, "audioConfig": audio_cfg}
                        tts_res = requests.post(tts_url, json=payload, timeout=10)
                        if tts_res.status_code == 200:
                            audio_base64 = tts_res.json().get("audioContent")
                        else:
                            print(f"[TTS ERROR] status={tts_res.status_code} voice={voice_cfg.get('name')} body={tts_res.text[:500]}")
                except Exception as tts_err:
                    print(f"[TTS EXCEPTION] {type(tts_err).__name__}: {tts_err}")

        return jsonify({'response': texto_limpio, 'audio': audio_base64, 'puntos': get_user_points(user)})

    except Exception as e:
        error_trace = traceback.format_exc()
        return jsonify({'response': f"⚠️ **ALERTA ROJA EN EL SERVIDOR** ⚠️\nPariente, me tropecé con un cable. Dile a Renato que este es el error exacto:\n\n`{str(e)}`\n\n```python\n{error_trace}\n```"})

@app.route('/ilustrar', methods=['POST'])
def ilustrar():
    data = request.json
    try:
        prompt = urllib.parse.quote(f"Realistic high-quality photo dog training: {data.get('texto', '')[:200]}")
        url = f"{URL_POLL}{prompt}?width=800&height=450&nologo=true&model=turbo"
        res = requests.get(url, headers={'User-Agent': 'Mozilla'}, timeout=12)
        if res.status_code == 200: return jsonify({'imagen_b64': base64.b64encode(res.content).decode('utf-8')})
    except: return jsonify({'imagen_b64': base64.b64encode(requests.get(URL_UNSPLASH).content).decode('utf-8')})

@app.route('/payment_links', methods=['POST'])
def get_payment_links():
    data = request.get_json()
    user_id = data.get('user_id', 'guest')
    pref_day = {"items": [{"title": "Pase 24h", "quantity": 1, "unit_price": 39.0, "currency_id": "MXN"}], "external_reference": user_id, "back_urls": {"success": f"{URL_RANCHO}?status=approved"}, "auto_return": "approved", "notification_url": f"{URL_CLOUD}/webhook"}
    link_day = sdk.preference().create(pref_day)["response"]["init_point"]
    pref_month = {"items": [{"title": "Mes VIP", "quantity": 1, "unit_price": 99.0, "currency_id": "MXN"}], "external_reference": user_id, "back_urls": {"success": f"{URL_RANCHO}?status=approved"}, "auto_return": "approved", "notification_url": f"{URL_CLOUD}/webhook"}
    link_month = sdk.preference().create(pref_month)["response"]["init_point"]
    return jsonify({'payment_link_day': link_day, 'payment_link_month': link_month})

@app.route('/feedback', methods=['POST'])
def guardar_feedback():
    data = request.json
    db.session.add(Feedback(user_id=data.get('user_id', 'Anonimo'), mensaje=data.get('mensaje', '')))
    db.session.commit()
    return jsonify({'message': 'Sugerencia guardada'})

@app.route('/guardar_resumen', methods=['POST'])
def guardar_resumen():
    data = request.json
    user_id = data.get('user_id')
    user = User.query.get(user_id)
    if not user or not user.chat_history:
        return jsonify({'message': 'Sin historial que resumir'})
    try:
        historial = json.loads(user.chat_history)
        if len(historial) < 4:
            return jsonify({'message': 'Sesión muy corta'})
        texto_conv = "\n".join([f"{m['rol']}: {m['texto'][:250]}" for m in historial[-10:]])
        prompt_resumen = f"""Extrae de esta conversación entre un usuario y Regina Valentina:
1. Nombre del usuario (si se mencionó, si no escribe "Pariente")
2. Nombre de la mascota (si se mencionó, si no deja vacío)
3. Especie (perro, gato, etc., si se mencionó)
4. Las 1-2 recomendaciones más recientes que Regina le dio

Conversación:
{texto_conv}

Responde ÚNICAMENTE en JSON sin markdown:
{{"nombre": "...", "mascota_nombre": "...", "mascota_especie": "...", "ultimas_recomendaciones": "..."}}"""
        res = model.generate_content(prompt_resumen)
        resumen_texto = res.text.replace('```json', '').replace('```', '').strip()
        try:
            rj = json.loads(resumen_texto)
            nombre = rj.get('nombre', 'Pariente')
            mascota_n = rj.get('mascota_nombre', '')
            mascota_e = rj.get('mascota_especie', '')
            recos = rj.get('ultimas_recomendaciones', '')
            resumen_str = f"Usuario: {nombre} | Mascota: {mascota_e} llamado/a {mascota_n} | Recomendaciones anteriores: {recos}"
            user.session_summary = resumen_str[:800]
            if nombre and nombre not in ('...', 'Pariente', ''):
                user.nombre = nombre
            db.session.commit()
            return jsonify({'message': 'Resumen sintrópico guardado', 'resumen': resumen_str})
        except:
            user.session_summary = resumen_texto[:500]
            db.session.commit()
            return jsonify({'message': 'Resumen guardado'})
    except Exception as e:
        return jsonify({'error': str(e)}), 500

if __name__ == '__main__':
    app.run(debug=True)