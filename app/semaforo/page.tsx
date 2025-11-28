'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import Link from 'next/link';
import styles from './semaforo.module.css';

interface Paciente {
  id_paciente: number;
  nombre: string;
  id_pulsera: number;
  ritmo_cardiaco: number | null;
  temperatura_c: number | null;
  esta_puesta: boolean | null;
  momento_lectura: string | null;
  estado: 'rojo' | 'verde' | 'azul';
  estado_texto: string;
}

export default function SemaforoPage() {
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
      const response = await fetch('/api/pacientes/semaforo');
      const data = await response.json();

      if (response.ok) {
        setPacientes(data.pacientes);
      }
    } catch (error) {
      console.error('Error al cargar datos del semáforo:', error);
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

  if (loading) {
    return <div className={styles.loading}>Cargando...</div>;
  }

  return (
    <div>
      <header className={styles.header}>
        <div>
          <h1>Semáforo de Estado</h1>
          <div className={styles.subtitle}>Estado actual de todos los pacientes</div>
        </div>
        <div className={styles.headerActions}>
          <Link href="/dashboard" className={styles.navButton}>
            ← Volver al Dashboard
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
        <div className={styles.leyenda}>
          <div className={styles.leyendaItem}>
            <div className={`${styles.leyendaColor} ${styles.verde}`}></div>
            <span>Verde - Estable</span>
          </div>
          <div className={styles.leyendaItem}>
            <div className={`${styles.leyendaColor} ${styles.azul}`}></div>
            <span>Azul - Advertencia</span>
          </div>
          <div className={styles.leyendaItem}>
            <div className={`${styles.leyendaColor} ${styles.rojo}`}></div>
            <span>Rojo - Crítico</span>
          </div>
        </div>

        {pacientes.length === 0 ? (
          <p>No hay pacientes registrados o aún no hay lecturas.</p>
        ) : (
          <div className={styles.semaforoGrid}>
            {pacientes.map((p) => (
              <div key={p.id_paciente} className={`${styles.pacienteCard} ${styles[p.estado]}`}>
                <div className={styles.pacienteInfo}>
                  <div className={styles.pacienteNombre}>{p.nombre}</div>
                  <div className={styles.pacienteDatos}>ID: {p.id_paciente}</div>
                  <div className={styles.pacienteDatos}>Pulsera: {p.id_pulsera}</div>

                  {p.temperatura_c !== null && (
                    <div className={styles.pacienteDatos}>Temp: {p.temperatura_c}°C</div>
                  )}

                  {p.ritmo_cardiaco !== null && (
                    <div className={styles.pacienteDatos}>Ritmo: {p.ritmo_cardiaco} lpm</div>
                  )}

                  <div className={`${styles.semaforo} ${styles[p.estado]}`}>
                    {p.estado_texto}
                  </div>

                  <div className={`${styles.estadoTexto} ${styles[p.estado + 'Text']}`}>
                    {p.estado_texto}
                  </div>

                  {p.momento_lectura && (
                    <div className={styles.pacienteDatos} style={{ marginTop: '0.5rem' }}>
                      Última lectura:<br />
                      {new Date(p.momento_lectura).toLocaleString('es-MX')}
                    </div>
                  )}
                </div>
              </div>
            ))}
          </div>
        )}
      </main>
    </div>
  );
}
