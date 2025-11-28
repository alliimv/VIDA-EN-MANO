# 💡 Ejemplos de Mejoras Opcionales (Nivel Avanzado)

Este archivo contiene código opcional para mejorar aún más tu aplicación.

---

## 1. Validación de Datos con Marshmallow

**Instalar**:
```bash
pip install marshmallow
```

**Crear schemas (agregar antes de las rutas)**:
```python
from marshmallow import Schema, fields, validate, ValidationError

class LecturaSchema(Schema):
    """Schema para validar datos de lectura de pulsera"""
    ritmo_cardiaco = fields.Int(required=True, validate=validate.Range(min=0, max=200))
    temperatura_c = fields.Float(required=True, validate=validate.Range(min=30, max=45))
    esta_puesta = fields.Bool()
    comentario = fields.Str()

lectura_schema = LecturaSchema()

class PacienteSchema(Schema):
    """Schema para validar datos de paciente"""
    nombre = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    apellido_paterno = fields.Str(required=True, validate=validate.Length(min=1, max=100))
    apellido_materno = fields.Str()
    fecha_nacimiento = fields.Date()

paciente_schema = PacienteSchema()
```

**Usar en rutas**:
```python
@app.route("/pulsera/<int:id_pulsera>/lectura", methods=["POST"])
def insertar_lectura_pulsera(id_pulsera):
    data = request.get_json(silent=True)
    
    if data is None:
        return jsonify({"error": "Body debe ser JSON"}), 400
    
    try:
        validated_data = lectura_schema.load(data)
    except ValidationError as err:
        return jsonify({"errors": err.messages}), 400
    
    # Proceder con datos validados
    # ...
```

---

## 2. Logging Completo

**Crear `logging_config.py`**:
```python
import logging
import logging.handlers
import os

def setup_logging():
    """Configura logging para desarrollo y producción"""
    
    # Crear directorio de logs si no existe
    if not os.path.exists("logs"):
        os.mkdir("logs")
    
    # Logger principal
    logger = logging.getLogger("app")
    logger.setLevel(logging.DEBUG if os.getenv("FLASK_ENV") == "development" else logging.INFO)
    
    # Formato
    formatter = logging.Formatter(
        '%(asctime)s - %(name)s - %(levelname)s - %(message)s'
    )
    
    # Handler para archivo
    file_handler = logging.handlers.RotatingFileHandler(
        "logs/app.log",
        maxBytes=10485760,  # 10MB
        backupCount=10
    )
    file_handler.setFormatter(formatter)
    logger.addHandler(file_handler)
    
    # Handler para consola
    console_handler = logging.StreamHandler()
    console_handler.setFormatter(formatter)
    logger.addHandler(console_handler)
    
    return logger

# En index.py
from logging_config import setup_logging
logger = setup_logging()
```

**Usar en el código**:
```python
@app.route("/login", methods=["POST"])
def login():
    username = request.form.get("username", "").strip()
    logger.info(f"Intento de login de usuario: {username}")
    
    try:
        row = execute_query(...)
    except RuntimeError as e:
        logger.error(f"Error en BD durante login: {e}")
        return redirect(url_for("home", error="Error de servidor"))
    
    logger.info(f"Login exitoso: {username}")
    session["logged_in"] = True
    return redirect(url_for("dashboard"))
```

---

## 3. Rate Limiting

**Instalar**:
```bash
pip install Flask-Limiter
```

**Configurar en index.py**:
```python
from flask_limiter import Limiter
from flask_limiter.util import get_remote_address

limiter = Limiter(
    app=app,
    key_func=get_remote_address,
    default_limits=["200 per day", "50 per hour"]
)

# Proteger login específicamente
@app.route("/login", methods=["POST"])
@limiter.limit("5 per minute")
def login():
    # ...

# Proteger API
@app.route("/pulsera/<int:id_pulsera>/lectura", methods=["POST"])
@limiter.limit("10 per minute")
def insertar_lectura_pulsera(id_pulsera):
    # ...
```

---

## 4. Caché de Datos

**Instalar**:
```bash
pip install Flask-Caching
```

**Configurar**:
```python
from flask_caching import Cache

cache = Cache(app, config={'CACHE_TYPE': 'simple'})

@app.route("/dashboard")
@login_required
@cache.cached(timeout=300)  # Cache 5 minutos
def dashboard():
    query = """..."""
    rows = execute_query(query)
    # ...
```

---

## 5. Tests Unitarios

**Crear `test_index.py`**:
```python
import unittest
from api.index import app, determinar_estado_paciente, calcular_edad
from datetime import date

class TestApp(unittest.TestCase):
    def setUp(self):
        self.app = app
        self.app.config['TESTING'] = True
        self.client = self.app.test_client()
    
    def test_home_not_logged_in(self):
        """Test que home redirige cuando no está logueado"""
        response = self.client.get('/')
        self.assertEqual(response.status_code, 200)
    
    def test_determinar_estado_critico(self):
        """Test estado crítico"""
        estado = determinar_estado_paciente(40.5, 75, True)
        self.assertEqual(estado, "rojo")
    
    def test_determinar_estado_estable(self):
        """Test estado estable"""
        estado = determinar_estado_paciente(37.0, 75, True)
        self.assertEqual(estado, "verde")
    
    def test_determinar_estado_advertencia(self):
        """Test estado advertencia"""
        estado = determinar_estado_paciente(37.0, 75, False)
        self.assertEqual(estado, "azul")
    
    def test_calcular_edad(self):
        """Test cálculo de edad"""
        fecha = date(2000, 1, 15)
        edad = calcular_edad(fecha)
        self.assertIsNotNone(edad)
        self.assertGreater(edad, 20)

if __name__ == '__main__':
    unittest.main()
```

**Ejecutar tests**:
```bash
python -m pytest test_index.py -v
```

---

## 6. Modelos con SQLAlchemy (Opcional)

Si quieres simplificar aún más el código:

**Instalar**:
```bash
pip install Flask-SQLAlchemy
```

**Configurar**:
```python
from flask_sqlalchemy import SQLAlchemy

app.config['SQLALCHEMY_DATABASE_URI'] = os.getenv('connection')
db = SQLAlchemy(app)

class Paciente(db.Model):
    __tablename__ = 'pacientes'
    
    id_paciente = db.Column(db.Integer, primary_key=True)
    nombre = db.Column(db.String(100), nullable=False)
    apellido_paterno = db.Column(db.String(100), nullable=False)
    apellido_materno = db.Column(db.String(100))
    fecha_nacimiento = db.Column(db.Date)
    
    pulseras = db.relationship('Pulsera', backref='paciente')

class Pulsera(db.Model):
    __tablename__ = 'pulseras'
    
    id_pulsera = db.Column(db.Integer, primary_key=True)
    id_paciente = db.Column(db.Integer, db.ForeignKey('pacientes.id_paciente'))
    
    lecturas = db.relationship('Lectura', backref='pulsera')

class Lectura(db.Model):
    __tablename__ = 'lecturas'
    
    id_lectura = db.Column(db.Integer, primary_key=True)
    id_pulsera = db.Column(db.Integer, db.ForeignKey('pulseras.id_pulsera'))
    ritmo_cardiaco = db.Column(db.Integer)
    temperatura_c = db.Column(db.Float)
    esta_puesta = db.Column(db.Boolean)
    momento_lectura = db.Column(db.DateTime, server_default=db.func.now())
```

**Usar en rutas**:
```python
@app.route("/dashboard")
@login_required
def dashboard():
    pacientes = Paciente.query.all()
    
    datos = []
    for p in pacientes:
        pulsera = p.pulseras[0] if p.pulseras else None
        ultima_lectura = pulsera.lecturas[0] if pulsera and pulsera.lecturas else None
        
        datos.append({
            "id_paciente": p.id_paciente,
            "nombre": f"{p.nombre} {p.apellido_paterno}",
            # ...
        })
    
    return render_template("dashboard.html", pacientes=datos)
```

---

## 7. Variables de Entorno Organizadas

**Crear `config.py`**:
```python
import os
from dotenv import load_dotenv

load_dotenv()

class Config:
    """Configuración base"""
    DEBUG = False
    TESTING = False
    SECRET_KEY = os.getenv("FLASK_SECRET_KEY", "dev-key")
    SQLALCHEMY_DATABASE_URI = os.getenv("connection")

class DevelopmentConfig(Config):
    """Configuración de desarrollo"""
    DEBUG = True
    TESTING = False

class ProductionConfig(Config):
    """Configuración de producción"""
    DEBUG = False
    TESTING = False

class TestingConfig(Config):
    """Configuración de testing"""
    DEBUG = True
    TESTING = True
    SQLALCHEMY_DATABASE_URI = "sqlite:///:memory:"

def get_config():
    env = os.getenv("FLASK_ENV", "development")
    if env == "production":
        return ProductionConfig
    elif env == "testing":
        return TestingConfig
    else:
        return DevelopmentConfig

# En index.py
from config import get_config
app.config.from_object(get_config())
```

---

## 8. Decoradores Personalizados

```python
from functools import wraps
import time

def timing(f):
    """Decorador para medir tiempo de ejecución"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        start = time.time()
        result = f(*args, **kwargs)
        elapsed = time.time() - start
        logger.info(f"{f.__name__} tardó {elapsed:.2f}s")
        return result
    return decorated_function

def async_task(f):
    """Decorador para tareas asincrónicas (requiere Celery)"""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        # Para tareas en background
        return f.delay(*args, **kwargs)
    return decorated_function

# Usar
@app.route("/dashboard")
@login_required
@timing
def dashboard():
    # ...
```

---

## 9. Manejo de Excepciones Personalizado

```python
class DatabaseError(Exception):
    """Error de base de datos"""
    pass

class ValidationError(Exception):
    """Error de validación"""
    pass

@app.errorhandler(DatabaseError)
def handle_db_error(e):
    logger.error(f"DB Error: {e}")
    return jsonify({"error": "Error en base de datos"}), 500

@app.errorhandler(ValidationError)
def handle_validation_error(e):
    return jsonify({"error": str(e)}), 400

@app.errorhandler(404)
def handle_not_found(e):
    return render_template("404.html"), 404

@app.errorhandler(500)
def handle_internal_error(e):
    logger.error(f"Internal error: {e}")
    return render_template("500.html"), 500
```

---

## 10. Blueprints para Organizar Código

**Crear `auth.py`**:
```python
from flask import Blueprint, request, redirect, url_for, session
from datetime import datetime
auth = Blueprint('auth', __name__)

@auth.route("/login", methods=["POST"])
def login():
    # ...
```

**Crear `api.py`**:
```python
from flask import Blueprint, jsonify, request
api = Blueprint('api', __name__, url_prefix='/api')

@api.route("/pulsera/<int:id>/lectura", methods=["POST"])
def lectura(id):
    # ...
```

**En index.py**:
```python
from auth import auth
from api import api

app.register_blueprint(auth)
app.register_blueprint(api)
```

---

## 📋 Resumen de Mejoras Opcionales

| Mejora | Complejidad | Beneficio | Prioridad |
|--------|-------------|----------|-----------|
| Validación con Marshmallow | Media | Alto | Alta |
| Logging completo | Media | Alto | Alta |
| Rate Limiting | Baja | Medio | Media |
| Caché | Media | Medio | Media |
| Tests | Alta | Alto | Alta |
| SQLAlchemy | Alta | Alto | Media |
| Config organizado | Baja | Medio | Media |
| Decoradores | Baja | Bajo | Baja |
| Error handlers | Baja | Medio | Alta |
| Blueprints | Media | Alto | Media |

---

**Estas mejoras son opcionales pero recomendadas para producción. ¡Elige las que más te interesen!** 🚀

