# setup_database.py
import psycopg2
from dotenv import load_dotenv
import os
import bcrypt

load_dotenv()


def init_database():
    conn = psycopg2.connect(os.getenv("DB_URL"), sslmode='require')
    cur = conn.cursor()

    # Ejecutar script SQL
    with open('init_db.sql', 'r') as f:
        sql_script = f.read()

    cur.execute(sql_script)

    # Crear hash para contraseñas de prueba
    password = "123456"
    hashed_pw = bcrypt.hashpw(password.encode('utf-8'), bcrypt.gensalt()).decode('utf-8')

    # Actualizar usuarios con hash real
    cur.execute("""
        UPDATE usuarios 
        SET password_hash = %s 
        WHERE username IN ('admin', 'enfermero1', 'familiar1');
    """, (hashed_pw,))

    conn.commit()
    cur.close()
    conn.close()
    print("✅ Base de datos inicializada correctamente")


if __name__ == "__main__":
    init_database()