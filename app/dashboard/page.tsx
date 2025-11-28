'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import styles from './dashboard.module.css';

interface Paciente {
  id_paciente: number;
  nombre: string;
  edad: number | null;
  id_pulsera: number;
  ritmo_cardiaco: number | null;
  temperatura_c: number | null;
  esta_puesta: boolean | null;
  momento_lectura: string | null;
}

export default function DashboardPage() {
  const router = useRouter();
  const [pacientes, setPacientes] = useState<Paciente[]>([]);
  const [username, setUsername] = useState('');
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    checkSession();
    loadPacientes();
  }, []);

  const checkSession = async () => {
    try {
      const response = await fetch('/api/auth/session');
      const data = await response.json();

      if (!data.isLoggedIn) {
        router.push('/');
      } else {
        setUsername(data.username);
      }
    } catch (error) {
      console.error('Error al verificar sesión:', error);
      router.push('/');
    }
  };

  const loadPacientes = async () => {
    try {
      const response = await fetch('/api/pacientes');
      const data = await response.json();

      if (response.ok) {
        setPacientes(data.pacientes);
      }
    } catch (error) {
      console.error('Error al cargar pacientes:', error);
    } finally {
      setLoading(false);
    }
  };

  const handleLogout = async () => {
    try {
      await fetch('/api/auth/logout', { method: 'POST' });
      router.push('/');
    } catch (error) {
      console.error('Error al cerrar sesión:', error);
    }
  };

  const isAlert = (value: number | null, min: number, max: number) => {
    return value !== null && (value < min || value > max);
  };

  const isOk = (value: number | null, min: number, max: number) => {
    return value !== null && value >= min && value <= max;
  };

  if (loading) {
    return <div className={styles.loading}>Cargando...</div>;
  }

  return (
    <div>
      <header className={styles.header}>
        <div>
          <h1>Panel de monitoreo</h1>
          <div className={styles.subtitle}>Últimas lecturas por paciente</div>
        </div>
        <div className={styles.headerActions}>
          <Link href="/semaforo" className={styles.navButton}>
            Ver Semáforo de Estado
          </Link>
          <div className={styles.user}>
            Sesión: {username} |{' '}
            <button onClick={handleLogout} className={styles.logoutButton}>
              Cerrar sesión
            </button>
          </div>
        </div>
      </header>

      <main className={styles.main}>
        {pacientes.length === 0 ? (
          <p>No hay pacientes registrados o aún no hay lecturas.</p>
        ) : (
          <table className={styles.table}>
            <thead>
              <tr>
                <th>ID Paciente</th>
                <th>Nombre</th>
                <th>Edad</th>
                <th>ID Pulsera</th>
                <th>Temp (°C)</th>
                <th>Ritmo (lpm)</th>
                <th>Pulsera</th>
                <th>Última lectura</th>
              </tr>
            </thead>
            <tbody>
              {pacientes.map((p) => {
                const tempAlert = isAlert(p.temperatura_c, 36, 38);
                const tempOk = isOk(p.temperatura_c, 36, 38);
                const ritmoAlert = isAlert(p.ritmo_cardiaco, 50, 110);
                const ritmoOk = isOk(p.ritmo_cardiaco, 50, 110);

                return (
                  <tr key={p.id_paciente}>
                    <td>{p.id_paciente}</td>
                    <td>{p.nombre}</td>
                    <td>{p.edad ?? '-'}</td>
                    <td>{p.id_pulsera}</td>
                    <td className={tempAlert ? styles.alert : tempOk ? styles.ok : ''}>
                      {p.temperatura_c ?? '-'}
                    </td>
                    <td className={ritmoAlert ? styles.alert : ritmoOk ? styles.ok : ''}>
                      {p.ritmo_cardiaco ?? '-'}
                    </td>
                    <td>
                      {p.esta_puesta === true && (
                        <span className={`${styles.badge} ${styles.badgeOn}`}>Puesta</span>
                      )}
                      {p.esta_puesta === false && (
                        <span className={`${styles.badge} ${styles.badgeOff}`}>No puesta</span>
                      )}
                      {p.esta_puesta === null && '-'}
                    </td>
                    <td>
                      {p.momento_lectura
                        ? new Date(p.momento_lectura).toLocaleString('es-MX')
                        : '-'}
                    </td>
                  </tr>
                );
              })}
            </tbody>
          </table>
        )}
      </main>
    </div>
  );
}
