import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';
import { calcularEdad } from '@/lib/utils';
import { getSession } from '@/lib/session';

export async function GET() {
  try {
    const session = await getSession();
    if (!session.isLoggedIn) {
      return NextResponse.json({ error: 'No autorizado' }, { status: 401 });
    }

    const sql = `
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
      JOIN pulseras pu ON pu.id_paciente = p.id_paciente
      LEFT JOIN LATERAL (
        SELECT *
        FROM lecturas l
        WHERE l.id_pulsera = pu.id_pulsera
        ORDER BY l.momento_lectura DESC
        LIMIT 1
      ) l ON TRUE
      ORDER BY p.id_paciente;
    `;

    const rows = await query(sql);

    const pacientes = rows.map((r: any) => ({
      id_paciente: r.id_paciente,
      nombre: `${r.nombre} ${r.apellido_paterno} ${r.apellido_materno}`,
      edad: calcularEdad(r.fecha_nacimiento),
      id_pulsera: r.id_pulsera,
      ritmo_cardiaco: r.ritmo_cardiaco,
      temperatura_c: r.temperatura_c,
      esta_puesta: r.esta_puesta,
      momento_lectura: r.momento_lectura,
    }));

    return NextResponse.json({ pacientes });
  } catch (error) {
    console.error('Error al obtener pacientes:', error);
    return NextResponse.json(
      { error: 'Error al consultar datos' },
      { status: 500 }
    );
  }
}
