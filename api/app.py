import bcrypt
import psycopg2
from dotenv import load_dotenv
import os

load_dotenv()


def hash_password(password):
    salt = bcrypt.gensalt()
    return bcrypt.hashpw(password.encode('utf-8'), salt)


def migrate():
    conn = psycopg2.connect(os.getenv("DB_URL"))
    cur = conn.cursor()

    # Obtener usuarios con contraseñas
    cur.execute("SELECT username, password_hash FROM usuarios;")
    users = cur.fetchall()

    updated_count = 0
    for username, password in users:
        if password and not password.startswith('$2b$'):  # Si no está hasheada
            print(f"Migrando usuario: {username}")
            hashed = hash_password(password)
            cur.execute("""
                UPDATE usuarios 
                SET password_hash = %s 
                WHERE username = %s;
            """, (hashed.decode('utf-8'), username))
            updated_count += 1

    conn.commit()
    cur.close()
    conn.close()
    print(f"Migración completada! {updated_count} usuarios actualizados.")


if __name__ == "__main__":
    migrate()