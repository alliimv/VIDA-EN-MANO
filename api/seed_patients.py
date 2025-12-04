#!/usr/bin/env python3
"""
seed_patients.py
Script idempotente para insertar 55 pacientes de ejemplo realistas en la tabla `pacientes`
y asignarles una pulsera cuyo id sea igual al id_paciente (si es posible).

Uso: python api/seed_patients.py

El script lee DB_URL desde las variables de entorno (.env si existe).
"""
import os
from datetime import date, timedelta
import random
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()
DB_URL = os.getenv('DB_URL')
if not DB_URL:
    raise RuntimeError("No se encontró la variable de entorno DB_URL. Carga .env o exporta DB_URL")

random_seed = 42
rng = random.Random(random_seed)

FIRST = [
    'María','Ana','Carmen','Josefa','Isabel','Dolores','Rosa','Pilar','Luisa','Antonia',
    'Francisco','José','Manuel','Antonio','Juan','Miguel','Pedro','Luis','Jorge','Carlos',
    'Sergio','Andrés','Roberto','Eduardo','Enrique'
]

LAST1 = [
    'Gómez','Pérez','López','Sánchez','Martínez','García','Rodríguez','Fernández','Ruiz','Torres',
    'Ramírez','Flores','Rivera','Vargas','Ramos'
]

LAST2 = [
    'López','Hernández','González','Jiménez','Morales','Castro','Delgado','Medina','Ortiz','Silva'
]

TARGET = 55

# Generar combinaciones únicas hasta TARGET
names = []
used = set()
tries = 0
while len(names) < TARGET and tries < 10000:
    tries += 1
    first = rng.choice(FIRST)
    l1 = rng.choice(LAST1)
    l2 = rng.choice(LAST2)
    # fecha de nacimiento entre 1930-1959 (residentes mayores)
    year = rng.randint(1930, 1959)
    month = rng.randint(1, 12)
    # asegurar día válido
    day = rng.randint(1, 28)
    dob = date(year, month, day)
    key = (first, l1, l2, dob.isoformat())
    if key in used:
        continue
    used.add(key)
    names.append({'nombre': first, 'apellido_paterno': l1, 'apellido_materno': l2, 'fecha_nacimiento': dob})

if len(names) < TARGET:
    raise RuntimeError(f"No se pudieron generar suficientes nombres (generados {len(names)})")

# Conectar y sembrar
conn = None
inserted = 0
skipped = 0
pulsera_assigned = 0
warnings = []

try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor()

    for p in names:
        nombre = p['nombre']
        ap = p['apellido_paterno']
        am = p['apellido_materno']
        dob = p['fecha_nacimiento']

        # Verificar existencia
        cur.execute(
            "SELECT id_paciente FROM pacientes WHERE nombre = %s AND apellido_paterno = %s AND apellido_materno = %s AND fecha_nacimiento = %s",
            (nombre, ap, am, dob)
        )
        row = cur.fetchone()
        if row:
            skipped += 1
            id_paciente = row[0]
            # intentar asegurar que la pulsera con id = id_paciente exista y esté asignada a este paciente
            cur.execute('SELECT id_pulsera, id_paciente FROM pulseras WHERE id_pulsera = %s', (int(id_paciente),))
            pr = cur.fetchone()
            if not pr:
                try:
                    cur.execute('INSERT INTO pulseras (id_pulsera, id_paciente, fecha_asignacion) VALUES (%s, %s, NOW())', (int(id_paciente), id_paciente))
                    conn.commit()
                    pulsera_assigned += 1
                except Exception as e:
                    conn.rollback()
                    warnings.append(f"No se pudo insertar pulsera {id_paciente} para paciente existente {id_paciente}: {e}")
            continue

        # Insertar paciente
        try:
            cur.execute(
                "INSERT INTO pacientes (nombre, apellido_paterno, apellido_materno, fecha_nacimiento) VALUES (%s,%s,%s,%s) RETURNING id_paciente",
                (nombre, ap, am, dob)
            )
            id_paciente = cur.fetchone()[0]
            conn.commit()
            inserted += 1
        except Exception as e:
            conn.rollback()
            warnings.append(f"Error insert paciente {nombre} {ap} {am}: {e}")
            continue

        # Intentar asignar pulsera con mismo id
        try:
            cur.execute('SELECT id_pulsera, id_paciente FROM pulseras WHERE id_pulsera = %s', (int(id_paciente),))
            pr = cur.fetchone()
            if pr:
                # ya existe una pulsera con ese id
                if pr[1] == id_paciente or pr[1] is None:
                    # reasignar si es necesario
                    cur.execute('UPDATE pulseras SET id_paciente = %s, fecha_asignacion = NOW() WHERE id_pulsera = %s', (id_paciente, int(id_paciente)))
                    conn.commit()
                    pulsera_assigned += 1
                else:
                    warnings.append(f"Pulsera {id_paciente} ya existe asignada a otro paciente (id_paciente={pr[1]}). No se reasignó.")
            else:
                cur.execute('INSERT INTO pulseras (id_pulsera, id_paciente, fecha_asignacion) VALUES (%s, %s, NOW())', (int(id_paciente), id_paciente))
                conn.commit()
                pulsera_assigned += 1
        except Exception as e:
            conn.rollback()
            warnings.append(f"No se pudo insertar pulsera {id_paciente}: {e}")

    cur.close()

except Exception as e:
    print('ERROR al conectar o ejecutar queries:', e)

finally:
    if conn:
        conn.close()

print('--- Resultado del seed ---')
print(f'Target: {TARGET}  generados intentados: {len(names)}')
print(f'Insertados: {inserted}')
print(f'Saltados (ya existentes): {skipped}')
print(f'Pulseras asignadas/actualizadas: {pulsera_assigned}')
if warnings:
    print('\nWarnings:')
    for w in warnings:
        print('-', w)
print('Hecho.')

