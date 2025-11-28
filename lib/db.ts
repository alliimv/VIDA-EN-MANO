import { Pool } from 'pg';

// Singleton para la conexión a PostgreSQL
let pool: Pool | null = null;

export function getPool(): Pool {
  if (!pool) {
    const connectionString = process.env.DATABASE_URL;

    if (!connectionString) {
      throw new Error("No se encontró la variable de entorno 'DATABASE_URL'");
    }

    pool = new Pool({
      connectionString,
      max: 20,
      idleTimeoutMillis: 30000,
      connectionTimeoutMillis: 2000,
    });
  }

  return pool;
}

export async function query(
  text: string,
  params?: any[]
): Promise<any[]> {
  const pool = getPool();
  try {
    const result = await pool.query(text, params);
    return result.rows;
  } catch (error) {
    console.error('Error en query:', error);
    throw error;
  }
}

export async function queryOne(
  text: string,
  params?: any[]
): Promise<any | null> {
  const rows = await query(text, params);
  return rows.length > 0 ? rows[0] : null;
}

export async function execute(
  text: string,
  params?: any[]
): Promise<any | null> {
  const pool = getPool();
  const client = await pool.connect();

  try {
    const result = await client.query(text, params);
    return result.rows.length > 0 ? result.rows[0] : null;
  } catch (error) {
    console.error('Error en execute:', error);
    throw error;
  } finally {
    client.release();
  }
}
