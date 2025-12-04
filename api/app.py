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
from groq import Groq

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


# Helper: obtener id_paciente asignado a un familiar
def get_assigned_patient_id(username):
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id_paciente_asignado FROM usuarios WHERE username = %s;", (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
        if row:
            return row[0]
    except Exception:
        pass
    return None

# ================================
#   CONFIGURACIÓN DE SESIÓN PERMANENTE
# ================================
@app.before_request
def make_session_permanent():
    session.permanent = True


@app.before_request
def restrict_familiar_access():
    # Después de hacer la sesión permanente, limitar qué endpoints puede usar un 'familiar'.
    # Permitir endpoints básicos y aquellos que sirven para ver su paciente/historial.
    if not is_logged_in():
        return None

    tipo = session.get('tipo_usuario')
    if tipo != 'familiar':
        return None

    # Endpoint actual
    ep = request.endpoint or ''

    # Permitir estáticos
    if ep.startswith('static'):
        return None

    # Lista blanca de endpoints que un familiar puede usar
    # Añadimos todas las rutas relacionadas con ver/crear/editar/eliminar historial,
    # además de vistas de pacientes y búsqueda para que puedan abrir el historial.
    allowed = {
        'home', 'login', 'logout', 'mi_perfil', 'ver_pacientes', 'buscar_pacientes',
        'historial_paciente', 'historial_paciente_nuevo', 'editar_historial', 'eliminar_historial',
        'cambiar_contrasena', 'tabla_pacientes', 'dashboard', 'semaforo'
    }

    # Si intenta acceder a otra endpoint, redirigirle a su perfil
    if ep not in allowed:
        return redirect(url_for('mi_perfil'))

    return None

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
        print(f"Error al consultar usuarios: {e}")
        return redirect(url_for("home", error="Error al autenticar usuario"))

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
            error_msg = "Error al registrar el usuario. Por favor inténtalo más tarde."
            print(f"Error en registro: {e}")
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

    # Por defecto valores
    total_pacientes = 0
    criticos = 0
    estables = 0
    top_residentes = []
    trend_labels = []
    trend_criticos = []
    trend_estables = []

    try:
        conn = get_connection()
        cur = conn.cursor()

        # Si el usuario es familiar, limitar la vista al paciente asignado
        if user_role == 'familiar':
            assigned = get_assigned_patient_id(username)
            if not assigned:
                # Usuario familiar sin asignación
                total_pacientes = 0
                cur.close()
                conn.close()
                return render_template("dashboard.html",
                                       username=username,
                                       user_role=user_role,
                                       total_pacientes=total_pacientes,
                                       criticos=criticos,
                                       estables=estables,
                                       top_residentes=top_residentes,
                                       trend_labels=trend_labels,
                                       trend_criticos=trend_criticos,
                                       trend_estables=trend_estables)

            # total = 1 (su paciente)
            total_pacientes = 1

            # Buscar pulsera del paciente
            cur.execute('SELECT id_pulsera FROM pulseras WHERE id_paciente = %s LIMIT 1;', (assigned,))
            pul = cur.fetchone()
            id_pulsera = pul[0] if pul else None

            # Estadísticas (últimas 24h) solo para las lecturas de la pulsera asignada
            if id_pulsera:
                cur.execute("""
                    SELECT 
                        COUNT(CASE WHEN (temperatura_c < 35 OR temperatura_c > 39.5) OR (ritmo_cardiaco < 40 OR ritmo_cardiaco > 130) THEN 1 END) as criticos,
                        COUNT(CASE WHEN (temperatura_c BETWEEN 36 AND 37.5) AND (ritmo_cardiaco BETWEEN 60 AND 100) AND esta_puesta = true THEN 1 END) as estables
                    FROM lecturas l
                    WHERE l.id_pulsera = %s AND l.momento_lectura > NOW() - INTERVAL '24 hours';
                """, (id_pulsera,))
                stats = cur.fetchone()
                criticos = stats[0] if stats else 0
                estables = stats[1] if stats else 0

            # Top residente -> su propio paciente (si existe)
            cur.execute("SELECT p.id_paciente, p.nombre, p.apellido_paterno, p.apellido_materno, pu.id_pulsera, l.temperatura_c, l.ritmo_cardiaco, l.momento_lectura FROM pacientes p LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente LEFT JOIN LATERAL (SELECT * FROM lecturas l WHERE l.id_pulsera = pu.id_pulsera ORDER BY l.momento_lectura DESC LIMIT 1) l ON TRUE WHERE p.id_paciente = %s;", (assigned,))
            r = cur.fetchone()
            if r:
                nombre = f"{r[1]} {r[2]} {r[3]}".strip()
                temp = r[5]
                ritmo = r[6]
                estado = 'N/A'
                if temp is not None and ritmo is not None:
                    if (temp < 35 or temp > 39.5) or (ritmo < 40 or ritmo > 130):
                        estado = 'Crítico'
                    elif (36 <= temp <= 37.5) and (60 <= ritmo <= 100):
                        estado = 'Estable'
                    else:
                        estado = 'Advertencia'
                top_residentes = [{
                    'id_paciente': r[0],
                    'nombre': nombre,
                    'id_pulsera': r[4] or 'Sin asignar',
                    'estado': estado,
                    'momento_lectura': r[7]
                }]

            # Tendencias: promedios de signos vitales por día en últimos 7 días para la pulsera (si existe)
            try:
                if id_pulsera:
                    cur.execute("""
                        SELECT date_trunc('day', momento_lectura) as dia,
                               ROUND(AVG(temperatura_c), 1) as temp_promedio,
                               ROUND(AVG(ritmo_cardiaco), 0) as ritmo_promedio
                        FROM lecturas
                        WHERE id_pulsera = %s AND momento_lectura > NOW() - INTERVAL '7 days'
                          AND temperatura_c IS NOT NULL
                          AND ritmo_cardiaco IS NOT NULL
                        GROUP BY dia
                        ORDER BY dia;
                    """, (id_pulsera,))
                else:
                    # sin pulsera -> no hay lecturas
                    rows = []
                    cur.close()
                    conn.close()
                    trend_labels = []
                    trend_temperatura = [36.5] * 7
                    trend_ritmo = [75] * 7
                    return render_template("dashboard.html",
                                           username=username,
                                           user_role=user_role,
                                           total_pacientes=total_pacientes,
                                           criticos=criticos,
                                           estables=estables,
                                           top_residentes=top_residentes,
                                           trend_labels=trend_labels,
                                           trend_temperatura=trend_temperatura,
                                           trend_ritmo=trend_ritmo)

                rows = cur.fetchall()
                # usar timedelta importado a nivel de módulo
                labels = []
                temp_data = []
                ritmo_data = []
                today = datetime.now().date()
                day_map = {r[0].date(): (r[1] or 36.5, r[2] or 75) for r in rows}
                for i in range(6, -1, -1):
                    d = today - timedelta(days=i)
                    labels.append(d.strftime('%d/%m'))
                    temp, ritmo = day_map.get(d, (36.5, 75))
                    temp_data.append(float(temp))
                    ritmo_data.append(int(ritmo))

                trend_labels = labels
                trend_temperatura = temp_data
                trend_ritmo = ritmo_data

            except Exception:
                trend_labels = [(datetime.now().date() - timedelta(days=i)).strftime('%d/%m') for i in range(6, -1, -1)]
                trend_temperatura = [36.5, 36.6, 36.4, 36.7, 36.5, 36.6, 36.5]
                trend_ritmo = [75, 78, 72, 80, 76, 74, 77]

        else:
            # Usuario enfermero/medico/admin -> todo el sistema (comportamiento original)
            # Obtener conteo total de pacientes
            cur.execute("SELECT COUNT(*) FROM pacientes;")
            total_pacientes = cur.fetchone()[0] or 0

            # Estadísticas de últimas 24h (global)
            cur.execute("""
                SELECT 
                    COUNT(CASE WHEN (l.temperatura_c < 35 OR l.temperatura_c > 39.5) 
                              OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130) THEN 1 END) as criticos,
                    COUNT(CASE WHEN (l.temperatura_c BETWEEN 36 AND 37.5) AND (l.ritmo_cardiaco BETWEEN 60 AND 100) AND l.esta_puesta = true THEN 1 END) as estables
                FROM lecturas l
                WHERE l.momento_lectura > NOW() - INTERVAL '24 hours';
            """)
            stats = cur.fetchone()
            criticos = stats[0] if stats else 0
            estables = stats[1] if stats else 0

            # TOP RESIDENTES: lectura más reciente por paciente, ordenar por severidad y fecha
            try:
                cur.execute("""
                    SELECT p.id_paciente, p.nombre, p.apellido_paterno, p.apellido_materno,
                           pu.id_pulsera, l.temperatura_c, l.ritmo_cardiaco, l.momento_lectura
                    FROM pacientes p
                    LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
                    LEFT JOIN LATERAL (
                        SELECT * FROM lecturas l
                        WHERE l.id_pulsera = pu.id_pulsera
                        ORDER BY l.momento_lectura DESC LIMIT 1
                    ) l ON TRUE
                    ORDER BY
                      (CASE WHEN (l.temperatura_c < 35 OR l.temperatura_c > 39.5) OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130) THEN 1
                            WHEN (l.temperatura_c BETWEEN 36 AND 37.5) AND (l.ritmo_cardiaco BETWEEN 60 AND 100) AND l.esta_puesta = true THEN 2
                            ELSE 3 END) ASC NULLS LAST,
                      l.momento_lectura DESC
                    LIMIT 5;
                """)
                top_rows = cur.fetchall()
                top_residentes = []
                for r in top_rows:
                    nombre = f"{r[1]} {r[2]} {r[3]}".strip()
                    temp = r[5]
                    ritmo = r[6]
                    estado = 'N/A'
                    if temp is not None and ritmo is not None:
                        if (temp < 35 or temp > 39.5) or (ritmo < 40 or ritmo > 130):
                            estado = 'Crítico'
                        elif (36 <= temp <= 37.5) and (60 <= ritmo <= 100):
                            estado = 'Estable'
                        else:
                            estado = 'Advertencia'
                    top_residentes.append({
                        'id_paciente': r[0],
                        'nombre': nombre,
                        'id_pulsera': r[4] or 'Sin asignar',
                        'estado': estado,
                        'momento_lectura': r[7]
                    })
            except Exception:
                top_residentes = []

            # Tendencias últimos 7 días (global) - PROMEDIOS DE SIGNOS VITALES
            try:
                cur.execute("""
                    SELECT date_trunc('day', momento_lectura) as dia,
                           ROUND(AVG(temperatura_c), 1) as temp_promedio,
                           ROUND(AVG(ritmo_cardiaco), 0) as ritmo_promedio,
                           COUNT(*) as num_lecturas
                    FROM lecturas
                    WHERE momento_lectura > NOW() - INTERVAL '7 days'
                      AND temperatura_c IS NOT NULL
                      AND ritmo_cardiaco IS NOT NULL
                    GROUP BY dia
                    ORDER BY dia;
                """)
                rows = cur.fetchall()
                # usar timedelta importado a nivel de módulo
                labels = []
                temp_data = []
                ritmo_data = []
                today = datetime.now().date()
                day_map = {r[0].date(): (r[1] or 36.5, r[2] or 75) for r in rows}
                for i in range(6, -1, -1):
                    d = today - timedelta(days=i)
                    labels.append(d.strftime('%d/%m'))
                    temp, ritmo = day_map.get(d, (36.5, 75))
                    temp_data.append(float(temp))
                    ritmo_data.append(int(ritmo))
                trend_labels = labels
                trend_temperatura = temp_data
                trend_ritmo = ritmo_data
            except Exception as ex:
                print(f"Error en tendencias: {ex}")
                from datetime import timedelta
                trend_labels = [(datetime.now().date() - timedelta(days=i)).strftime('%d/%m') for i in range(6, -1, -1)]
                trend_temperatura = [36.5, 36.6, 36.4, 36.7, 36.5, 36.6, 36.5]
                trend_ritmo = [75, 78, 72, 80, 76, 74, 77]

        cur.close()
        conn.close()

    except Exception as e:
        # si ocurre un error de BD, devolver valores por defecto y mostrar dashboard vacío/moderado
        total_pacientes = total_pacientes or 0
        criticos = criticos or 0
        estables = estables or 0
        top_residentes = top_residentes or []
        trend_labels = trend_labels or []
        trend_temperatura = trend_temperatura if 'trend_temperatura' in locals() else [36.5] * 7
        trend_ritmo = trend_ritmo if 'trend_ritmo' in locals() else [75] * 7

    return render_template("dashboard.html",
                           username=username,
                           user_role=user_role,
                           total_pacientes=total_pacientes,
                           criticos=criticos,
                           estables=estables,
                           top_residentes=top_residentes,
                           trend_labels=trend_labels,
                           trend_temperatura=trend_temperatura,
                           trend_ritmo=trend_ritmo)


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
    user_role = session.get("tipo_usuario", "invitado")

    # Base query
    base_query = """
        SELECT p.*, pu.id_pulsera, l.temperatura_c, l.ritmo_cardiaco, l.esta_puesta, l.momento_lectura
        FROM pacientes p
        LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
        LEFT JOIN LATERAL (
            SELECT * FROM lecturas l
            WHERE l.id_pulsera = pu.id_pulsera
            ORDER BY l.momento_lectura DESC LIMIT 1
        ) l ON TRUE
    """

    params = []

    # If user is a familiar, only show their assigned patient
    if user_role == 'familiar':
        assigned = get_assigned_patient_id(username)
        if not assigned:
            # no assigned patient - render empty list
            return render_template("tabla_pacientes.html", username=username, pacientes=[])
        base_query += " WHERE p.id_paciente = %s"
        params.append(assigned)

    base_query += " ORDER BY p.id_paciente;"

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if params:
            cur.execute(base_query, tuple(params))
        else:
            cur.execute(base_query)
        rows = cur.fetchall()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error al consultar pacientes: {e}")
        return render_template("tabla_pacientes.html", username=session.get("username"), pacientes=[])

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

    username = session.get('username')
    user_role = session.get('tipo_usuario', 'invitado')

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

        # If familiar, restrict to assigned patient regardless of search
        if user_role == 'familiar':
            assigned = get_assigned_patient_id(username)
            if not assigned:
                return render_template(
                    "buscar_pacientes.html",
                    username=session.get("username"),
                    pacientes=[],
                    busqueda=busqueda,
                    estado_filtro=estado_filtro,
                    tiene_pulsera=tiene_pulsera,
                    total_resultados=0
                )
            query += " AND p.id_paciente = %s"
            params.append(int(assigned))

        else:
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
            print(f"Error en la búsqueda: {e}")
            return render_template("buscar_pacientes.html", username=session.get("username"), pacientes=[], busqueda=busqueda, estado_filtro=estado_filtro, tiene_pulsera=tiene_pulsera, total_resultados=0)

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
            conn = None
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                 INSERT INTO pacientes (nombre, apellido_paterno, apellido_materno, fecha_nacimiento)
                 VALUES (%s, %s, %s, %s) RETURNING id_paciente;
             """, (nombre, apellido_paterno, apellido_materno, fecha_nacimiento if fecha_nacimiento else None))

            id_paciente = cur.fetchone()[0]

            # Si se pide asignar pulsera, y no se proporcionó id_pulsera, usar el id_paciente como id_pulsera
            if asignar_pulsera:
                if not id_pulsera:
                    id_pulsera_to_use = int(id_paciente)
                else:
                    id_pulsera_to_use = int(id_pulsera)

                # Verificar conflicto (si la pulsera ya existe)
                cur.execute("SELECT 1 FROM pulseras WHERE id_pulsera = %s;", (id_pulsera_to_use,))
                if cur.fetchone():
                    conn.rollback()
                    cur.close()
                    conn.close()
                    return render_template("agregar_paciente.html",
                                           error=f"La pulsera {id_pulsera_to_use} ya está asignada",
                                           username=session.get("username"))

                cur.execute("""
                    INSERT INTO pulseras (id_pulsera, id_paciente, fecha_asignacion)
                    VALUES (%s, %s, NOW());
                """, (id_pulsera_to_use, id_paciente))

            # Commit y cerrar
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for("ver_pacientes"))

        except ValueError:
            # Error al convertir id_pulsera a int
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            return render_template("agregar_paciente.html",
                                   error="El ID de pulsera debe ser un número válido",
                                   username=session.get("username"))
        except Exception as e:
            try:
                if conn is not None:
                    conn.rollback()
            except Exception:
                pass
            print(f"Error al guardar paciente: {e}")
            return render_template("agregar_paciente.html",
                                   error="Error al guardar el paciente. Por favor inténtalo más tarde.",
                                   username=session.get("username"))

    # GET
    return render_template("agregar_paciente.html", username=session.get("username"))


# ================================
#   HISTORIAL MÉDICO DE PACIENTE
# ================================
@app.route("/historial-paciente/<int:id_paciente>")
def historial_paciente(id_paciente):
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get('username')
    user_role = session.get('tipo_usuario', 'invitado')

    # Si es familiar, verificar que tenga acceso a este paciente
    if user_role == 'familiar':
        assigned = get_assigned_patient_id(username)
        if not assigned or assigned != id_paciente:
            return render_template('historial_paciente.html',
                                   error="No tienes permiso para ver este paciente",
                                   paciente=None, entries=[])

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Obtener información del paciente
        cur.execute("""
            SELECT id_paciente, nombre, apellido_paterno, apellido_materno, fecha_nacimiento
            FROM pacientes
            WHERE id_paciente = %s;
        """, (id_paciente,))
        paciente = cur.fetchone()

        if not paciente:
            cur.close()
            conn.close()
            return render_template('historial_paciente.html',
                                   error="Paciente no encontrado",
                                   paciente=None, entries=[])

        # Obtener historial médico del paciente
        cur.execute("""
            SELECT id_historial, titulo, descripcion, creado_por, fecha
            FROM historial_medico
            WHERE id_paciente = %s
            ORDER BY fecha DESC;
        """, (id_paciente,))
        entries_raw = cur.fetchall()

        # Preparar las entradas con permisos de edición
        entries = []
        for e in entries_raw:
            can_edit = user_role in ['enfermero', 'medico', 'admin']
            entries.append({
                'id_historial': e['id_historial'],
                'titulo': e['titulo'],
                'descripcion': e['descripcion'],
                'creado_por': e['creado_por'],
                'fecha': e['fecha'].strftime('%d/%m/%Y %H:%M') if e['fecha'] else '',
                'can_edit': can_edit
            })

        cur.close()
        conn.close()

        return render_template('historial_paciente.html',
                               paciente=paciente,
                               entries=entries)

    except Exception as e:
        print(f"Error al cargar historial: {e}")
        return render_template('historial_paciente.html',
                               error="Error al cargar el historial",
                               paciente=None, entries=[])


# ================================
#   NUEVA ENTRADA DE HISTORIAL
# ================================
@app.route("/historial-paciente/<int:id_paciente>/nuevo", methods=["GET", "POST"])
def historial_paciente_nuevo(id_paciente):
    if not is_logged_in():
        return redirect(url_for("home"))

    user_role = session.get('tipo_usuario', 'invitado')
    username = session.get('username')

    # Solo enfermeros/médicos/admin pueden crear entradas
    if user_role not in ['enfermero', 'medico', 'admin']:
        return redirect(url_for('historial_paciente', id_paciente=id_paciente))

    if request.method == "POST":
        titulo = request.form.get("titulo", "").strip()
        descripcion = request.form.get("descripcion", "").strip()

        if not titulo:
            return render_template('historial_paciente_form.html',
                                   id_paciente=id_paciente,
                                   error="El título es obligatorio",
                                   titulo=titulo, descripcion=descripcion)

        try:
            conn = get_connection()
            cur = conn.cursor()
            cur.execute("""
                INSERT INTO historial_medico (id_paciente, titulo, descripcion, creado_por, fecha)
                VALUES (%s, %s, %s, %s, NOW());
            """, (id_paciente, titulo, descripcion, username))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('historial_paciente', id_paciente=id_paciente))
        except Exception as e:
            print(f"Error al crear entrada de historial: {e}")
            return render_template('historial_paciente_form.html',
                                   id_paciente=id_paciente,
                                   error="Error al guardar la entrada",
                                   titulo=titulo, descripcion=descripcion)

    # GET - mostrar formulario
    return render_template('historial_paciente_form.html', id_paciente=id_paciente)


# ================================
#   EDITAR ENTRADA DE HISTORIAL
# ================================
@app.route("/historial-paciente/<int:id_paciente>/editar/<int:id_historial>", methods=["GET", "POST"])
def editar_historial(id_paciente, id_historial):
    if not is_logged_in():
        return redirect(url_for("home"))

    user_role = session.get('tipo_usuario', 'invitado')

    # Solo enfermeros/médicos/admin pueden editar
    if user_role not in ['enfermero', 'medico', 'admin']:
        return redirect(url_for('historial_paciente', id_paciente=id_paciente))

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        if request.method == "POST":
            titulo = request.form.get("titulo", "").strip()
            descripcion = request.form.get("descripcion", "").strip()

            if not titulo:
                cur.execute("SELECT titulo, descripcion FROM historial_medico WHERE id_historial = %s;", (id_historial,))
                entry = cur.fetchone()
                cur.close()
                conn.close()
                return render_template('historial_paciente_form.html',
                                       id_paciente=id_paciente,
                                       id_historial=id_historial,
                                       error="El título es obligatorio",
                                       titulo=titulo, descripcion=descripcion)

            cur.execute("""
                UPDATE historial_medico
                SET titulo = %s, descripcion = %s
                WHERE id_historial = %s AND id_paciente = %s;
            """, (titulo, descripcion, id_historial, id_paciente))
            conn.commit()
            cur.close()
            conn.close()
            return redirect(url_for('historial_paciente', id_paciente=id_paciente))

        # GET - cargar datos existentes
        cur.execute("SELECT titulo, descripcion FROM historial_medico WHERE id_historial = %s;", (id_historial,))
        entry = cur.fetchone()
        cur.close()
        conn.close()

        if not entry:
            return redirect(url_for('historial_paciente', id_paciente=id_paciente))

        return render_template('historial_paciente_form.html',
                               id_paciente=id_paciente,
                               id_historial=id_historial,
                               titulo=entry['titulo'],
                               descripcion=entry['descripcion'])

    except Exception as e:
        print(f"Error al editar historial: {e}")
        return redirect(url_for('historial_paciente', id_paciente=id_paciente))


# ================================
#   ELIMINAR ENTRADA DE HISTORIAL
# ================================
@app.route("/historial-paciente/<int:id_paciente>/eliminar/<int:id_historial>", methods=["POST"])
def eliminar_historial(id_paciente, id_historial):
    if not is_logged_in():
        return redirect(url_for("home"))

    user_role = session.get('tipo_usuario', 'invitado')

    # Solo enfermeros/médicos/admin pueden eliminar
    if user_role not in ['enfermero', 'medico', 'admin']:
        return redirect(url_for('historial_paciente', id_paciente=id_paciente))

    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("DELETE FROM historial_medico WHERE id_historial = %s AND id_paciente = %s;",
                    (id_historial, id_paciente))
        conn.commit()
        cur.close()
        conn.close()
    except Exception as e:
        print(f"Error al eliminar entrada de historial: {e}")

    return redirect(url_for('historial_paciente', id_paciente=id_paciente))


# ================================
#   CAMBIAR CONTRASEÑA
# ================================
@app.route("/cambiar-contrasena", methods=["GET", "POST"])
def cambiar_contrasena():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get('username')

    if request.method == "POST":
        password_actual = request.form.get("password_actual", "")
        password_nueva = request.form.get("password_nueva", "")
        password_confirmar = request.form.get("password_confirmar", "")

        if not password_actual or not password_nueva:
            return render_template("cambiar_contrasena.html",
                                   username=username,
                                   error="Todos los campos son obligatorios")

        if password_nueva != password_confirmar:
            return render_template("cambiar_contrasena.html",
                                   username=username,
                                   error="Las contraseñas nuevas no coinciden")

        if len(password_nueva) < 6:
            return render_template("cambiar_contrasena.html",
                                   username=username,
                                   error="La contraseña debe tener al menos 6 caracteres")

        try:
            conn = get_connection()
            cur = conn.cursor()

            # Verificar contraseña actual
            cur.execute("SELECT password_hash FROM usuarios WHERE username = %s;", (username,))
            row = cur.fetchone()

            if not row or not check_password(password_actual, row[0]):
                cur.close()
                conn.close()
                return render_template("cambiar_contrasena.html",
                                       username=username,
                                       error="Contraseña actual incorrecta")

            # Actualizar contraseña
            nueva_hash = hash_password(password_nueva)
            cur.execute("UPDATE usuarios SET password_hash = %s WHERE username = %s;",
                        (nueva_hash, username))
            conn.commit()
            cur.close()
            conn.close()

            return render_template("cambiar_contrasena.html",
                                   username=username,
                                   success="Contraseña actualizada correctamente")

        except Exception as e:
            print(f"Error al cambiar contraseña: {e}")
            return render_template("cambiar_contrasena.html",
                                   username=username,
                                   error="Error al cambiar la contraseña")

    return render_template("cambiar_contrasena.html", username=username)


# ================================
#   SEMÁFORO - VISTA DE ESTADO GLOBAL
# ================================
@app.route("/semaforo")
def semaforo():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get('username')
    user_role = session.get('tipo_usuario', 'invitado')

    pacientes = []

    # Query similar a la usada en ver_pacientes/buscar_pacientes: lectura más reciente por pulsera
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
        ORDER BY p.id_paciente;
    """

    params = []

    try:
        # Si es familiar, limitar a su paciente asignado
        if user_role == 'familiar':
            assigned = get_assigned_patient_id(username)
            if not assigned:
                # usuario familiar sin asignación -> lista vacía
                return render_template('semaforo.html', username=username, pacientes=[])
            query = query.replace('\n        WHERE 1=1\n', '\n        WHERE p.id_paciente = %s\n')
            params.append(int(assigned))

        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        if params:
            cur.execute(query, tuple(params))
        else:
            cur.execute(query)
        rows = cur.fetchall()
        cur.close()
        conn.close()

        for r in rows:
            nombre_completo = f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}".strip()
            temp = r['temperatura_c']
            ritmo = r['ritmo_cardiaco']
            esta_puesta = r['esta_puesta']

            estado = 'azul'
            if temp is not None and ritmo is not None:
                if (temp < 35 or temp > 39.5) or (ritmo < 40 or ritmo > 130):
                    estado = 'rojo'
                elif (36 <= temp <= 37.5) and (60 <= ritmo <= 100) and esta_puesta:
                    estado = 'verde'
                else:
                    estado = 'azul'

            pacientes.append({
                'id_paciente': r['id_paciente'],
                'nombre': nombre_completo,
                'id_pulsera': r['id_pulsera'] if r['id_pulsera'] is not None else 'Sin asignar',
                'temperatura_c': temp,
                'ritmo_cardiaco': ritmo,
                'esta_puesta': esta_puesta,
                'momento_lectura': r['momento_lectura'],
                'estado': estado,
                'estado_texto': {'rojo': 'Crítico', 'verde': 'Estable', 'azul': 'Advertencia'}[estado]
            })

    except Exception as e:
        # En caso de error de BD devolvemos lista vacía y lo registramos
        print(f"Error en semaforo: {e}")
        pacientes = []

    return render_template('semaforo.html', username=username, pacientes=pacientes)


# ================================
#   API JSON PARA PULSERAS/SENSORES
# ================================

@app.route("/pulsera/<int:id_pulsera>/lectura", methods=["POST"])
def registrar_lectura(id_pulsera):
    """
    Endpoint para que las pulseras envíen lecturas de sensores.
    Body JSON: {
        "ritmo_cardiaco": int,
        "temperatura_c": float,
        "esta_puesta": bool
    }
    """
    try:
        data = request.get_json()

        if not data:
            return {"error": "No se recibieron datos JSON"}, 400

        ritmo_cardiaco = data.get("ritmo_cardiaco")
        temperatura_c = data.get("temperatura_c")
        esta_puesta = data.get("esta_puesta")

        # Validaciones básicas
        if ritmo_cardiaco is None or temperatura_c is None or esta_puesta is None:
            return {"error": "Faltan campos requeridos: ritmo_cardiaco, temperatura_c, esta_puesta"}, 400

        # Verificar que la pulsera existe
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT id_paciente FROM pulseras WHERE id_pulsera = %s;", (id_pulsera,))
        pulsera = cur.fetchone()

        if not pulsera:
            cur.close()
            conn.close()
            return {"error": f"Pulsera {id_pulsera} no encontrada"}, 404

        # Insertar lectura (momento_lectura se auto-genera con DEFAULT NOW())
        cur.execute("""
            INSERT INTO lecturas (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta)
            VALUES (%s, %s, %s, %s)
            RETURNING id_lectura, momento_lectura;
        """, (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta))

        result = cur.fetchone()
        id_lectura = result[0]
        momento_lectura = result[1]

        conn.commit()
        cur.close()
        conn.close()

        return {
            "success": True,
            "id_lectura": id_lectura,
            "id_pulsera": id_pulsera,
            "momento_lectura": momento_lectura.isoformat() if momento_lectura else None,
            "mensaje": "Lectura registrada correctamente"
        }, 201

    except Exception as e:
        print(f"Error al registrar lectura: {e}")
        return {"error": "Error interno al procesar la lectura", "detalle": str(e)}, 500


@app.route("/pulsera/<int:id_pulsera>/lecturas", methods=["GET"])
def obtener_lecturas(id_pulsera):
    """
    Endpoint para obtener lecturas de una pulsera.
    Query params:
        - limit: número máximo de lecturas (default 10, max 100)
    """
    try:
        # Obtener parámetro limit
        limit = request.args.get("limit", "10")
        try:
            limit = int(limit)
            if limit < 1:
                limit = 10
            elif limit > 100:
                limit = 100
        except ValueError:
            limit = 10

        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Verificar que la pulsera existe
        cur.execute("SELECT id_paciente FROM pulseras WHERE id_pulsera = %s;", (id_pulsera,))
        pulsera = cur.fetchone()

        if not pulsera:
            cur.close()
            conn.close()
            return {"error": f"Pulsera {id_pulsera} no encontrada"}, 404

        # Obtener lecturas
        cur.execute("""
            SELECT id_lectura, ritmo_cardiaco, temperatura_c, esta_puesta, momento_lectura
            FROM lecturas
            WHERE id_pulsera = %s
            ORDER BY momento_lectura DESC
            LIMIT %s;
        """, (id_pulsera, limit))

        lecturas_raw = cur.fetchall()
        cur.close()
        conn.close()

        # Formatear respuesta
        lecturas = []
        for l in lecturas_raw:
            lecturas.append({
                "id_lectura": l["id_lectura"],
                "ritmo_cardiaco": l["ritmo_cardiaco"],
                "temperatura_c": float(l["temperatura_c"]) if l["temperatura_c"] is not None else None,
                "esta_puesta": l["esta_puesta"],
                "momento_lectura": l["momento_lectura"].isoformat() if l["momento_lectura"] else None
            })

        return {
            "id_pulsera": id_pulsera,
            "total_lecturas": len(lecturas),
            "lecturas": lecturas
        }, 200

    except Exception as e:
        print(f"Error al obtener lecturas: {e}")
        return {"error": "Error interno al obtener lecturas", "detalle": str(e)}, 500


# ================================
#   DEBUG/TESTING ENDPOINTS
# ================================

@app.route("/debug-conn")
def debug_conn():
    """Endpoint para probar la conexión a la base de datos"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute("SELECT version();")
        version = cur.fetchone()[0]

        # Contar registros en tablas principales
        cur.execute("SELECT COUNT(*) FROM pacientes;")
        count_pacientes = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM pulseras;")
        count_pulseras = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM lecturas;")
        count_lecturas = cur.fetchone()[0]

        cur.close()
        conn.close()

        return {
            "status": "OK",
            "database_version": version,
            "estadisticas": {
                "pacientes": count_pacientes,
                "pulseras": count_pulseras,
                "lecturas": count_lecturas
            }
        }, 200

    except Exception as e:
        return {
            "status": "ERROR",
            "error": str(e)
        }, 500


@app.route("/sensor")
def sensor():
    """Endpoint legacy para probar conexión (mantener compatibilidad)"""
    return debug_conn()


# ================================
#   CHATBOT CON IA (GROQ)
# ================================

@app.route("/api/chatbot", methods=["POST"])
def chatbot_api():
    """API del chatbot - recibe mensaje y devuelve respuesta de IA"""
    if not is_logged_in():
        return jsonify({"error": "No autorizado"}), 401

    try:
        data = request.get_json()
        user_message = data.get("message", "").strip()

        if not user_message:
            return jsonify({"error": "Mensaje vacío"}), 400

        # Obtener información del usuario
        username = session.get("username")
        user_role = session.get("user_role", "familiar")

        # Obtener contexto de la base de datos para la IA
        conn = get_db_connection()
        cur = conn.cursor()

        # Contexto según el rol del usuario
        contexto_db = obtener_contexto_chatbot(cur, user_role, username)

        cur.close()
        conn.close()

        # Llamar a Groq API
        groq_api_key = os.getenv("GROQ_API_KEY")
        if not groq_api_key:
            return jsonify({"error": "API key de Groq no configurada. Agrega GROQ_API_KEY a tu archivo .env"}), 500

        client = Groq(api_key=groq_api_key)

        # Crear el prompt del sistema con contexto
        system_prompt = f"""Eres un asistente médico virtual para el sistema 'Vida en Mano', un sistema de monitoreo de pacientes en residencias de ancianos.

INFORMACIÓN DEL USUARIO:
- Nombre: {username}
- Rol: {user_role}

CONTEXTO DE LA BASE DE DATOS:
{contexto_db}

INSTRUCCIONES:
1. Responde de forma clara, concisa y profesional
2. Si te preguntan por pacientes, usa la información del contexto
3. Si te preguntan por lecturas médicas (temperatura, ritmo cardíaco), explica los valores
4. Valores normales de referencia:
   - Temperatura: 36-37.5°C
   - Ritmo cardíaco: 60-100 bpm
5. Si no tienes información suficiente, indícalo claramente
6. Mantén un tono empático y profesional
7. Responde en español

RESTRICCIONES:
- Solo proporciona información médica general, NO diagnósticos
- Si es un familiar, solo habla de su paciente asignado
- NO inventes datos que no estén en el contexto"""

        # Llamar a Groq
        chat_completion = client.chat.completions.create(
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_message}
            ],
            model="llama-3.3-70b-versatile",  # Modelo rápido y capaz
            temperature=0.7,
            max_tokens=1024,
        )

        respuesta_ia = chat_completion.choices[0].message.content

        return jsonify({
            "success": True,
            "response": respuesta_ia,
            "timestamp": datetime.now().isoformat()
        })

    except Exception as e:
        return jsonify({"error": f"Error en chatbot: {str(e)}"}), 500


def obtener_contexto_chatbot(cur, user_role, username):
    """Obtiene información relevante de la BD para el contexto del chatbot"""
    contexto = ""

    try:
        # Estadísticas generales
        cur.execute("SELECT COUNT(*) FROM pacientes;")
        total_pacientes = cur.fetchone()[0]

        cur.execute("SELECT COUNT(*) FROM lecturas WHERE momento_lectura > NOW() - INTERVAL '24 hours';")
        lecturas_24h = cur.fetchone()[0]

        contexto += f"ESTADÍSTICAS GENERALES:\n"
        contexto += f"- Total de pacientes: {total_pacientes}\n"
        contexto += f"- Lecturas en últimas 24h: {lecturas_24h}\n\n"

        # Si es familiar, solo su paciente
        if user_role == "familiar":
            cur.execute("""
                SELECT u.id_paciente_asignado
                FROM usuarios u
                WHERE u.username = %s;
            """, (username,))
            result = cur.fetchone()

            if result and result[0]:
                id_paciente = result[0]

                # Información del paciente
                cur.execute("""
                    SELECT p.nombre, p.apellido_paterno, p.apellido_materno,
                           p.fecha_nacimiento, p.genero
                    FROM pacientes p
                    WHERE p.id_paciente = %s;
                """, (id_paciente,))
                paciente = cur.fetchone()

                if paciente:
                    edad = (date.today() - paciente[3]).days // 365
                    contexto += f"PACIENTE ASIGNADO:\n"
                    contexto += f"- Nombre: {paciente[0]} {paciente[1]} {paciente[2]}\n"
                    contexto += f"- Edad: {edad} años\n"
                    contexto += f"- Género: {paciente[4]}\n\n"

                    # Última lectura
                    cur.execute("""
                        SELECT l.temperatura_c, l.ritmo_cardiaco, l.esta_puesta, l.momento_lectura
                        FROM lecturas l
                        INNER JOIN pulseras pu ON pu.id_pulsera = l.id_pulsera
                        WHERE pu.id_paciente = %s
                        ORDER BY l.momento_lectura DESC
                        LIMIT 1;
                    """, (id_paciente,))
                    lectura = cur.fetchone()

                    if lectura:
                        contexto += f"ÚLTIMA LECTURA:\n"
                        contexto += f"- Temperatura: {lectura[0]}°C\n"
                        contexto += f"- Ritmo cardíaco: {lectura[1]} bpm\n"
                        contexto += f"- Pulsera puesta: {'Sí' if lectura[2] else 'No'}\n"
                        contexto += f"- Momento: {lectura[3]}\n"

        # Si es staff, información general
        else:
            # Top 5 pacientes recientes
            cur.execute("""
                SELECT p.nombre, p.apellido_paterno, l.temperatura_c, l.ritmo_cardiaco,
                       l.esta_puesta, l.momento_lectura
                FROM pacientes p
                LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
                LEFT JOIN LATERAL (
                    SELECT * FROM lecturas
                    WHERE id_pulsera = pu.id_pulsera
                    ORDER BY momento_lectura DESC
                    LIMIT 1
                ) l ON true
                WHERE l.momento_lectura IS NOT NULL
                ORDER BY l.momento_lectura DESC
                LIMIT 5;
            """)
            pacientes_recientes = cur.fetchall()

            if pacientes_recientes:
                contexto += "PACIENTES CON LECTURAS RECIENTES:\n"
                for pac in pacientes_recientes:
                    contexto += f"- {pac[0]} {pac[1]}: Temp {pac[2]}°C, Ritmo {pac[3]} bpm, Pulsera: {'Sí' if pac[4] else 'No'}\n"
                contexto += "\n"

            # Estadísticas de criticidad
            cur.execute("""
                SELECT
                    COUNT(*) FILTER (WHERE (temperatura_c < 35 OR temperatura_c > 39.5)
                                       OR (ritmo_cardiaco < 40 OR ritmo_cardiaco > 130)) as criticos,
                    COUNT(*) FILTER (WHERE (temperatura_c BETWEEN 36 AND 37.5)
                                       AND (ritmo_cardiaco BETWEEN 60 AND 100)
                                       AND esta_puesta = true) as estables
                FROM lecturas
                WHERE momento_lectura > NOW() - INTERVAL '24 hours';
            """)
            stats = cur.fetchone()

            if stats:
                contexto += f"ESTADO DE PACIENTES (últimas 24h):\n"
                contexto += f"- Lecturas críticas: {stats[0]}\n"
                contexto += f"- Lecturas estables: {stats[1]}\n"

    except Exception as e:
        contexto += f"\n[Error obteniendo contexto: {str(e)}]"

    return contexto


# -----------------------------
# Ejecutar aplicación cuando se lance el script
# -----------------------------
if __name__ == '__main__':
    # Permitir configurar puerto/host/debug vía variables de entorno
    port = int(os.environ.get('PORT', 5000))
    debug_env = os.environ.get('FLASK_DEBUG', '').lower()
    debug = True if debug_env in ('1', 'true', 'yes') else False
    # En desarrollo usualmente se quiere debug=True; si no se especifica, usar True
    if debug_env == '':
        debug = True
    app.run(host='0.0.0.0', port=port, debug=debug)
