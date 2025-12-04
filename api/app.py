# ================================
#   IMPORTACIONES NECESARIAS
# ================================
from flask import Flask, render_template, request, redirect, url_for, session, jsonify
import psycopg2
import psycopg2.extras
from dotenv import load_dotenv
import os
from datetime import date, datetime
import json
import bcrypt
from datetime import timedelta

# ================================
#   CONFIGURACIÓN Y CONEXIÓN
# ================================
load_dotenv()

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("No se encontró la variable de entorno 'DB_URL'.")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key-change-this")
app.permanent_session_lifetime = timedelta(days=7)


# ================================
#   FUNCIONES DE HASH DE CONTRASEÑAS
# ================================
def hash_password(password):
    """Genera hash de contraseña usando bcrypt y devuelve str (utf-8)."""
    salt = bcrypt.gensalt()
    # return str so it's stored consistently in DB (text column)
    return bcrypt.hashpw(password.encode('utf-8'), salt).decode('utf-8')


def check_password(password, hashed_password):
    """Verifica contraseña contra hash (acepta stored str o bytes)."""
    if not password or not hashed_password:
        return False
    try:
        # ensure hashed_password is bytes for bcrypt.checkpw
        if isinstance(hashed_password, str):
            hashed = hashed_password.encode('utf-8')
        else:
            hashed = hashed_password
        return bcrypt.checkpw(password.encode('utf-8'), hashed)
    except Exception:
        # No insecure fallbacks: on error, deny authentication
        return False


# ================================
#   FILTROS PERSONALIZADOS PARA TEMPLATES
# ================================

@app.template_filter('format_id')
def format_id_filter(id_num):
    """Formatea ID como 001, 002, etc. (solo para pacientes)"""
    try:
        return f"{int(id_num):03d}"
    except (ValueError, TypeError):
        return str(id_num)


@app.template_filter('tojson')
def tojson_filter(value):
    """Filtro para convertir valores a JSON en templates"""
    if hasattr(value, 'isoformat'):
        return value.isoformat()
    try:
        return json.dumps(value, indent=2, ensure_ascii=False)
    except:
        return str(value)


@app.context_processor
def inject_now():
    return {'now': datetime.now}


# ================================
#   CONEXIÓN A LA BASE DE DATOS
# ================================

def get_connection():
    return psycopg2.connect(DB_URL)


def is_logged_in():
    return session.get("logged_in") is True


# ================================
#   CONFIGURACIÓN DE SESIÓN PERMANENTE
# ================================
@app.before_request
def make_session_permanent():
    session.permanent = True


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
    username = request.form.get("username", "").strip()
    password = request.form.get("password", "")

    if not username or not password:
        return redirect(url_for("home", error="Usuario y contraseña requeridos"))

    try:
        conn = get_connection()
        cur = conn.cursor()
        # Fetch password hash and tipo_usuario so we can store role in session
        cur.execute("SELECT password_hash, COALESCE(tipo_usuario, '') FROM usuarios WHERE username = %s;", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return f"Error al consultar usuarios: {e}"

    if row is None:
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))

    stored_hash = row[0]
    user_tipo = row[1] if len(row) > 1 else ""

    if check_password(password, stored_hash):
        session["logged_in"] = True
        session["username"] = username
        # store role for UI purposes
        session["tipo_usuario"] = user_tipo or "familiar"
        return redirect(url_for("dashboard"))
    else:
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ================================
#   REGISTRO SIMPLIFICADO (SOLO UNA VEZ)
# ================================
@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Página para que nuevos usuarios se registren"""

    # Cargar pacientes para el select (SIEMPRE)
    pacientes = []
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("SELECT id_paciente, nombre, apellido_paterno, apellido_materno FROM pacientes ORDER BY nombre;")
        pacientes = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error al cargar pacientes: {e}")

    if request.method == "POST":
        nombre_completo = request.form.get("nombre_completo", "").strip()
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        tipo_usuario = request.form.get("tipo_usuario", "familiar")
        id_paciente = request.form.get("id_paciente", "").strip()
        parentesco = request.form.get("parentesco", "").strip()

        # Validaciones básicas
        if not username or not password or not nombre_completo:
            return render_template("registro.html", error="Nombre, usuario y contraseña son obligatorios",
                                   pacientes=pacientes)

        if password != confirm_password:
            return render_template("registro.html", error="Las contraseñas no coinciden", pacientes=pacientes)

        if len(password) < 6:
            return render_template("registro.html", error="La contraseña debe tener al menos 6 caracteres",
                                   pacientes=pacientes)

        if tipo_usuario not in ["enfermero", "familiar"]:
            return render_template("registro.html", error="Tipo de usuario no válido", pacientes=pacientes)

        # Validaciones ESPECÍFICAS para familiares
        if tipo_usuario == "familiar":
            if not id_paciente:
                return render_template("registro.html", error="Debes seleccionar un paciente", pacientes=pacientes)
            if not parentesco:
                return render_template("registro.html", error="Debe especificar el parentesco", pacientes=pacientes)

        try:
            conn = get_connection()
            cur = conn.cursor()

            # Verificar si el usuario ya existe
            cur.execute("SELECT 1 FROM usuarios WHERE username = %s;", (username,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return render_template("registro.html", error="El nombre de usuario ya está en uso",
                                       pacientes=pacientes)

            # Hashear la contraseña (ahora retorna str)
            password_hash = hash_password(password)

            # Insertar usuario según tipo
            if tipo_usuario == "familiar":
                cur.execute("""
                    INSERT INTO usuarios (username, password_hash, fecha_creacion, nombre_completo, 
                                          tipo_usuario, id_paciente_asignado, parentesco)
                    VALUES (%s, %s, NOW(), %s, %s, %s, %s);
                """, (username, password_hash, nombre_completo,
                      tipo_usuario, int(id_paciente), parentesco))
            else:  # enfermero
                cur.execute("""
                    INSERT INTO usuarios (username, password_hash, fecha_creacion, nombre_completo, tipo_usuario)
                    VALUES (%s, %s, NOW(), %s, %s);
                """, (username, password_hash, nombre_completo, tipo_usuario))

            conn.commit()
            cur.close()
            conn.close()

            # Auto-login
            session["logged_in"] = True
            session["username"] = username
            session["tipo_usuario"] = tipo_usuario

            return redirect(url_for("dashboard"))

        except Exception as e:
            error_msg = f"Error en el registro: {str(e)}"
            print(error_msg)
            return render_template("registro.html", error=error_msg, pacientes=pacientes)

    # GET request - mostrar formulario con pacientes
    return render_template("registro.html", pacientes=pacientes)


# ================================
#   DASHBOARD PRINCIPAL
# ================================
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get("username")
    user_role = session.get("tipo_usuario", "invitado")

    # Contar pacientes
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT COUNT(*) FROM pacientes;")
        total_pacientes = cur.fetchone()[0] or 0

        cur.execute("""
            SELECT 
                COUNT(CASE WHEN (l.temperatura_c < 35 OR l.temperatura_c > 39.5) 
                          OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130) THEN 1 END) as criticos,
                COUNT(CASE WHEN (l.temperatura_c BETWEEN 36 AND 37.5) 
                          AND (l.ritmo_cardiaco BETWEEN 60 AND 100) 
                          AND l.esta_puesta = true THEN 1 END) as estables
            FROM lecturas l
            WHERE l.momento_lectura > NOW() - INTERVAL '24 hours';
        """)
        stats = cur.fetchone()
        criticos = stats[0] if stats else 0
        estables = stats[1] if stats else 0

        cur.close()
        conn.close()

    except Exception as e:
        total_pacientes = 0
        criticos = 0
        estables = 0

    return render_template("dashboard.html",
                           username=username,
                           user_role=user_role,
                           total_pacientes=total_pacientes,
                           criticos=criticos,
                           estables=estables)


# ================================
#   RUTA: MI PERFIL (VERSIÓN SIMPLE)
# ================================
@app.route("/mi-perfil")
def mi_perfil():
    username = session.get("username", "Invitado")
    logged_in = session.get("logged_in", False)

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        if logged_in:
            cur.execute("""
                SELECT username, fecha_creacion, nombre_completo,
                       COALESCE(tipo_usuario, 'familiar') as tipo_usuario,
                       id_paciente_asignado, parentesco
                FROM usuarios 
                WHERE username = %s;
            """, (username,))
            usuario_data = cur.fetchone()

            if usuario_data:
                usuario = {
                    "username": usuario_data["username"],
                    "fecha_creacion": usuario_data["fecha_creacion"],
                    "nombre_completo": usuario_data["nombre_completo"],
                    "tipo_usuario": usuario_data["tipo_usuario"],
                    "parentesco": usuario_data["parentesco"],
                    "id_paciente_asignado": usuario_data["id_paciente_asignado"]
                }

                # Obtener pacientes
                if usuario["tipo_usuario"] == "enfermero":
                    cur.execute(
                        "SELECT p.id_paciente, p.nombre, p.apellido_paterno, p.apellido_materno, p.fecha_nacimiento FROM pacientes p ORDER BY p.nombre;")
                elif usuario["id_paciente_asignado"]:
                    cur.execute("""
                        SELECT p.id_paciente, p.nombre, p.apellido_paterno, p.apellido_materno, p.fecha_nacimiento
                        FROM pacientes p
                        WHERE p.id_paciente = %s;
                    """, (usuario["id_paciente_asignado"],))
                else:
                    usuario["error"] = "No tienes paciente asignado"
                    asignaciones = []
                asignaciones = cur.fetchall()
            else:
                usuario = {"username": username, "tipo_usuario": "invitado"}
                asignaciones = []
        else:
            usuario = {"username": "Invitado", "tipo_usuario": "invitado"}
            cur.execute("SELECT id_paciente, nombre, apellido_paterno, apellido_materno FROM pacientes LIMIT 2;")
            asignaciones = cur.fetchall()

        cur.close()
        conn.close()

    except Exception as e:
        usuario = {"username": username, "tipo_usuario": "invitado", "error": str(e)}
        asignaciones = []
        print(f"Error en mi_perfil: {e}")

    return render_template("mi_perfil.html",
                           usuario=usuario,
                           asignaciones=asignaciones,
                           logged_in=logged_in)


# ================================
#   VER PACIENTES (TABLA) - TODOS LOS PACIENTES
# ================================
@app.route("/ver-pacientes")
def ver_pacientes():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get("username")
    query = """
        SELECT p.*, pu.id_pulsera, l.temperatura_c, l.ritmo_cardiaco, l.esta_puesta, l.momento_lectura
        FROM pacientes p
        LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
        LEFT JOIN LATERAL (
            SELECT * FROM lecturas l
            WHERE l.id_pulsera = pu.id_pulsera
            ORDER BY l.momento_lectura DESC LIMIT 1
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
                    (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))

    pacientes = []
    for r in rows:
        nombre_completo = f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}"
        pacientes.append({
            "id_paciente": r["id_paciente"],
            "nombre": nombre_completo,
            "edad": calcular_edad(r["fecha_nacimiento"]),
            "id_pulsera": r["id_pulsera"] if r["id_pulsera"] is not None else "Sin asignar",
            "temperatura_c": r["temperatura_c"],
            "ritmo_cardiaco": r["ritmo_cardiaco"],
            "esta_puesta": r["esta_puesta"],
            "momento_lectura": r["momento_lectura"],
        })

    return render_template("tabla_pacientes.html",
                           username=username,
                           pacientes=pacientes)


# ================================
#   BUSCADOR DE PACIENTES
# ================================
@app.route("/buscar-pacientes", methods=["GET", "POST"])
def buscar_pacientes():
    if not is_logged_in():
        return redirect(url_for("home"))

    pacientes = []
    params = []

    if request.method == "POST":
        busqueda = request.form.get("busqueda", "").strip()
        estado_filtro = request.form.get("estado", "")
        tiene_pulsera = request.form.get("tiene_pulsera", "")

        query = """
            SELECT DISTINCT p.id_paciente, p.nombre, p.apellido_paterno, p.apellido_materno,
                   p.fecha_nacimiento, pu.id_pulsera, l.ritmo_cardiaco, l.temperatura_c,
                   l.esta_puesta, l.momento_lectura
            FROM pacientes p
            LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
            LEFT JOIN LATERAL (
                SELECT * FROM lecturas l
                WHERE l.id_pulsera = pu.id_pulsera
                ORDER BY l.momento_lectura DESC LIMIT 1
            ) l ON TRUE
            WHERE 1=1
        """

        if busqueda:
            if busqueda.isdigit():
                query += " AND p.id_paciente = %s"
                params.append(int(busqueda))
            else:
                query += " AND (p.nombre ILIKE %s OR p.apellido_paterno ILIKE %s OR p.apellido_materno ILIKE %s)"
                termino_busqueda = f"%{busqueda}%"
                params.extend([termino_busqueda, termino_busqueda, termino_busqueda])

        if estado_filtro:
            if estado_filtro == "rojo":
                query += " AND ((l.temperatura_c < 35 OR l.temperatura_c > 39.5) OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130))"
            elif estado_filtro == "verde":
                query += " AND (l.temperatura_c BETWEEN 36 AND 37.5) AND (l.ritmo_cardiaco BETWEEN 60 AND 100) AND l.esta_puesta = true"
            elif estado_filtro == "azul":
                query += " AND NOT ((l.temperatura_c < 35 OR l.temperatura_c > 39.5) OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130))"
                query += " AND NOT ((l.temperatura_c BETWEEN 36 AND 37.5) AND (l.ritmo_cardiaco BETWEEN 60 AND 100) AND l.esta_puesta = true)"

        if tiene_pulsera == "con":
            query += " AND pu.id_pulsera IS NOT NULL"
        elif tiene_pulsera == "sin":
            query += " AND pu.id_pulsera IS NULL"

        query += " ORDER BY p.id_paciente"

        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            cur.close()
            conn.close()

            def calcular_edad(fecha_nacimiento):
                if not fecha_nacimiento:
                    return None
                hoy = date.today()
                return hoy.year - fecha_nacimiento.year - (
                            (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day))

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

                pacientes.append({
                    "id_paciente": r["id_paciente"],
                    "nombre": nombre_completo,
                    "edad": calcular_edad(r["fecha_nacimiento"]),
                    "id_pulsera": r["id_pulsera"] if r["id_pulsera"] is not None else "Sin asignar",
                    "ritmo_cardiaco": ritmo,
                    "temperatura_c": temp,
                    "esta_puesta": esta_puesta,
                    "momento_lectura": r["momento_lectura"],
                    "estado": estado,
                    "estado_texto": {"rojo": "Crítico", "verde": "Estable", "azul": "Advertencia"}[estado]
                })

        except Exception as e:
            return f"<h3>Error en la búsqueda: {e}</h3>"

    return render_template(
        "buscar_pacientes.html",
        username=session.get("username"),
        pacientes=pacientes,
        busqueda=request.form.get("busqueda", "") if request.method == "POST" else "",
        estado_filtro=request.form.get("estado", "") if request.method == "POST" else "",
        tiene_pulsera=request.form.get("tiene_pulsera", "") if request.method == "POST" else "",
        total_resultados=len(pacientes)
    )


# ================================
#   AGREGAR PACIENTE CON PULSERA
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
        asignar_pulsera = request.form.get("asignar_pulsera", "no") == "si"
        id_pulsera = request.form.get("id_pulsera", "").strip()

        if not nombre or not apellido_paterno:
            return render_template("agregar_paciente.html",
                                   error="Nombre y apellido paterno son obligatorios",
                                   username=session.get("username"))

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO pacientes (nombre, apellido_paterno, apellido_materno, fecha_nacimiento)
                VALUES (%s, %s, %s, %s) RETURNING id_paciente;
            """, (nombre, apellido_paterno, apellido_materno, fecha_nacimiento if fecha_nacimiento else None))

            id_paciente = cur.fetchone()[0]

            if asignar_pulsera and id_pulsera:
                cur.execute("SELECT 1 FROM pulseras WHERE id_pulsera = %s;", (int(id_pulsera),))
                if cur.fetchone():
                    conn.rollback()
                    cur.close()
                    conn.close()
                    return render_template("agregar_paciente.html",
                                           error=f"La pulsera {id_pulsera} ya está asignada",
                                           username=session.get("username"))

                cur.execute("""
                    INSERT INTO pulseras (id_pulsera, id_paciente, fecha_asignacion)
                    VALUES (%s, %s, NOW());
                """, (int(id_pulsera), id_paciente))

            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("ver_pacientes"))

        except ValueError:
            return render_template("agregar_paciente.html",
                                   error="El ID de pulsera debe ser un número válido",
                                   username=session.get("username"))
        except Exception as e:
            return render_template("agregar_paciente.html",
                                   error=f"Error al guardar: {str(e)}",
                                   username=session.get("username"))

    return render_template("agregar_paciente.html", username=session.get("username"))


# ================================
#   ASIGNAR PULSERA A PACIENTE EXISTENTE
# ================================
@app.route("/asignar-pulsera/<int:id_paciente>", methods=["GET", "POST"])
def asignar_pulsera(id_paciente):
    if not is_logged_in():
        return redirect(url_for("home"))

    if request.method == "POST":
        id_pulsera = request.form.get("id_pulsera", "").strip()

        if not id_pulsera:
            return render_template("asignar_pulsera.html",
                                   error="El ID de pulsera es requerido",
                                   username=session.get("username"),
                                   id_paciente=id_paciente)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("SELECT 1 FROM pacientes WHERE id_paciente = %s;", (id_paciente,))
            if not cur.fetchone():
                cur.close()
                conn.close()
                return render_template("asignar_pulsera.html",
                                       error="Paciente no encontrado",
                                       username=session.get("username"),
                                       id_paciente=id_paciente)

            cur.execute("SELECT 1 FROM pulseras WHERE id_pulsera = %s;", (int(id_pulsera),))
            if cur.fetchone():
                cur.close()
                conn.close()
                return render_template("asignar_pulsera.html",
                                       error=f"La pulsera {id_pulsera} ya está asignada",
                                       username=session.get("username"),
                                       id_paciente=id_paciente)

            cur.execute("SELECT 1 FROM pulseras WHERE id_paciente = %s;", (id_paciente,))
            if cur.fetchone():
                cur.execute("UPDATE pulseras SET id_pulsera = %s, fecha_asignacion = NOW() WHERE id_paciente = %s;",
                            (int(id_pulsera), id_paciente))
            else:
                cur.execute("INSERT INTO pulseras (id_pulsera, id_paciente, fecha_asignacion) VALUES (%s, %s, NOW());",
                            (int(id_pulsera), id_paciente))

            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("ver_pacientes"))

        except ValueError:
            return render_template("asignar_pulsera.html",
                                   error="El ID de pulsera debe ser un número",
                                   username=session.get("username"),
                                   id_paciente=id_paciente)
        except Exception as e:
            return render_template("asignar_pulsera.html",
                                   error=f"Error: {str(e)}",
                                   username=session.get("username"),
                                   id_paciente=id_paciente)

    return render_template("asignar_pulsera.html",
                           username=session.get("username"),
                           id_paciente=id_paciente)


# ================================
#   SEMÁFORO
# ================================
@app.route("/semaforo")
def semaforo():
    if not is_logged_in():
        return redirect(url_for("home"))

    query = """
        SELECT p.id_paciente, p.nombre, p.apellido_paterno, p.apellido_materno,
               pu.id_pulsera, l.ritmo_cardiaco, l.temperatura_c, l.esta_puesta, l.momento_lectura
        FROM pacientes p
        LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
        LEFT JOIN LATERAL (
            SELECT * FROM lecturas l
            WHERE l.id_pulsera = pu.id_pulsera
            ORDER BY l.momento_lectura DESC LIMIT 1
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
            "estado_texto": {"rojo": "Crítico", "verde": "Estable", "azul": "Advertencia"}[estado]
        })

    return render_template("semaforo.html",
                           username=session.get("username"),
                           pacientes=pacientes_con_estado)


# ================================
#   API PARA PULSERAS
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
        return jsonify({"error": "Faltan campos: 'ritmo_cardiaco', 'temperatura_c'"}), 400

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("""
            INSERT INTO lecturas (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario)
            VALUES (%s, %s, %s, %s, %s) RETURNING id_lectura, momento_lectura;
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