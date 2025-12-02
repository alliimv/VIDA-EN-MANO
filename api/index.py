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

CONNECTION_STRING = (os.getenv("connection") or "").strip()
if not CONNECTION_STRING:
    raise RuntimeError("No se encontró la variable de entorno 'connection'.")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key-change-this")


def get_connection():
    return psycopg2.connect(CONNECTION_STRING)


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
            COALESCE(pu.id_pulsera, 'Sin asignar') as id_pulsera,
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
            "id_pulsera": r["id_pulsera"],
            "ritmo_cardiaco": r["ritmo_cardiaco"],
            "temperatura_c": r["temperatura_c"],
            "esta_puesta": r["esta_puesta"],
            "momento_lectura": r["momento_lectura"],
        })

    # Usa el template que ya tienes para la tabla
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