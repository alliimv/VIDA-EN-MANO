import { NextRequest, NextResponse } from 'next/server';
import { execute } from '@/lib/db';

export async function POST(
  request: NextRequest,
  { params }: { params: Promise<{ id_pulsera: string }> }
) {
  try {
    const { id_pulsera } = await params;
    const body = await request.json();

    const { ritmo_cardiaco, temperatura_c, esta_puesta, comentario } = body;

    if (ritmo_cardiaco === undefined || temperatura_c === undefined) {
      return NextResponse.json(
        { error: "Faltan campos: 'ritmo_cardiaco', 'temperatura_c'" },
        { status: 400 }
      );
    }

    const row = await execute(
      `INSERT INTO lecturas (
        id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario
      )
      VALUES ($1, $2, $3, $4, $5)
      RETURNING id_lectura, momento_lectura`,
      [id_pulsera, ritmo_cardiaco, temperatura_c, esta_puesta, comentario]
    );

    return NextResponse.json(
      {
        message: 'Lectura insertada correctamente',
        id_pulsera: parseInt(id_pulsera),
        id_lectura: row.id_lectura,
        momento_lectura: row.momento_lectura,
      },
      { status: 201 }
    );
  } catch (error) {
    console.error('Error al insertar lectura:', error);
    return NextResponse.json(
      { error: 'Error al insertar lectura' },
      { status: 500 }
    );
  }
}
