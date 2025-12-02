from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, session
)
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os

# ================================
#   CONFIGURACIÓN Y CONEXIÓN NEON
# ================================
load_dotenv()

# Variables (por si las quieres usar después)
USER = os.getenv("user")
PASSWORD = os.getenv("password")
HOST = os.getenv("host")
PORT = os.getenv("port")
DBNAME = os.getenv("dbname")

# Cadena de conexión (viene de la variable de entorno 'connection')
# IMPORTANTE: en Vercel debe ser SOLO:
# postgresql://usuario:pass@host/dbname?sslmode=require
CONNECTION_STRING = (os.getenv("connection") or "").strip()

if not CONNECTION_STRING:
    raise RuntimeError("No se encontró la variable de entorno 'connection'.")

app = Flask(__name__)

# Clave para sesiones (login)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key")


def get_connection():
    # Usamos el mismo método del segundo código
    return psycopg2.connect(CONNECTION_STRING)


# ================================
#   RUTA DE PRUEBA DE CONEXIÓN
# ================================
@app.route("/debug-conn")
def debug_conn():
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT NOW();")
        now = cur.fetchone()
        cur.close()
        conn.close()
        return f"Conexión OK. NOW() = {now}"
    except Exception as e:
        return f"Error al conectar: {e}"


# ================================
#   FUNCIONES AUXILIARES LOGIN
# ================================
def is_logged_in():
    return session.get("logged_in") is True


# ================================
#   RUTAS DE AUTENTICACIÓN
# ================================

@app.route("/", methods=["GET"])
def home():
    """
    Página de login.
    Si ya está logueado, lo manda al dashboard.
    """
    if is_logged_in():
        return redirect(url_for("dashboard"))

    error = request.args.get("error")
    return render_template("login.html", error=error)


@app.route("/login", methods=["POST"])
def login():
    """
    Valida usuario contra la tabla 'usuarios' en la base de datos.
    """
    username = request.form.get("username", "")
    password = request.form.get("password", "")

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT password_hash FROM usuarios WHERE username = %s;",
            (username,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return f"Error al consultar la tabla usuarios: {e}"

    if row is None:
        # usuario no existe
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))

    password_hash = row[0]

    # Para proyecto escolar: comparación directa (si guardaste texto plano)
    if password == password_hash:
        session["logged_in"] = True
        session["username"] = username
        return redirect(url_for("dashboard"))
    else:
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ================================
#   DASHBOARD PROTEGIDO
# ================================

@app.route("/dashboard")
def dashboard():
    """
    Muestra tabla de pacientes + pulseras + última lectura.
    Usa las tablas:
      - pacientes
      - pulseras
      - lecturas
    """
    if not is_logged_in():
        return redirect(url_for("home"))

    query = """
        SELECT
            p.id_paciente,
            p.nombre,
            p.apellido_paterno,
            p.apellido_materno,
            p.fecha_nacimiento,
            pu.id_pulsera,
            l.ritmo_cardiaco,
            l.temperatura_c,
            l.esta_puesta,
            l.momento_lectura
        FROM pacientes p
        JOIN pulseras pu
          ON pu.id_paciente = p.id_paciente
        LEFT JOIN LATERAL (
            SELECT *
            FROM lecturas l
            WHERE l.id_pulsera = pu.id_pulsera
            ORDER BY l.momento_lectura DESC
            LIMIT 1
        ) l ON TRUE
        ORDER BY p.id_paciente;
    """

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return f"<h3>Error al consultar datos del dashboard: {e}</h3>"

    from datetime import date

    def calcular_edad(fecha_nacimiento):
        if not fecha_nacimiento:
            return None
        hoy = date.today()
        return hoy.year - fecha_nacimiento.year - (
            (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
        )

    pacientes = []
    for r in rows:
        nombre_completo = f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}"
        pacientes.append({
            "id_paciente": r["id_paciente"],
            "nombre": nombre_completo,
            "edad": calcular_edad(r["fecha_nacimiento"]),
            "id_pulsera": r["id_pulsera"],
            "ritmo_cardiaco": r["ritmo_cardiaco"],
            "temperatura_c": r["temperatura_c"],
            "esta_puesta": r["esta_puesta"],
            "momento_lectura": r["momento_lectura"],
        })

    return render_template(
        "dashboard.html",
        username=session.get("username"),
        pacientes=pacientes
    )


# ================================
#   PRUEBA DE CONEXIÓN /SENSOR
# ================================
@app.route("/sensor")
def sensor():
    try:
        connection = get_connection()
        cursor = connection.cursor()
        cursor.execute("SELECT NOW();")
        result = cursor.fetchone()
        cursor.close()
        connection.close()
        return f"Current Time: {result}"
    except Exception as e:
        return f"Failed to connect: {e}"


# ================================
#   API PARA LA PULSERA (JSON)
# ================================

# 1) INSERTAR LECTURA DE SENSORES
@app.route("/pulsera/<int:id_pulsera>/lectura", methods=["POST"])
def insertar_lectura_pulsera(id_pulsera):
    data = request.get_json(silent=True)

    if data is None:
        return jsonify({"error": "Body debe ser JSON"}), 400

    ritmo_cardiaco = data.get("ritmo_cardiaco")
    temperatura_c = data.get("temperatura_c")
    esta_puesta = data.get("esta_puesta")
    comentario = data.get("comentario", None)

    if ritmo_cardiaco is None or temperatura_c is None:
        return jsonify({
            "error": "Faltan campos obligatorios: 'ritmo_cardiaco', 'temperatura_c'"
        }), 400

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO lecturas (
                id_pulsera,
                ritmo_cardiaco,
                temperatura_c,
                esta_puesta,
                comentario
            )
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id_lectura, momento_lectura;
        """, (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario))

        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message": "Lectura insertada correctamente",
            "id_pulsera": id_pulsera,
            "id_lectura": row[0],
            "momento_lectura": row[1].isoformat()
        }), 201

    except psycopg2.Error as e:
        return jsonify({"error": str(e)}), 500


# 2) OBTENER ÚLTIMAS LECTURAS
@app.route("/pulsera/<int:id_pulsera>/lecturas", methods=["GET"])
def obtener_lecturas_pulsera(id_pulsera):
    limit = request.args.get("limit", default=10, type=int)

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            SELECT
                id_lectura,
                momento_lectura,
                ritmo_cardiaco,
                temperatura_c,
                esta_puesta,
                comentario
            FROM lecturas
            WHERE id_pulsera = %s
            ORDER BY momento_lectura DESC
            LIMIT %s;
        """, (id_pulsera, limit))

        rows = cur.fetchall()
        cur.close()
        conn.close()

        lecturas = []
        for r in rows:
            lecturas.append({
                "id_lectura": r[0],
                "momento_lectura": r[1].isoformat(),
                "ritmo_cardiaco": r[2],
                "temperatura_c": float(r[3]) if r[3] is not None else None,
                "esta_puesta": r[4],
                "comentario": r[5]
            })

        return jsonify({
            "id_pulsera": id_pulsera,
            "count": len(lecturas),
            "lecturas": lecturas
        })

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ----------------- TUS EJEMPLOS ORIGINALES -----------------


@app.route("/hello")
def hello():
    return render_template("hello.html", user="Fulanito")


# ================================
#   PÁGINA DE SEMÁFORO DE ESTADO
# ================================

@app.route("/semaforo")
def semaforo():
    """
    Muestra un semáforo con el estado de todos los pacientes
    """
    if not is_logged_in():
        return redirect(url_for("home"))

    # Consulta para obtener el estado actual de todos los pacientes
    query = """
        SELECT
            p.id_paciente,
            p.nombre,
            p.apellido_paterno,
            p.apellido_materno,
            pu.id_pulsera,
            l.ritmo_cardiaco,
            l.temperatura_c,
            l.esta_puesta,
            l.momento_lectura
        FROM pacientes p
        JOIN pulseras pu ON pu.id_paciente = p.id_paciente
        LEFT JOIN LATERAL (
            SELECT *
            FROM lecturas l
            WHERE l.id_pulsera = pu.id_pulsera
            ORDER BY l.momento_lectura DESC
            LIMIT 1
        ) l ON TRUE
        ORDER BY p.id_paciente;
    """

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        return f"<h3>Error al consultar datos del semáforo: {e}</h3>"

    pacientes_con_estado = []
    
    for r in rows:
        nombre_completo = f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}"
        
        # Determinar el estado del semáforo
        temp = r["temperatura_c"]
        ritmo = r["ritmo_cardiaco"]
        esta_puesta = r["esta_puesta"]
        
        estado = "azul"  # Por defecto: advertencia
        
        if temp is not None and ritmo is not None:
            # CRÍTICO (rojo): temperatura fuera de rango peligroso O ritmo cardíaco muy peligroso
            if (temp < 35 or temp > 39.5) or (ritmo < 40 or ritmo > 130):
                estado = "rojo"
            # BUENO (verde): valores normales y pulsera puesta
            elif (36 <= temp <= 37.5) and (60 <= ritmo <= 100) and esta_puesta:
                estado = "verde"
            # ADVERTENCIA (azul): valores ligeramente fuera de rango o pulsera no puesta
            else:
                estado = "azul"
        
        pacientes_con_estado.append({
            "id_paciente": r["id_paciente"],
            "nombre": nombre_completo,
            "id_pulsera": r["id_pulsera"],
            "ritmo_cardiaco": ritmo,
            "temperatura_c": temp,
            "esta_puesta": esta_puesta,
            "momento_lectura": r["momento_lectura"],
            "estado": estado,
            "estado_texto": {
                "rojo": "Crítico",
                "verde": "Estable", 
                "azul": "Advertencia"
            }[estado]
        })

    return render_template(
        "semaforo.html",
        username=session.get("username"),
        pacientes=pacientes_con_estado
    )
# ================================
#   GESTIÓN DE PACIENTES
# ================================

@app.route("/agregar-paciente", methods=["GET", "POST"])
def agregar_paciente():
    """
    Formulario para agregar nuevos pacientes
    """
    if not is_logged_in():
        return redirect(url_for("home"))

    if request.method == "POST":
        # Obtener datos del formulario
        nombre = request.form.get("nombre", "").strip()
        apellido_paterno = request.form.get("apellido_paterno", "").strip()
        apellido_materno = request.form.get("apellido_materno", "").strip()
        fecha_nacimiento = request.form.get("fecha_nacimiento", "").strip()

        # Validaciones básicas
        if not nombre or not apellido_paterno:
            return render_template("agregar_paciente.html",
                                   error="Nombre y apellido paterno son obligatorios")

        try:
            conn = get_connection()
            cur = conn.cursor()

            # Insertar el paciente - EL ID SE GENERA AUTOMÁTICAMENTE (SERIAL)
            cur.execute("""
                INSERT INTO pacientes (nombre, apellido_paterno, apellido_materno, fecha_nacimiento)
                VALUES (%s, %s, %s, %s)
                RETURNING id_paciente;
            """, (nombre, apellido_paterno, apellido_materno, fecha_nacimiento or None))

            id_paciente = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

            # Mensaje de éxito
            return redirect(url_for("dashboard"))

        except psycopg2.Error as e:
            error_msg = str(e)
            # Mensaje más amigable para errores comunes
            if "pacientes_pkey" in error_msg:
                error_msg = "Error: ID de paciente duplicado. El sistema asignará automáticamente un ID único."
            elif "violates foreign key constraint" in error_msg:
                error_msg = "Error: No se puede asignar la pulsera porque no existe en el sistema."

            return render_template("agregar_paciente.html",
                                   error=f"Error al guardar paciente: {error_msg}")

    # Si es GET, mostrar el formulario vacío
    return render_template("agregar_paciente.html", username=session.get("username"))


# Ruta de prueba para verificar si el botón está funcionando
@app.route("/debug-boton")
def debug_boton():
    return """
    <!DOCTYPE html>
    <html>
    <body style="padding: 20px; font-family: sans-serif;">
        <h1>Debug: Prueba de botones</h1>

        <h2>Botón de Agregar Paciente:</h2>
        <a href="/agregar-paciente" style="background: #10b981; color: white; padding: 10px 20px; display: inline-block; margin: 10px 0; text-decoration: none; border-radius: 5px;">
            ➕ Agregar Paciente
        </a>

        <h2>Botón de Semáforo:</h2>
        <a href="/semaforo" style="background: #2563eb; color: white; padding: 10px 20px; display: inline-block; margin: 10px 0; text-decoration: none; border-radius: 5px;">
            📊 Ver Semáforo
        </a>

        <h2>Estado de rutas:</h2>
        <ul>
            <li><strong>/agregar-paciente:</strong> <a href="/agregar-paciente">Probar</a></li>
            <li><strong>/semaforo:</strong> <a href="/semaforo">Probar</a></li>
            <li><strong>/dashboard:</strong> <a href="/dashboard">Probar</a></li>
        </ul>

        <h2>¿Qué deberías ver?</h2>
        <p>Si los botones de arriba funcionan, pero no aparecen en el dashboard, el problema está en el archivo dashboard.html</p>
    </body>
    </html>
    """


@app.route("/diagnostico-agregar")
def diagnostico_agregar():
    """
    Página de diagnóstico para el formulario de agregar paciente
    """
    if not is_logged_in():
        return "No estás logueado"

    # Verifica la conexión a la base de datos
    try:
        conn = get_connection()
        cur = conn.cursor()

        # Verifica si la tabla existe
        cur.execute("""
            SELECT EXISTS (
                SELECT FROM information_schema.tables 
                WHERE table_name = 'pacientes'
            );
        """)
        tabla_existe = cur.fetchone()[0]

        # Verifica la estructura de la tabla
        cur.execute("""
            SELECT column_name, data_type, is_nullable
            FROM information_schema.columns
            WHERE table_name = 'pacientes'
            ORDER BY ordinal_position;
        """)
        columnas = cur.fetchall()

        # Cuenta pacientes existentes
        cur.execute("SELECT COUNT(*) FROM pacientes;")
        total_pacientes = cur.fetchone()[0]

        cur.close()
        conn.close()

        resultado = f"""
        <h2>Diagnóstico - Agregar Paciente</h2>
        <p><strong>Tabla 'pacientes' existe:</strong> {tabla_existe}</p>
        <p><strong>Total pacientes en BD:</strong> {total_pacientes}</p>

        <h3>Estructura de la tabla:</h3>
        <table border="1">
            <tr><th>Columna</th><th>Tipo</th><th>¿Nulo?</th></tr>
        """
        for col in columnas:
            resultado += f"<tr><td>{col[0]}</td><td>{col[1]}</td><td>{col[2]}</td></tr>"
        resultado += "</table>"

        # Enlace para probar el formulario
        resultado += f"""
        <h3>Pruebas:</h3>
        <ul>
            <li><a href="/agregar-paciente">Ir al formulario de agregar paciente</a></li>
            <li><a href="/dashboard">Volver al dashboard</a></li>
        </ul>
        """

        return resultado

    except Exception as e:
        return f"<h2>Error en diagnóstico:</h2><pre>{str(e)}</pre>"