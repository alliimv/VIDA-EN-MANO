#!/usr/bin/env python3
"""
seed_readings.py
Script idempotente para insertar lecturas de ejemplo en la tabla `lecturas`.
- Para cada pulsera existente en `pulseras`, si NO existen lecturas en los últimos `days_back` días,
  inserta `reads_per_pulsera` lecturas distribuidas en ese periodo.
- Valores generados: temperatura_c (°C), ritmo_cardiaco (bpm), esta_puesta (bool), comentario opcional.

Uso: python api/seed_readings.py
"""
import os
from datetime import datetime, timedelta
import random
from dotenv import load_dotenv
import psycopg2
import psycopg2.extras

load_dotenv()
DB_URL = os.getenv('DB_URL')
if not DB_URL:
    raise RuntimeError('No se encontró la variable de entorno DB_URL')

random.seed(12345)

# Config
days_back = 7
reads_per_day = 4  # multiplicador -> total = reads_per_day * days_back
reads_per_pulsera = reads_per_day * days_back

# Probabilidades para generar valores fuera de rango
prob_critical = 0.08  # 8% lecturas críticas
prob_not_worn = 0.05  # 5% lecturas con pulsera no puesta

comments = [
    None,
    'Control rutinario',
    'Paciente en reposo',
    'Evento anómalo detectado',
    'Verificado por enfermería',
    'Lectura manual',
]

conn = None
try:
    conn = psycopg2.connect(DB_URL)
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    # Obtener pulseras que tienen id_pulsera y asociadas (o no) -> iterar todas las pulseras
    cur.execute('SELECT id_pulsera, id_paciente FROM pulseras')
    pulseras = cur.fetchall()
    if not pulseras:
        print('No se encontraron pulseras en la base de datos. Asegúrate de tener pulseras asignadas.')
    total_inserted = 0
    total_skipped = 0

    now = datetime.now()
    start_time = now - timedelta(days=days_back)

    for row in pulseras:
        id_pulsera = row['id_pulsera']
        # Si ya existen lecturas en el intervalo, saltar para evitar duplicados
        cur.execute('SELECT 1 FROM lecturas WHERE id_pulsera = %s AND momento_lectura >= %s LIMIT 1', (id_pulsera, start_time))
        if cur.fetchone():
            total_skipped += 1
            continue

        # Generar lecturas distribuidas uniformemente en el periodo
        for i in range(reads_per_pulsera):
            # distribuir tiempo
            frac = i / max(1, reads_per_pulsera - 1)
            ts = start_time + (now - start_time) * frac

            # generar si la pulsera está puesta
            if random.random() < prob_not_worn:
                esta_puesta = False
                temperatura_c = None
                ritmo = None
            else:
                esta_puesta = True
                # Decidir si lectura crítica
                if random.random() < prob_critical:
                    # generar valores críticos (hyper/hypo)
                    if random.random() < 0.5:
                        temperatura_c = round(random.uniform(39.6, 41.0), 1)  # fiebre alta
                    else:
                        temperatura_c = round(random.uniform(33.5, 34.9), 1)  # hipotermia

                    # ritmo crítico
                    if random.random() < 0.5:
                        ritmo = random.randint(130, 180)  # taquicardia extrema
                    else:
                        ritmo = random.randint(20, 39)  # bradicardia extrema
                else:
                    # lectura normal o ligera variación
                    temperatura_c = round(random.uniform(36.0, 37.8), 1)
                    ritmo = random.randint(55, 100)

            comentario = random.choice(comments)

            try:
                # La tabla `lecturas` en la base de datos actual no contiene columna `comentario`.
                # Insertamos solo las columnas existentes: id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, momento_lectura
                cur.execute(
                    'INSERT INTO lecturas (id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, momento_lectura) VALUES (%s, %s, %s, %s, %s)',
                    (id_pulsera, ritmo, temperatura_c, esta_puesta, ts)
                )
                total_inserted += 1
            except Exception as e:
                conn.rollback()
                print(f'Error insert lectura para pulsera {id_pulsera} en {ts}: {e}')
            # commit after loop per pulsera (handled below)

        # commit after each pulsera to keep transactions reasonable
        conn.commit()

    print('--- Seed lecturas completed ---')
    print(f'Pulseras procesadas: {len(pulseras)}')
    print(f'Inserted lecturas: {total_inserted}')
    print(f'Skipped pulseras (lecturas recientes ya existentes): {total_skipped}')

except Exception as e:
    print('ERROR during seeding lecturas:', e)

finally:
    if conn:
        conn.close()
