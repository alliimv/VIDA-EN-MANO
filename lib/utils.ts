export function calcularEdad(fechaNacimiento: Date | null): number | null {
  if (!fechaNacimiento) return null;

  const hoy = new Date();
  const nacimiento = new Date(fechaNacimiento);

  let edad = hoy.getFullYear() - nacimiento.getFullYear();
  const mesActual = hoy.getMonth();
  const mesNacimiento = nacimiento.getMonth();

  if (mesActual < mesNacimiento ||
      (mesActual === mesNacimiento && hoy.getDate() < nacimiento.getDate())) {
    edad--;
  }

  return edad;
}

export function determinarEstadoPaciente(
  temperatura: number | null,
  ritmo: number | null,
  pulseraPuesta: boolean | null
): 'rojo' | 'verde' | 'azul' {
  if (temperatura === null || ritmo === null) {
    return 'azul';
  }

  // CRÍTICO: valores peligrosos
  if ((temperatura < 35 || temperatura > 39.5) || (ritmo < 40 || ritmo > 130)) {
    return 'rojo';
  }

  // ESTABLE: valores normales y pulsera puesta
  if ((temperatura >= 36 && temperatura <= 37.5) &&
      (ritmo >= 60 && ritmo <= 100) &&
      pulseraPuesta) {
    return 'verde';
  }

  // ADVERTENCIA: fuera de rango ideal o pulsera no puesta
  return 'azul';
}

export const ESTADO_TEXTO = {
  rojo: 'Crítico',
  verde: 'Estable',
  azul: 'Advertencia'
} as const;
