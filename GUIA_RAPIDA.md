# 📖 Guía Rápida de Cambios

## 🎯 ¿Qué Cambió?

### Nuevas Funciones Auxiliares

#### 1. `execute_query(query, params=None, fetch_one=False)`
Ejecuta una consulta SELECT de forma segura.

**Uso**:
```python
# Obtener múltiples filas
rows = execute_query("SELECT * FROM pacientes;")

# Obtener una sola fila
row = execute_query(
    "SELECT * FROM usuarios WHERE username = %s;",
    ("admin",),
    fetch_one=True
)
```

#### 2. `execute_update(query, params=None)`
Ejecuta INSERT/UPDATE/DELETE y hace commit automáticamente.

**Uso**:
```python
row = execute_update(
    "INSERT INTO pacientes (...) VALUES (...) RETURNING id_paciente;",
    (nombre, apellido, fecha)
)
id_paciente = row[0]
```

#### 3. `@login_required`
Decorador para proteger rutas.

**Uso**:
```python
@app.route("/dashboard")
@login_required
def dashboard():
    # Esta ruta redirige a login si no está autenticado
    pass
```

#### 4. `determinar_estado_paciente(temperatura, ritmo, pulsera_puesta)`
Calcula el estado del semáforo.

**Uso**:
```python
estado = determinar_estado_paciente(37.2, 75, True)
# Retorna: 'verde', 'azul' o 'rojo'
```

#### 5. `calcular_edad(fecha_nacimiento)`
Calcula la edad de una persona.

**Uso**:
```python
edad = calcular_edad(row["fecha_nacimiento"])
```

---

## 🔄 Cómo Usar Las Nuevas Funciones

### Antes (Código Antiguo)
```python
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("home"))
    
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT * FROM pacientes;")
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return f"Error: {e}"
    
    # ... procesar datos ...
```

### Después (Código Nuevo)
```python
@app.route("/dashboard")
@login_required
def dashboard():
    try:
        rows = execute_query("SELECT * FROM pacientes;")
    except RuntimeError as e:
        return f"Error: {e}", 500
    
    # ... procesar datos ...
```

---

## 📚 Ejemplos de Uso

### Insertar un Paciente
```python
row = execute_update(
    """INSERT INTO pacientes (nombre, apellido_paterno, fecha_nacimiento)
       VALUES (%s, %s, %s)
       RETURNING id_paciente;""",
    ("Juan", "Pérez", "2000-01-15")
)
id_paciente = row[0]
```

### Obtener Datos de Usuario
```python
user = execute_query(
    "SELECT * FROM usuarios WHERE username = %s;",
    ("admin",),
    fetch_one=True
)

if user:
    print(user['password_hash'])
```

### Obtener Últimas Lecturas
```python
lecturas = execute_query(
    """SELECT * FROM lecturas 
       WHERE id_pulsera = %s 
       ORDER BY momento_lectura DESC 
       LIMIT 10;""",
    (5,)
)

for lectura in lecturas:
    print(f"Ritmo: {lectura['ritmo_cardiaco']}")
```

### Actualizar una Pulsera
```python
execute_update(
    "UPDATE pulseras SET id_paciente = %s WHERE id_pulsera = %s;",
    (123, 456)
)
```

---

## 🛡️ Manejo de Errores

Todas las funciones auxiliares lanzan `RuntimeError`, así que usa:

```python
try:
    datos = execute_query("SELECT ...")
except RuntimeError as e:
    logger.error(f"Error en BD: {e}")
    return render_template("error.html", mensaje=str(e)), 500
```

---

## 🔐 Rutas Protegidas

Estas rutas ahora usan `@login_required`:
- `/dashboard`
- `/semaforo`
- `/agregar-paciente`

**Nota**: Si intentas acceder sin estar logueado, te redirige automáticamente a `/`.

---

## 📱 API Endpoints

### Insertar Lectura
```bash
POST /pulsera/5/lectura
Content-Type: application/json

{
  "ritmo_cardiaco": 75,
  "temperatura_c": 37.2,
  "esta_puesta": true,
  "comentario": "Lectura normal"
}
```

**Respuesta (201)**:
```json
{
  "message": "Lectura insertada correctamente",
  "id_pulsera": 5,
  "id_lectura": 123,
  "momento_lectura": "2025-11-27T10:30:45.123456"
}
```

### Obtener Lecturas
```bash
GET /pulsera/5/lecturas?limit=10
```

**Respuesta (200)**:
```json
{
  "id_pulsera": 5,
  "count": 10,
  "lecturas": [
    {
      "id_lectura": 123,
      "momento_lectura": "2025-11-27T10:30:45.123456",
      "ritmo_cardiaco": 75,
      "temperatura_c": 37.2,
      "esta_puesta": true,
      "comentario": "Lectura normal"
    }
    // ... más lecturas ...
  ]
}
```

---

## 🧪 Testing Rápido

### Probar la conexión
```bash
curl http://localhost:5000/debug-conn
# Respuesta: Conexión OK. NOW() = 2025-11-27 10:30:45.123456
```

### Probar login
```bash
curl -X POST http://localhost:5000/login \
  -d "username=admin&password=12345"
```

### Probar API de pulsera
```bash
curl -X POST http://localhost:5000/pulsera/5/lectura \
  -H "Content-Type: application/json" \
  -d '{"ritmo_cardiaco": 75, "temperatura_c": 37.2}'
```

---

## 📊 Estados del Semáforo

| Estado | Color | Condición |
|--------|-------|-----------|
| Crítico | 🔴 Rojo | Temp < 35°C o > 39.5°C, Ritmo < 40 o > 130 |
| Estable | 🟢 Verde | Temp 36-37.5°C, Ritmo 60-100, Pulsera puesta |
| Advertencia | 🔵 Azul | Cualquier otro caso |

---

## 🚀 Próximas Pasos Sugeridos

1. Leer `MEJORAS.md` para entender todos los cambios
2. Leer `SEGURIDAD.md` para mejorar la seguridad
3. Implementar hasheo de contraseñas (werkzeug)
4. Añadir logging
5. Crear tests unitarios
6. Hacer deploy a producción

---

**¿Preguntas? Revisa los comentarios en `api/index.py`** 📝

