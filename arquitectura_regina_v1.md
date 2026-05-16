# Arquitectura Regina Valentina — Blueprint Técnico v1

> **Destinado a:** Vera, Elena y cualquier IA futura que tome el relevo de este ecosistema.
> **Propósito:** Mapa técnico completo del sistema. Léelo de principio a fin antes de tocar una sola línea de código.
> **Generado por:** Claude Sonnet 4.6 — Mesa Redonda V1266 — Mayo 2026

---

## 1. Visión General del Ecosistema

Regina Valentina es una plataforma SaaS de consultoría veterinaria conductual potenciada por LLM, orientada al mercado hispanohablante (foco: CDMX y México). Su propuesta de valor central es una IA con personalidad norteña ("cowgirl ranchera"), que guía a dueños de mascotas a través de problemas conductuales, reforzando hábitos positivos mediante un motor de gamificación integrado.

El sistema se compone de tres capas desacopladas:

```
┌─────────────────────────────────────────────────────────┐
│  FRONTEND (Firebase Hosting)                            │
│  index.html · rescate.html · terminos.html              │
│  Vanilla JS + Firebase SDK v10 + Font Awesome           │
└────────────────────────┬────────────────────────────────┘
                         │ REST/JSON (HTTPS)
┌────────────────────────▼────────────────────────────────┐
│  BACKEND (Google Cloud Run)                             │
│  Python Flask 3.1 · Gunicorn · SQLAlchemy + SQLite      │
│  Gemini 2.5 Flash · Claude Sonnet/Haiku · MercadoPago  │
└────────────────────────┬────────────────────────────────┘
                         │ Admin SDK / OIDC
┌────────────────────────▼────────────────────────────────┐
│  INFRAESTRUCTURA (GCP)                                  │
│  Firebase Auth + Firestore · Secret Manager · WIF CI/CD│
└─────────────────────────────────────────────────────────┘
```

---

## 2. Estructura de Archivos

```
Regina_Valentina_App/
│
├── frontend/                        ← Servido por Firebase Hosting (CDN global)
│   ├── index.html                   ← Chat principal (~3 200 líneas; todo-en-uno)
│   ├── rescate.html                 ← Red de Rescate CDMX (~3 600 líneas)
│   ├── terminos.html                ← Términos y Condiciones (615 líneas)
│   ├── manifest.json                ← PWA manifest (nombre, íconos, display)
│   └── ReginaValentinaRostro.png   ← Foto de Regina (og:image, branding)
│
├── backend/
│   ├── app.py                       ← Servidor Flask completo (~1 223 líneas)
│   ├── base_robles_v3.sqlite        ← Base de datos SQLite (local/Cloud Run /tmp)
│   ├── requirements.txt             ← 47 dependencias Python
│   ├── Dockerfile                   ← Imagen python:3.11-slim, gunicorn, puerto 8080
│   ├── .env.example                 ← Plantilla de variables de entorno
│   └── .gcloudignore                ← Excluye .env, venv, __pycache__ del build
│
├── .github/workflows/
│   ├── deploy-backend.yml           ← CI/CD: Cloud Run (trigger: backend/**)
│   └── deploy-frontend.yml          ← CI/CD: Firebase Hosting (trigger: frontend/**)
│
├── firebase.json                    ← Hosting config: rewrites SPA, cache headers
├── .firebaserc                      ← Proyecto Firebase: "regina-valentina-app"
├── .gitignore                       ← Excluye .env, venv, *.sqlite, node_modules
└── arquitectura_regina_v1.md        ← ESTE ARCHIVO
```

### Convenciones clave
- **Todo el frontend está en archivos HTML monolíticos** (CSS + JS inline). No hay bundler, no hay `node_modules`. Esta decisión reduce la fricción operacional y permite iteraciones ultrarrápidas.
- **El backend es un solo `app.py`** con todos los endpoints, modelos ORM y lógica de negocio. Cuando supere ~2 000 líneas, se recomienda dividirlo en Blueprints Flask.

---

## 3. Flujo de Firebase Auth y Firestore

### 3.1 Autenticación

```
Usuario
  │
  ├─[Botón "Continuar con Google"]
  │   signInWithGoogle() → firebase.auth().signInWithPopup(GoogleAuthProvider)
  │   Firebase devuelve: user.uid, user.email, user.displayName, user.photoURL
  │
  ├─ POST /registro_google  { firebase_uid, email, nombre, foto_url }
  │   Backend:
  │     1. Busca User por id == firebase_uid
  │     2. Si no existe → crea User con defaults (free, 0 pts)
  │     3. Si director email → is_admin = True automáticamente
  │     4. Devuelve: { status, is_premium, is_admin, puntos, nombre }
  │
  └─ Frontend guarda en localStorage:
       regina_user_id     ← firebase_uid (PK en SQLite)
       regina_registrado  ← true
       regina_nombre      ← nombre
       regina_foto_url    ← URL foto Google
       regina_is_premium  ← bool
       regina_is_admin    ← bool
       regina_is_director ← bool (email == direccion@roblesbienestar.com)
```

### 3.2 Sesión posterior (recarga de página)

Al cargar `index.html`, `onAuthStateChanged(auth, user)` se dispara automáticamente:
- Si `user != null`: reutiliza `user.uid` sin ir al backend (localStorage ya tiene el estado).
- Si `user == null`: muestra el modal de auth.

### 3.3 Firestore (uso acotado)

Firestore **no** es la base de datos principal. Su uso está limitado a:

| Colección               | Propósito                              | Escrito por      |
|-------------------------|----------------------------------------|------------------|
| `suscriptores_blog`     | Newsletter (email + timestamp)         | Frontend JS      |
| *(Rescate — informes)*  | Reportes de mascotas (pendiente audit) | rescate.html     |

El grueso del estado de usuario (puntos, historial, premium) vive en **SQLite vía backend**.

### 3.4 Firebase Admin SDK (backend)

El backend usa `firebase-admin` para verificar tokens en operaciones sensibles (si aplica) y para escribir a Firestore desde servidor. Las credenciales se inyectan via Secret Manager en Cloud Run — nunca un archivo JSON hardcodeado.

---

## 4. Interconexión Frontend ↔ Backend ↔ LLM

### 4.1 Endpoint principal: `POST /chat`

```
Frontend (enviarMensaje)
  │
  ├─ Construye payload:
  │    { user_id, mensaje, imagen_b64?, cerebro_llm, premium_voice }
  │
  └─ fetch(`${API_URL}/chat`, { method:'POST', body: JSON.stringify(payload) })

Backend (app.py → /chat)
  │
  ├─ 1. Valida user_id → busca User en SQLite
  ├─ 2. Verifica cuota (free: 3 mensajes)
  ├─ 3. Construye system_prompt (persona Regina + resumen de sesión)
  ├─ 4. Añade historial (últimos 14 mensajes del chat_history)
  ├─ 5. Selecciona LLM según cerebro_llm:
  │       "gemini"  → google.generativeai (Gemini 2.5 Flash)
  │       "claude"  → anthropic.Anthropic (Claude Sonnet 4.6)
  ├─ 6. Llama al LLM → extrae respuesta de texto
  ├─ 7. Regex [LOGRO: <skill> | PUNTOS: <n>] → actualiza puntos en DB
  ├─ 8. Guarda mensaje en chat_history (JSON, max 14 entradas rolling)
  ├─ 9. Si premium_voice=true → Google TTS API → audio base64
  └─ 10. Devuelve { respuesta, audio_base64?, puntos:{} }

Frontend
  ├─ Renderiza burbuja de chat con respuesta
  ├─ Si audio_base64 → guarda en data-audio del elemento DOM
  └─ actualizarInsigniasVisuales(puntos) → actualiza barras/badges
```

### 4.2 Selección de LLM en tiempo real

El usuario puede cambiar de modelo en el panel de ajustes (`sel-cerebro-llm`). El valor se envía en cada request; el backend no tiene estado del modelo elegido entre requests. Ambos modelos reciben **exactamente el mismo system prompt**, garantizando consistencia de personalidad.

### 4.3 Variables de entorno del backend (Cloud Run Secret Manager)

```
GEMINI_API_KEY          → Google AI Studio
ANTHROPIC_API_KEY       → Anthropic Console
TTS_API_KEY             → Google Cloud TTS API
MERCADOPAGO_ACCESS_TOKEN → MercadoPago Dashboard
SECRET_KEY              → Flask sessions (reservado)
```

**Nunca** se commitean al repositorio. En dev local, se cargan desde `backend/.env` (excluido por `.gitignore`). En producción, Cloud Run los inyecta desde Secret Manager.

---

## 5. Motor de Gamificación

### 5.1 Arquitectura General

```
LLM response (texto crudo)
     │
     └─ Regex: r'\[LOGRO:\s*([^|]+)\|?\s*PUNTOS:\s*(\d+)\]'
              ↓
         Extrae: skill_name, points_value
              ↓
         Mapa normalizado:
           "Líder de la Manada"   → user.pts_lider
           "Maestro Zen"          → user.pts_zen
           "Autocontrol"          → user.pts_autocontrol
           "Atleta Perruno"       → user.pts_atleta
           "Socio Supremo"        → user.pts_socio
              ↓
         UPDATE User SET pts_X = pts_X + n WHERE id = user_id
              ↓
         Return puntos dict → Frontend → actualizarInsigniasVisuales()
```

### 5.2 Las 5 Habilidades

| Skill | Emoji | Concepto | Campo DB |
|-------|-------|----------|----------|
| Líder de la Manada | 🟢 | Liderazgo calmo, guía sin coerción | `pts_lider` |
| Maestro Zen | 🔵 | Ambiente libre de estrés, calma | `pts_zen` |
| Autocontrol | 🔴 | Consistencia y paciencia del humano | `pts_autocontrol` |
| Atleta Perruno | 🟠 | Ejercicio físico y enriquecimiento | `pts_atleta` |
| Socio Supremo | 🌟 | Vínculo emocional profundo | `pts_socio` |

### 5.3 Flujo Visual en Frontend

```javascript
actualizarInsigniasVisuales(puntos) {
    // Para cada skill: actualiza barra de progreso CSS width %
    // Si puntos >= umbral → activa insignia (badge diamond animado)
    // Si todas las insignias activas → desbloquea "Master Trophy" 🏆
}
```

Los umbrales de insignia y el diseño de las barras se gestionan completamente en el frontend (CSS + JS). El backend solo persiste enteros crudos.

### 5.4 Cupones de Gamificación (V1264)

El sistema de cupones tiene dos modos:

**A) Cupones estándar** (creados en `/panel-robles`):
```python
PromoCode(codigo=str, dias_regalo=int, usos_restantes=int, activo=bool, tipo='estandar')
```
Canjeables en `/canjear_codigo`. Al canjear: `user.is_premium = True`, `user.premium_until = now + timedelta(dias)`.

**B) Cupón Maestro / Gran Premio** (V1264 — recompensa máxima de gamificación):
- Endpoint: `POST /generar_cupon_maestro` (requiere autenticación Firebase)
- **Anti-fraude**: el backend valida desde DB que el usuario tiene las 5 insignias completadas. El frontend **nunca** puede falsificar esto.
- El cupón se genera con `tipo='gran_premio'`, `usos_restantes=1`, `expires_at = now + 7 días`.
- Se vincula al usuario via `owner_user_id`.
- Es de uso único y con expiración; si expira sin canjearse, queda inactivo.

### 5.5 Gemas y Sistema de Contador V1265

Las gemas son la capa visual más reciente del motor. Se renderizan en el frontend como íconos premium asociados a las insignias desbloqueadas. No tienen un campo propio en DB — se derivan del estado de los `pts_*`. La lógica de visualización vive en `actualizarInsigniasVisuales()`.

---

## 6. Red de Rescate — `rescate.html`

### 6.1 Propósito

Tablón comunitario para reportar y buscar mascotas extraviadas en CDMX. Es una funcionalidad secundaria pero estratégica: genera tráfico orgánico y refuerza el posicionamiento de "comunidad animal responsable".

### 6.2 Flujo de Publicación con Moderación

```
Usuario llena formulario (nombre, especie, zona CDMX, foto, contacto)
  │
  └─ POST /moderate  { texto: descripcion_completa }
        │
        Backend → Claude Haiku (modelo rápido y económico)
        │   System prompt: "Eres moderador. Detecta: fraude, extorsión,
        │    venta de animales, presión económica, odio, reportes falsos."
        │
        ├─ Claude responde: { decision: "APROBAR" | "RECHAZAR", razon }
        │
        ├─ APROBAR → reporte publicado en Firestore / estado activo
        └─ RECHAZAR → reporte en "cuarentena" → revisión manual admin
```

### 6.3 Flujo de Búsqueda y Contacto

- Los reportes listados son filtrados por: tipo (perdido/encontrado), zona, especie, fecha.
- Contacto directo: el solicitante ve teléfono/email del reportante (sin intermediarios).
- Botón "Compartir a WhatsApp" genera URL `wa.me/send?text=...` con la ficha del animal.

### 6.4 Régimen Legal (Cláusula 10 de Términos)

`rescate.html` opera bajo una exención de responsabilidad robusta: la plataforma es un **canal pasivo de información**, no una agencia de rescate. Robles Bienestar no garantiza recuperación ni responde por fraudes entre usuarios. La responsabilidad máxima está contractualmente capeada al último pago del usuario o $0, lo que sea mayor.

---

## 7. Stack de Despliegue y CI/CD

### 7.1 Topología de Ambientes

| Ambiente | Frontend | Backend |
|----------|----------|---------|
| **Producción** | Firebase Hosting (`reginavalentina.com`) | Cloud Run (`academia-robles-cloudrun`) |
| **Desarrollo local** | `file://` o Live Server | `python app.py` (puerto 5000) |

El frontend detecta el ambiente dinámicamente:
```javascript
const API_URL = (hostname === 'localhost' || hostname === '127.0.0.1')
    ? 'http://127.0.0.1:5000'
    : 'https://regina-valentina-XXXX-uc.a.run.app';
```

### 7.2 Pipeline de CI/CD (GitHub Actions + WIF)

**Workload Identity Federation** elimina las claves de cuenta de servicio estáticas. El flujo es:

```
git push → main
  │
  ├─[backend/** cambió]→ deploy-backend.yml
  │     1. google-github-actions/auth@v2 (OIDC token)
  │     2. gcloud run deploy --source ./backend
  │     3. Cloud Build construye imagen Docker
  │     4. Cloud Run despliega nueva revisión (zero-downtime)
  │
  └─[frontend/** cambió]→ deploy-frontend.yml
        1. google-github-actions/auth@v2 (OIDC token)
        2. npm install -g firebase-tools
        3. firebase deploy --only hosting
        4. CDN invalidation automática
```

Ambos workflows autentican con la misma cuenta de servicio:
`github-deploy-regina@academia-robles-cloudrun.iam.gserviceaccount.com`

### 7.3 Dockerfile (backend)

```dockerfile
FROM python:3.11-slim          # imagen base ligera
WORKDIR /app
COPY requirements.txt .
RUN pip install --no-cache-dir -r requirements.txt
COPY . .
EXPOSE 8080
CMD ["gunicorn", "--bind", "0.0.0.0:${PORT:-8080}", "--workers", "1", "--timeout", "120", "app:app"]
```

**Nota importante**: `--workers 1` es intencional. SQLite no soporta escrituras concurrentes de múltiples workers. Si se escala a PostgreSQL, se puede subir a 2-4 workers.

---

## 8. Modelo de Datos (SQLAlchemy ORM)

### 8.1 Tabla `user`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | String(50) PK | Firebase UID |
| `email` | String(120) unique | Email del usuario |
| `password_hash` | String(256) | Solo para auth legacy email/password |
| `nombre` | String(50) | Nombre para mostrar |
| `pais` | String(100) | Detectado via ip-api.com |
| `message_count` | Integer | Total mensajes enviados |
| `is_premium` | Boolean | Estado VIP activo |
| `premium_until` | DateTime | Expiración del VIP |
| `is_admin` | Boolean | Acceso al panel `/panel-robles` |
| `is_banned` | Boolean | Usuario suspendido |
| `pago_real` | Boolean | Pagó (vs recibió gift) |
| `chat_history` | Text | JSON array, rolling 14 msgs |
| `session_summary` | Text | Memo de sesión anterior (LLM generado) |
| `pts_lider` | Integer | Puntos Líder de la Manada |
| `pts_zen` | Integer | Puntos Maestro Zen |
| `pts_autocontrol` | Integer | Puntos Autocontrol |
| `pts_atleta` | Integer | Puntos Atleta Perruno |
| `pts_socio` | Integer | Puntos Socio Supremo |

### 8.2 Tabla `promo_code`

| Campo | Tipo | Descripción |
|-------|------|-------------|
| `id` | Integer PK | Auto-increment |
| `codigo` | String(50) unique | Código alfanumérico |
| `dias_regalo` | Integer | Días de VIP que otorga |
| `usos_restantes` | Integer | Decrements on each use |
| `activo` | Boolean | Puede desactivarse manualmente |
| `tipo` | String(50) | 'estandar', 'gran_premio' |
| `owner_user_id` | String(50) | FK a User.id (cupón maestro) |
| `expires_at` | DateTime nullable | Expira automáticamente |

### 8.3 Tablas auxiliares

- **`feedback`**: Buzón de sugerencias/quejas. Campos: `id, user_id, mensaje, fecha`.
- **`blog_post`**: Artículos del blog. Campos: `id, titulo, contenido (HTML), fecha, slug, autor`.

---

## 9. Sistema de Pagos (MercadoPago)

### 9.1 Flujo de Checkout

```
Frontend → POST /payment_links { plan: '24h' | '30d', user_id }
  │
  Backend → MercadoPago SDK → preference.create({
  │    items: [{ title, unit_price: 39 | 99, currency_id: 'MXN' }],
  │    back_urls: { success, failure, pending },
  │    notification_url: 'https://.../webhook'
  │  })
  │
  └─ Devuelve { init_point: URL de checkout MercadoPago }

Usuario completa pago en MercadoPago
  │
  MercadoPago → POST /webhook { data: { id: payment_id } }
  │
  Backend:
    1. SDK.payment.get(payment_id)
    2. Si status == "approved":
       user.is_premium = True
       user.premium_until = now + timedelta(hours=24 | days=30)
       user.pago_real = True
       db.commit()
```

**Sin auto-renovación**: MercadoPago no gestiona suscripciones recurrentes en este setup. El usuario debe re-comprar al expirar.

---

## 10. Panel de Administración

### 10.1 Acceso

URL: `/panel-robles?admin_id=<firebase_uid>`
El backend valida que `User.is_admin == True` para el UID dado. La auto-elevación ocurre al registrarse con `direccion@roblesbienestar.com`.

### 10.2 Capacidades

| Función | Endpoint | Descripción |
|---------|----------|-------------|
| Dashboard BI | `GET /panel-robles` | MRR, funnel conversión, top países |
| Crear código promo | `POST /admin/crear_codigo` | Genera PromoCode configurable |
| Otorgar VIP | `POST /admin/hacer_premium` | Premia a usuario por email |
| Banear/desbanear | `POST /admin/banear` / desbanear | Suspende o reactiva cuenta |
| Purgar fantasmas | `POST /admin/purgar_fantasmas` | Elimina cuentas sin actividad |
| Generar artículo | `POST /admin/generar_articulo` | Gemini escribe post del blog |
| Autopiloto blog | `POST /admin/autopiloto_blog` | Blog basado en tendencias |
| Borrar artículo | `POST /admin/borrar_articulo` | Elimina post por id |
| Exportar CSV | `GET /admin/exportar_csv` | Descarga base de usuarios |
| Ver cuarentena | *(Firestore)* | Moderación Red de Rescate |

---

## 11. Accesibilidad

El frontend implementa 4 modos de accesibilidad persistidos en `localStorage`:

| Modo | Activación CSS | Efecto |
|------|---------------|--------|
| Dyslexia Mode | `body.dyslexia-mode` | Fuente OpenDyslexic, espaciado aumentado |
| Large Text | `body.large-text-mode` | 1.45rem mensajes, 1.35rem input |
| High Contrast | `body.high-contrast-mode` | Fondo negro, texto blanco, bordes amarillo |
| LSM (Lengua de Señas Mexicana) | `body.lsm-mode` | Fuente Gallaudet, 2.2rem |

Cada toggle persiste su estado entre sesiones. Los modos son acumulables (ej. Dyslexia + High Contrast).

---

## 12. Consideraciones de Seguridad

### 12.1 Fortalezas

- **WIF en CI/CD**: Cero claves estáticas de cuenta de servicio en el repo.
- **CORS whitelist**: Solo dominios conocidos pueden llamar al backend.
- **Firebase Auth**: Proveedor de identidad industry-standard (Google OAuth2).
- **Admin gate**: Endpoints sensibles validan `is_admin` en DB, nunca en frontend.
- **Cupón anti-fraude**: `/generar_cupon_maestro` valida puntos desde DB, no desde parámetros del request.

### 12.2 Deuda de Seguridad Conocida

- **Sin rate limiting por IP**: El endpoint `/chat` depende de la cuota por usuario, pero no bloquea spam desde múltiples cuentas.
- **SQLite sin cifrado en reposo**: Aceptable en Cloud Run (efímero), pero riesgo en desarrollo local.
- **No hay validación CSRF**: El frontend es SPA sin cookies de sesión, lo que reduce el riesgo, pero no elimina el vector.
- **Tracebacks en errores**: Algunos endpoints devuelven `str(exception)` al frontend en caso de error — expone información de implementación.

---

## 13. Glosario Rápido

| Término | Significado en este ecosistema |
|---------|-------------------------------|
| **UID** | Firebase User ID — PK universal en SQLite |
| **VIP** | Estado premium activo (`is_premium=True`) |
| **Logro** | Etiqueta `[LOGRO: X | PUNTOS: N]` en respuesta LLM |
| **Cupón Maestro** | PromoCode de tipo `gran_premio`, 1 uso, 7 días, recompensa máxima |
| **Fantasma** | Usuario con 0 mensajes y sin email (purgar con seguridad) |
| **Bocina** | Botón de reproducción TTS en burbuja de chat |
| **Paywall voluntario** | Prompt de upgrade que aparece al agotar 3 mensajes free |
| **WIF** | Workload Identity Federation — autenticación GCP sin claves estáticas |
| **Cuarentena** | Estado de reporte de rescate pendiente revisión manual |

---

## 14. Roadmap Técnico Recomendado

1. **Rate limiting**: Implementar `Flask-Limiter` con Redis en Cloud Run para proteger `/chat` y `/registro_google`.
2. **Blueprints Flask**: Dividir `app.py` en módulos: `auth.py`, `chat.py`, `admin.py`, `blog.py`, `rescate.py`.
3. **PostgreSQL**: Migrar SQLite → Cloud SQL PostgreSQL para permitir múltiples workers y backups gestionados.
4. **Alembic**: Reemplazar los `ALTER TABLE` adhoc con migraciones versionadas.
5. **Test suite**: Añadir tests de integración para `/chat` (gamificación), `/webhook` (pagos), `/moderate` (moderación).
6. **Error handling centralizado**: Blueprint de errores Flask que devuelva JSON estructurado sin tracebacks.
7. **Logging estructurado**: Reemplazar `print()` con `logging` de Python + Cloud Logging sink.
8. **PWA offline**: Implementar Service Worker con cache strategy para `index.html` y assets estáticos.

---

*Documento generado automáticamente por Claude Sonnet 4.6 — Mayo 2026 — Academia Robles Bienestar*
*No editar manualmente. Para actualizar, pide a la IA que regenere desde el estado actual del código.*
