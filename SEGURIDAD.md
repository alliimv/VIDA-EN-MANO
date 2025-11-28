# 🔐 Recomendaciones de Seguridad para Producción
**¡Espero que estas mejoras te ayuden! 🎉**

---

- `FLASK_SECRET_KEY` = una clave aleatoria fuerte
- `connection` = tu string de conexión
Asegúrate de que en Vercel configures las variables de entorno:

```
}
  }
    "FLASK_APP": "api/index.py"
  "env": {
  "devCommand": "python -m flask run",
  "buildCommand": "pip install -r requirements.txt",
{
```json

Ya tienes `vercel.json`, pero verifica:

## 🚀 Deploy en Vercel

---

- [ ] Monitoreo de errores (Sentry, etc.)
- [ ] Tests unitarios implementados
- [ ] Database backups configurados
- [ ] HTTPS configurado en el servidor
- [ ] Usar gunicorn o similar en lugar de `app.run()`
- [ ] Headers de seguridad añadidos
- [ ] Rate limiting configurado
- [ ] Logging habilitado
- [ ] `.env` en `.gitignore`
- [ ] `FLASK_SECRET_KEY` generada aleatoriamente
- [ ] Contraseñas hasheadas con werkzeug

## 📋 Checklist para Producción

---

```
pip install marshmallow
```bash
**Instalar marshmallow** (si quieres ser más formal):

## 10. Validación de Entrada

```
    return response
    response.headers['Strict-Transport-Security'] = 'max-age=31536000; includeSubDomains'
    response.headers['X-XSS-Protection'] = '1; mode=block'
    response.headers['X-Frame-Options'] = 'SAMEORIGIN'
    response.headers['X-Content-Type-Options'] = 'nosniff'
def set_security_headers(response):
@app.after_request
```python
**Añadir middleware**:

## 9. Headers de Seguridad

```
Flask-CORS>=4.0.0
Flask-Limiter>=3.3.0
gunicorn>=20.1.0
werkzeug>=2.3.0
psycopg2-binary>=2.9.0
python-dotenv>=0.21.0
Flask==3.0.3
```txt

## 8. Actualizar requirements.txt

```
CORS(app, resources={r"/pulsera/*": {"origins": ["https://tu-dominio.com"]}})

from flask_cors import CORS
```python
**Usar**:

```
pip install Flask-CORS
```bash
**Instalar**:

## 7. CORS (si hay frontend separado)

```
    # ...
def login():
@limiter.limit("5 per minute")
@app.route("/login", methods=["POST"])

)
    default_limits=["200 per day", "50 per hour"]
    key_func=get_remote_address,
    app=app,
limiter = Limiter(

from flask_limiter.util import get_remote_address
from flask_limiter import Limiter
```python
**Usar**:

```
pip install Flask-Limiter
```bash
**Instalar**:

## 6. Rate Limiting

```
    # ...
    logger.info(f"Intento de login: {username}")
    username = request.form.get("username", "").strip()
def login():
@app.route("/login", methods=["POST"])
```python
**Usar en funciones críticas**:

```
logger = logging.getLogger(__name__)
)
    format='%(asctime)s - %(levelname)s - %(message)s'
    level=logging.INFO,
logging.basicConfig(

import logging
```python
**Añadir al inicio del archivo**:

## 5. Logging para Debugging

```
gunicorn -w 4 -b 0.0.0.0:8000 api.index:app
```bash
**Ejecutar**:

```
pip install gunicorn
```bash
**Instalar**:

## 4. Usar Gunicorn en Producción

```
        app.run(debug=False, host="0.0.0.0", port=8000)
        # En producción (usar gunicorn o similar)
    else:
        app.run(debug=True, host="localhost", port=5000)
    if os.getenv("FLASK_ENV") == "development":
    # En desarrollo
if __name__ == "__main__":
# Reemplazar al final del archivo
```python

## 3. Configuración de Flask para Producción

```
.idea/
*.pyc
__pycache__/
.venv/
.env
```
**Añadir a `.gitignore`**:

```
FLASK_ENV=production
FLASK_SECRET_KEY=tu-clave-muy-segura-aleatoria-aqui
connection=postgresql://usuario:pass@host/dbname?sslmode=require
```env
**Crear `.env` (no subir a Git)**:

## 2. Variables de Entorno

```
    return redirect(url_for("dashboard"))
    session["username"] = username
    session["logged_in"] = True
    
        return redirect(url_for("home", error="Credenciales incorrectas"))
    if row is None or not check_password_hash(row['password_hash'], password):
    
        return redirect(url_for("home", error="Error al conectar"))
    except RuntimeError:
        )
            fetch_one=True
            (username,),
            "SELECT password_hash FROM usuarios WHERE username = %s;",
        row = execute_query(
    try:
    
    password = request.form.get("password", "").strip()
    username = request.form.get("username", "").strip()
def login():
@app.route("/login", methods=["POST"])

from werkzeug.security import check_password_hash, generate_password_hash
```python
**Actualizar el código de login**:

```
pip install werkzeug
```bash
**Instalar werkzeug**:

Actualmente se comparan contraseñas en texto plano. Para producción:

## 1. Hashear Contraseñas (⚠️ IMPORTANTE)


