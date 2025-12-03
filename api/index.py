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

# ================================
#   CONFIGURACIÓN Y CONEXIÓN
# ================================
load_dotenv()

DB_URL = os.getenv("DB_URL")
if not DB_URL:
    raise RuntimeError("No se encontró la variable de entorno 'DB_URL'.")

app = Flask(__name__)
app.secret_key = os.getenv("FLASK_SECRET_KEY", "super-secret-key-change-this")

# ================================
#   FILTROS PERSONALIZADOS PARA TEMPLATES
# ================================

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


def get_connection():
    return psycopg2.connect(DB_URL)


def is_logged_in():
    return session.get("logged_in") is True


# ================================
#   FUNCIONES AUXILIARES PARA ROLES
# ================================
def get_user_role(username):
    """Obtiene el rol de un usuario"""
    try:
        conn = get_connection()
        cur = conn.cursor()
        cur.execute(
            "SELECT rol FROM usuarios WHERE username = %s;",
            (username,)
        )
        row = cur.fetchone()
        cur.close()
        conn.close()
        return row[0] if row else 'enfermero'
    except Exception:
        return 'enfermero'


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
        cur.execute("""
            SELECT id_usuario, password_hash, rol, activo 
            FROM usuarios 
            WHERE username = %s;
        """, (username,))
        row = cur.fetchone()
        cur.close()
        conn.close()
    except Exception as e:
        return f"Error al consultar usuarios: {e}"

    if row is None:
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))

    id_usuario, stored_hash, rol, activo = row

    if not activo:
        return redirect(url_for("home", error="Usuario desactivado. Contacta al administrador."))

    # Verificar contraseña
    password_correct = False

    if password == stored_hash:
        password_correct = True

    if password_correct:
        session["logged_in"] = True
        session["username"] = username
        session["user_role"] = rol
        session["user_id"] = id_usuario
        return redirect(url_for("dashboard"))
    else:
        return redirect(url_for("home", error="Usuario o contraseña incorrectos"))


@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for("home"))


# ================================
#   REGISTRO DE NUEVOS USUARIOS
# ================================
@app.route("/registro", methods=["GET", "POST"])
def registro():
    """Página para que nuevos usuarios se registren"""
    if request.method == "POST":
        username = request.form.get("username", "").strip()
        password = request.form.get("password", "")
        confirm_password = request.form.get("confirm_password", "")
        rol_solicitado = request.form.get("rol", "enfermero")

        # Validaciones
        if not username or not password:
            return render_template("registro.html", error="Usuario y contraseña son obligatorios")

        if password != confirm_password:
            return render_template("registro.html", error="Las contraseñas no coinciden")

        if len(password) < 6:
            return render_template("registro.html", error="La contraseña debe tener al menos 6 caracteres")

        try:
            conn = get_connection()
            cur = conn.cursor()

            # Verificar si el usuario ya existe
            cur.execute("SELECT 1 FROM usuarios WHERE username = %s;", (username,))
            if cur.fetchone():
                cur.close()
                conn.close()
                return render_template("registro.html", error="El nombre de usuario ya está en uso")

            # Insertar nuevo usuario
            cur.execute("""
                INSERT INTO usuarios (username, password_hash, rol, activo)
                VALUES (%s, %s, %s, TRUE)
                RETURNING id_usuario;
            """, (username, password, rol_solicitado))

            id_usuario = cur.fetchone()[0]
            conn.commit()
            cur.close()
            conn.close()

            # Auto-login después del registro
            session["logged_in"] = True
            session["username"] = username
            session["user_role"] = rol_solicitado
            session["user_id"] = id_usuario

            return redirect(url_for("dashboard"))

        except Exception as e:
            return f"<h3>Error en el registro: {e}</h3>"

    return render_template("registro.html")


# ================================
#   DASHBOARD PRINCIPAL
# ================================
@app.route("/dashboard")
def dashboard():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get("username")
    user_role = session.get("user_role", "enfermero")

    # Contar pacientes según rol
    try:
        conn = get_connection()
        cur = conn.cursor()

        if user_role in ['admin', 'medico']:
            cur.execute("SELECT COUNT(*) FROM pacientes;")
        elif user_role == 'enfermero':
            cur.execute("""
                SELECT COUNT(DISTINCT ae.id_paciente) 
                FROM asignaciones_enfermero ae
                JOIN usuarios u ON u.id_usuario = ae.id_usuario
                WHERE u.username = %s;
            """, (username,))
        elif user_role == 'familiar':
            cur.execute("""
                SELECT COUNT(DISTINCT fa.id_paciente) 
                FROM familiares_autorizados fa
                JOIN usuarios u ON u.id_usuario = fa.id_usuario
                WHERE u.username = %s;
            """, (username,))

        total_pacientes = cur.fetchone()[0] or 0

        # Obtener estadísticas recientes
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
#   RUTA: MI PERFIL
# ================================
@app.route("/mi-perfil")
def mi_perfil():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get("username")
    user_role = session.get("user_role", "enfermero")

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Obtener información del usuario
        cur.execute("""
            SELECT username, rol, fecha_creacion 
            FROM usuarios 
            WHERE username = %s;
        """, (username,))
        usuario = cur.fetchone()

        # Obtener pacientes asignados según rol
        if user_role == 'enfermero':
            cur.execute("""
                SELECT p.nombre, p.apellido_paterno, p.apellido_materno, p.id_paciente
                FROM asignaciones_enfermero ae
                JOIN pacientes p ON p.id_paciente = ae.id_paciente
                JOIN usuarios u ON u.id_usuario = ae.id_usuario
                WHERE u.username = %s;
            """, (username,))
            asignaciones = cur.fetchall()
        elif user_role == 'familiar':
            cur.execute("""
                SELECT p.nombre, p.apellido_paterno, p.apellido_materno, p.id_paciente, fa.parentesco
                FROM familiares_autorizados fa
                JOIN pacientes p ON p.id_paciente = fa.id_paciente
                JOIN usuarios u ON u.id_usuario = fa.id_usuario
                WHERE u.username = %s;
            """, (username,))
            asignaciones = cur.fetchall()
        else:
            asignaciones = []

        cur.close()
        conn.close()

    except Exception as e:
        return f"<h3>Error al cargar perfil: {e}</h3>"

    return render_template("mi_perfil.html",
                           username=username,
                           user_role=user_role,
                           usuario=usuario,
                           asignaciones=asignaciones)


# ================================
#   VER PACIENTES (TABLA)
# ================================
@app.route("/ver-pacientes")
def ver_pacientes():
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get("username")
    user_role = session.get("user_role", "enfermero")

    # Construir query según rol
    if user_role in ['admin', 'medico']:
        query = """
            SELECT p.*, pu.id_pulsera 
            FROM pacientes p
            LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
            ORDER BY p.id_paciente;
        """
        params = []
    else:
        query = """
            SELECT p.*, pu.id_pulsera 
            FROM pacientes p
            LEFT JOIN pulseras pu ON pu.id_paciente = p.id_paciente
            WHERE p.id_paciente IN (
                SELECT ae.id_paciente FROM asignaciones_enfermero ae
                JOIN usuarios u ON u.id_usuario = ae.id_usuario
                WHERE u.username = %s
            )
            ORDER BY p.id_paciente;
        """
        params = [username]

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(query, tuple(params))
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
            "id_pulsera": r["id_pulsera"] if r["id_pulsera"] is not None else "Sin asignar",
        })

    return render_template("tabla_pacientes.html",
                           username=username,
                           user_role=user_role,
                           pacientes=pacientes)


# ================================
#   BUSCADOR DE PACIENTES
# ================================
@app.route("/buscar-pacientes", methods=["GET", "POST"])
def buscar_pacientes():
    if not is_logged_in():
        return redirect(url_for("home"))

    pacientes = []
    query_filtros = []
    params = []

    if request.method == "POST":
        # Obtener criterios de búsqueda
        busqueda = request.form.get("busqueda", "").strip()
        estado_filtro = request.form.get("estado", "")
        tiene_pulsera = request.form.get("tiene_pulsera", "")

        # Construir la consulta base
        query = """
            SELECT DISTINCT
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
            WHERE 1=1
        """

        # Filtro por texto (nombre, apellido, ID)
        if busqueda:
            if busqueda.isdigit():
                query += " AND p.id_paciente = %s"
                params.append(int(busqueda))
            else:
                query += " AND (p.nombre ILIKE %s OR p.apellido_paterno ILIKE %s OR p.apellido_materno ILIKE %s)"
                termino_busqueda = f"%{busqueda}%"
                params.extend([termino_busqueda, termino_busqueda, termino_busqueda])

        # Filtro por estado del semáforo
        if estado_filtro:
            if estado_filtro == "rojo":
                query += " AND ((l.temperatura_c < 35 OR l.temperatura_c > 39.5) OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130))"
            elif estado_filtro == "verde":
                query += " AND (l.temperatura_c BETWEEN 36 AND 37.5) AND (l.ritmo_cardiaco BETWEEN 60 AND 100) AND l.esta_puesta = true"
            elif estado_filtro == "azul":
                query += " AND NOT ((l.temperatura_c < 35 OR l.temperatura_c > 39.5) OR (l.ritmo_cardiaco < 40 OR l.ritmo_cardiaco > 130))"
                query += " AND NOT ((l.temperatura_c BETWEEN 36 AND 37.5) AND (l.ritmo_cardiaco BETWEEN 60 AND 100) AND l.esta_puesta = true)"

        # Filtro por pulsera
        if tiene_pulsera == "con":
            query += " AND pu.id_pulsera IS NOT NULL"
        elif tiene_pulsera == "sin":
            query += " AND pu.id_pulsera IS NULL"

        # Ordenar resultados
        query += " ORDER BY p.id_paciente"

        try:
            conn = get_connection()
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute(query, tuple(params))
            rows = cur.fetchall()
            cur.close()
            conn.close()

            # Procesar resultados
            def calcular_edad(fecha_nacimiento):
                if not fecha_nacimiento:
                    return None
                hoy = date.today()
                return hoy.year - fecha_nacimiento.year - (
                        (hoy.month, hoy.day) < (fecha_nacimiento.month, fecha_nacimiento.day)
                )

            for r in rows:
                nombre_completo = f"{r['nombre']} {r['apellido_paterno']} {r['apellido_materno']}"

                # Determinar estado
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
                    "estado_texto": {
                        "rojo": "Crítico",
                        "verde": "Estable",
                        "azul": "Advertencia"
                    }[estado]
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
#   VER BASE DE DATOS COMPLETA (SIN FILTROS DE ROL)
# ================================
@app.route("/ver-bd-completa")
def ver_bd_completa():
    """
    Vista especial para ver toda la base de datos sin filtros por rol.
    Requiere autenticación pero no restricciones de rol.
    """
    if not is_logged_in():
        return redirect(url_for("home"))

    username = session.get("username")
    user_role = session.get("user_role", "enfermero")

    # Obtener todas las tablas y sus datos
    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # 1. Obtener lista de tablas
        cur.execute("""
            SELECT table_name 
            FROM information_schema.tables 
            WHERE table_schema = 'public' 
            AND table_type = 'BASE TABLE'
            ORDER BY table_name;
        """)
        tablas = [row['table_name'] for row in cur.fetchall()]

        datos_tablas = {}

        # 2. Obtener datos de cada tabla
        for tabla in tablas:
            try:
                # Obtener columnas
                cur.execute(f"""
                    SELECT column_name, data_type 
                    FROM information_schema.columns 
                    WHERE table_name = '{tabla}' 
                    ORDER BY ordinal_position;
                """)
                columnas = cur.fetchall()

                # Obtener datos
                cur.execute(f"SELECT * FROM {tabla} ORDER BY 1 LIMIT 1000;")
                filas = cur.fetchall()

                datos_tablas[tabla] = {
                    'columnas': columnas,
                    'filas': filas,
                    'total_filas': len(filas)
                }
            except Exception as e:
                datos_tablas[tabla] = {
                    'error': str(e),
                    'columnas': [],
                    'filas': [],
                    'total_filas': 0
                }

        # 3. Obtener estadísticas generales
        estadisticas = {}

        # Contar registros por tabla
        for tabla in tablas:
            cur.execute(f"SELECT COUNT(*) as total FROM {tabla};")
            total = cur.fetchone()['total']
            estadisticas[tabla] = total

        cur.close()
        conn.close()

    except Exception as e:
        return f"<h3>Error al consultar base de datos: {e}</h3>"

    return render_template("ver_bd_completa.html",
                           username=username,
                           user_role=user_role,
                           tablas=tablas,
                           datos_tablas=datos_tablas,
                           estadisticas=estadisticas)

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
#   RUTAS ADMINISTRATIVAS
# ================================
@app.route("/admin")
def admin_panel():
    if not is_logged_in():
        return redirect(url_for("home"))

    user_role = session.get("user_role", "enfermero")
    if user_role != 'admin':
        return "Acceso denegado. Se requiere rol de administrador.", 403

    try:
        conn = get_connection()
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # Obtener todos los usuarios
        cur.execute("""
            SELECT username, rol, fecha_creacion, activo 
            FROM usuarios 
            ORDER BY fecha_creacion DESC;
        """)
        usuarios = cur.fetchall()

        # Obtener estadísticas
        cur.execute("""
            SELECT 
                COUNT(*) as total_usuarios,
                COUNT(CASE WHEN rol = 'admin' THEN 1 END) as admins,
                COUNT(CASE WHEN rol = 'medico' THEN 1 END) as medicos,
                COUNT(CASE WHEN rol = 'enfermero' THEN 1 END) as enfermeros,
                COUNT(CASE WHEN rol = 'familiar' THEN 1 END) as familiares
            FROM usuarios;
        """)
        stats = cur.fetchone()

        cur.close()
        conn.close()

    except Exception as e:
        return f"<h3>Error en panel admin: {e}</h3>"

    return render_template("admin_panel.html",
                           username=session.get("username"),
                           user_role=user_role,
                           usuarios=usuarios,
                           stats=stats)


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