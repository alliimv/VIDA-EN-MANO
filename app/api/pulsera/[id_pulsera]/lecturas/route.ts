import { NextRequest, NextResponse } from 'next/server';
import { query } from '@/lib/db';

export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ id_pulsera: string }> }
) {
  try {
    const { id_pulsera } = await params;
    const { searchParams } = new URL(request.url);
    const limit = Math.min(parseInt(searchParams.get('limit') || '10'), 100);

    const rows = await query(
      `SELECT
        id_lectura,
        momento_lectura,
        ritmo_cardiaco,
        temperatura_c,
        esta_puesta,
        comentario
      FROM lecturas
      WHERE id_pulsera = $1
      ORDER BY momento_lectura DESC
      LIMIT $2`,
      [id_pulsera, limit]
    );

    const lecturas = rows.map((r: any) => ({
      id_lectura: r.id_lectura,
      momento_lectura: r.momento_lectura,
      ritmo_cardiaco: r.ritmo_cardiaco,
      temperatura_c: r.temperatura_c ? parseFloat(r.temperatura_c) : null,
      esta_puesta: r.esta_puesta,
      comentario: r.comentario,
    }));

    return NextResponse.json({
      id_pulsera: parseInt(id_pulsera),
      count: lecturas.length,
      lecturas,
    });
  } catch (error) {
    console.error('Error al obtener lecturas:', error);
    return NextResponse.json(
      { error: 'Error al consultar lecturas' },
      { status: 500 }
    );
  }
}
