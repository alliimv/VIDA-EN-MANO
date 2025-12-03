from flask import (
    Flask, request, jsonify, render_template,
    redirect, url_for, session
)
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os
from datetime import date

# ================================
#   CONFIGURACIÓN Y CONEXIÓN
# ================================
load_dotenv()

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("No se encontró la variable de entorno 'DB_URL'.")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key-change-this")

def get_connection():
    return psycopg2.connect(DB_URL)

def is_logged_in():
    return session.get("logged_in") is True

# ================================
#   RUTAS DE AUTENTICACIÓN
# ================================

@app.route("/")
def home():
    if is_logged_in():
        return redirect(url_for("dashboard"))
    error = request.args.get("error")
    return render_template("login.html", error=error)


@app.route("/login", methods=["POST"])
def login():
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
        return f"Error al consultar usuarios: {e}"

    if row is None:
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))

    password_hash = row[0]

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
#   DASHBOARD PRINCIPAL
# ================================

@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("home"))

    return render_template("dashboard.html", username=session.get("username"))


# ================================
#   VER PACIENTES (TABLA)
# ================================
@app.route("/ver-pacientes")
def ver_pacientes():
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
        LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
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
        return f"<h3>Error al consultar pacientes: {e}</h3>"

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
            "id_pulsera": r["id_pulsera"] if r["id_pulsera"] is not None else "Sin asignar",  # Aquí se maneja el None
            "ritmo_cardiaco": r["ritmo_cardiaco"],
            "temperatura_c": r["temperatura_c"],
            "esta_puesta": r["esta_puesta"],
            "momento_lectura": r["momento_lectura"],
        })

    return render_template("tabla_pacientes.html",
                         username=session.get("username"),
                         pacientes=pacientes)


# ================================
#   PRUEBA DE CONEXIÓN BD
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
        return f"✅ Conexión exitosa a PostgreSQL<br>Fecha/Hora del servidor: {now[0]}"
    except Exception as e:
        return f"❌ Error al conectar: {e}"


# ================================
#   AGREGAR PACIENTE
# ================================

@app.route("/agregar-paciente", methods=["GET", "POST"])
def agregar_paciente():
    if not is_logged_in():
        return redirect(url_for("home"))

    if request.method == "POST":
        nombre = request.form.get("nombre", "").strip()
        apellido_paterno = request.form.get("apellido_paterno", "").strip()
        apellido_materno = request.form.get("apellido_materno", "").strip()
        fecha_nacimiento = request.form.get("fecha_nacimiento", "").strip()

        if not nombre or not apellido_paterno:
            return render_template("agregar_paciente.html",
                                   error="Nombre y apellido paterno son obligatorios",
                                   username=session.get("username"))

        try:
            conn = get_connection()
            cur = conn.cursor()

            cur.execute("""
                INSERT INTO pacientes (nombre, apellido_paterno, apellido_materno, fecha_nacimiento)
                VALUES (%s, %s, %s, %s)
                RETURNING id_paciente;
            """, (nombre, apellido_paterno, apellido_materno,
                  fecha_nacimiento if fecha_nacimiento else None))

            id_paciente = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

            return redirect(url_for("dashboard"))

        except Exception as e:
            error_msg = f"Error al guardar: {str(e)}"
            return render_template("agregar_paciente.html",
                                   error=error_msg,
                                   username=session.get("username"))

    return render_template("agregar_paciente.html",
                           username=session.get("username"))


# ================================
#   SEMÁFORO
# ================================

@app.route("/semaforo")
def semaforo():
    if not is_logged_in():
        return redirect(url_for("home"))

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
        LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
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
        return f"<h3>Error al consultar semáforo: {e}</h3>"

    pacientes_con_estado = []

    for r in rows:
        nombre_completo = f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}"

        temp = r["temperatura_c"]
        ritmo = r["ritmo_cardiaco"]
        esta_puesta = r["esta_puesta"]

        estado = "azul"

        if temp is not None and ritmo is not None:
            if (temp < 35 or temp > 39.5) or (ritmo < 40 or ritmo > 130):
                estado = "rojo"
            elif (36 <= temp <= 37.5) and (60 <= ritmo <= 100) and esta_puesta:
                estado = "verde"
            else:
                estado = "azul"

        pacientes_con_estado.append({
            "id_paciente": r["id_paciente"],
            "nombre": nombre_completo,
            "id_pulsera": r["id_pulsera"] or "Sin asignar",
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
#   API PARA PULSERAS (mantener)
# ================================

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
            "error": "Faltan campos: 'ritmo_cardiaco', 'temperatura_c'"
        }), 400

    try:
        conn = get_connection()
        cur = conn.cursor()

        cur.execute("""
            INSERT INTO lecturas (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario)
            VALUES (%s, %s, %s, %s, %s)
            RETURNING id_lectura, momento_lectura;
        """, (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario))

        row = cur.fetchone()
        conn.commit()
        cur.close()
        conn.close()

        return jsonify({
            "message": "Lectura insertada",
            "id_pulsera": id_pulsera,
            "id_lectura": row[0],
            "momento_lectura": row[1].isoformat()
        }), 201

    except Exception as e:
        return jsonify({"error": str(e)}), 500


# ================================
#   RUTAS DE PRUEBA
# ================================

@app.route("/test")
def test():
    return "✅ Servidor funcionando"


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
#   INICIAR APLICACIÓN
# ================================

if __name__ == "__main__":
    app.run(debug=True, host="0.0.0.0", port=5000)
# python
import json
# (place this import near the other imports at top of file)

@app.route("/historial/<int:id_paciente>")
def historial(id_paciente):
    if not is_logged_in():
        return redirect(url_for("home"))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # get all pulseras for this paciente
        cur.execute("SELECT id_pulsera FROM pulseras WHERE id_paciente = %s;", (id_paciente,))
        pulseras_rows = cur.fetchall()
        pulseras = [r["id_pulsera"] for r in pulseras_rows]

        readings = []
        if pulseras:
            # recent N readings across all pulseras (most recent first)
            cur.execute("""
                SELECT id_lectura, id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario, momento_lectura
                FROM lecturas
                WHERE id_pulsera = ANY(%s)
                ORDER BY momento_lectura DESC
                LIMIT 50;
            """, (pulseras,))
            rows = cur.fetchall()
            # convert to list ordered ascending (old -> new) for charts
            for r in reversed(rows):
                readings.append({
                    "id_lectura": r["id_lectura"],
                    "id_pulsera": r["id_pulsera"],
                    "ritmo_cardiaco": r["ritmo_cardiaco"],
                    "temperatura_c": r["temperatura_c"],
                    "esta_puesta": r["esta_puesta"],
                    "comentario": r["comentario"],
                    "momento_lectura": r["momento_lectura"].isoformat() if r["momento_lectura"] else None
                })

        cur.close()
        conn.close()

    except Exception as e:
        return f"<h3>Error al obtener historial: {e}</h3>"

    timestamps = [r["momento_lectura"] for r in readings]
    temps = [r["temperatura_c"] for r in readings]
    ritmos = [r["ritmo_cardiaco"] for r in readings]

    return render_template(
        "historial.html",
        username=session.get("username"),
        id_paciente=id_paciente,
        readings=readings,
        timestamps=json.dumps(timestamps),
        temps=json.dumps(temps),
        ritmos=json.dumps(ritmos),
    )


@app.route("/historial/<int:id_paciente>/full")
def historial_full(id_paciente):
    if not is_logged_in():
        return redirect(url_for("home"))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        cur.execute("SELECT id_pulsera FROM pulseras WHERE id_paciente = %s;", (id_paciente,))
        pulseras = [r["id_pulsera"] for r in cur.fetchall()]

        full = []
        if pulseras:
            cur.execute("""
                SELECT id_lectura, id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario, momento_lectura
                FROM lecturas
                WHERE id_pulsera = ANY(%s)
                ORDER BY momento_lectura DESC;
            """, (pulseras,))
            rows = cur.fetchall()
            for r in rows:
                full.append({
                    "id_lectura": r["id_lectura"],
                    "id_pulsera": r["id_pulsera"],
                    "ritmo_cardiaco": r["ritmo_cardiaco"],
                    "temperatura_c": r["temperatura_c"],
                    "esta_puesta": r["esta_puesta"],
                    "comentario": r["comentario"],
                    "momento_lectura": r["momento_lectura"].isoformat() if r["momento_lectura"] else None
                })

        cur.close()
        conn.close()

    except Exception as e:
        return f"<h3>Error al obtener historial completo: {e}</h3>"

    return render_template(
        "historial_full.html",
        username=session.get("username"),
        id_paciente=id_paciente,
        full_readings=full
    )
