# Sistema de Monitoreo de Pacientes - Next.js

Sistema de monitoreo de personas adultas mayores con pulseras inteligentes, migrado de Flask a Next.js.

## Tecnologías Utilizadas

- **Next.js 15** - Framework React para aplicaciones web
- **TypeScript** - Tipado estático para JavaScript
- **PostgreSQL** - Base de datos (la misma que usabas con Flask)
- **Iron Session** - Manejo de sesiones seguras
- **CSS Modules** - Estilos con ámbito local

## Requisitos Previos

- Node.js 18 o superior
- PostgreSQL (tu base de datos existente)
- npm (viene con Node.js)

## Instalación

### 1. Instalar Dependencias

```bash
npm install
```

### 2. Configurar Variables de Entorno

Crea un archivo `.env.local` en la raíz del proyecto:

```bash
cp .env.local.example .env.local
```

Edita `.env.local` y configura tus valores:

```env
DATABASE_URL=postgresql://usuario:password@host:puerto/database
SESSION_SECRET=tu_secret_key_aleatorio_de_32_caracteres
```

#### Generar SESSION_SECRET

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

### 3. Verificar Conexión a PostgreSQL

Tu base de datos PostgreSQL debe tener las mismas tablas que usabas con Flask:
- `usuarios`
- `pacientes`
- `pulseras`
- `lecturas`

## Uso en Desarrollo

```bash
npm run dev
```

Abre [http://localhost:3000](http://localhost:3000) en tu navegador.

## Build para Producción

```bash
npm run build
npm start
```

## Estructura del Proyecto

```
vida_en_mano/
├── app/                        # Aplicación Next.js
│   ├── api/                   # API Routes (backend)
│   │   ├── auth/             # Endpoints de autenticación
│   │   │   ├── login/        # POST /api/auth/login
│   │   │   ├── logout/       # POST /api/auth/logout
│   │   │   └── session/      # GET /api/auth/session
│   │   ├── pacientes/        # Endpoints de pacientes
│   │   │   ├── route.ts      # GET /api/pacientes
│   │   │   └── semaforo/     # GET /api/pacientes/semaforo
│   │   └── pulsera/          # Endpoints de pulseras
│   │       └── [id_pulsera]/ # Rutas dinámicas por ID
│   ├── dashboard/            # Página del dashboard
│   ├── semaforo/             # Página del semáforo
│   ├── layout.tsx            # Layout principal
│   ├── page.tsx              # Página de login (/)
│   └── globals.css           # Estilos globales
├── lib/                       # Utilidades compartidas
│   ├── db.ts                 # Conexión y queries a PostgreSQL
│   ├── session.ts            # Manejo de sesiones
│   └── utils.ts              # Funciones auxiliares
├── public/                    # Archivos estáticos
├── next.config.js            # Configuración de Next.js
├── tsconfig.json             # Configuración de TypeScript
└── package.json              # Dependencias y scripts
```

## Rutas de la Aplicación

### Páginas (Frontend)

- `/` - Página de login
- `/dashboard` - Panel de monitoreo de pacientes
- `/semaforo` - Vista de semáforo de estados

### API Endpoints (Backend)

#### Autenticación
- `POST /api/auth/login` - Iniciar sesión
- `POST /api/auth/logout` - Cerrar sesión
- `GET /api/auth/session` - Verificar sesión actual

#### Pacientes
- `GET /api/pacientes` - Obtener todos los pacientes con última lectura
- `GET /api/pacientes/semaforo` - Obtener pacientes con estado de semáforo

#### Pulseras
- `POST /api/pulsera/[id]/lectura` - Insertar nueva lectura de sensores
- `GET /api/pulsera/[id]/lecturas?limit=10` - Obtener lecturas de una pulsera

## Ejemplo de Uso de la API

### Insertar Lectura desde una Pulsera

```bash
curl -X POST http://localhost:3000/api/pulsera/1/lectura \
  -H "Content-Type: application/json" \
  -d '{
    "ritmo_cardiaco": 75,
    "temperatura_c": 36.5,
    "esta_puesta": true,
    "comentario": "Lectura normal"
  }'
```

### Obtener Lecturas de una Pulsera

```bash
curl http://localhost:3000/api/pulsera/1/lecturas?limit=5
```

## Diferencias con la Versión Flask

### ✅ Ventajas de Next.js

1. **Compatible con Firebase Hosting** (y otras plataformas)
2. **TypeScript** - Menos errores en tiempo de ejecución
3. **React** - Interfaz más interactiva y moderna
4. **API Routes** - Backend y frontend en un solo proyecto
5. **Optimización automática** - Next.js optimiza el código automáticamente
6. **Fast Refresh** - Recarga instantánea en desarrollo

### Características Mantenidas

- ✅ Misma base de datos PostgreSQL
- ✅ Misma estructura de datos
- ✅ Mismas funcionalidades
- ✅ Mismos endpoints de API
- ✅ Mismo diseño visual

## Despliegue

### Vercel (Recomendado)

1. Instala Vercel CLI:
   ```bash
   npm install -g vercel
   ```

2. Despliega:
   ```bash
   vercel
   ```

3. Configura variables de entorno en el dashboard de Vercel

### Railway

1. Instala Railway CLI:
   ```bash
   npm install -g @railway/cli
   ```

2. Despliega:
   ```bash
   railway login
   railway init
   railway up
   ```

### Firebase Hosting

**Nota:** Firebase Hosting solo sirve contenido estático. Para Next.js con API Routes, es mejor usar Vercel o Railway.

Si aún quieres usar Firebase:
```bash
firebase login
firebase init
npm run build
firebase deploy
```

## Solución de Problemas

### Error de Conexión a PostgreSQL

Verifica que `DATABASE_URL` en `.env.local` sea correcto:
```env
DATABASE_URL=postgresql://usuario:password@host:puerto/database
```

### Error de Sesión

Verifica que `SESSION_SECRET` esté configurado en `.env.local`:
```env
SESSION_SECRET=tu_secret_key_de_32_caracteres
```

### Puerto en Uso

Si el puerto 3000 está ocupado:
```bash
npm run dev -- -p 3001
```

## Scripts Disponibles

```bash
npm run dev      # Servidor de desarrollo
npm run build    # Construir para producción
npm start        # Servidor de producción
npm run lint     # Linter de código
```

## Base de Datos

La aplicación usa las mismas tablas que tu versión Flask:

```sql
-- Tabla usuarios
CREATE TABLE usuarios (
    username VARCHAR PRIMARY KEY,
    password_hash VARCHAR NOT NULL
);

-- Tabla pacientes
CREATE TABLE pacientes (
    id_paciente SERIAL PRIMARY KEY,
    nombre VARCHAR NOT NULL,
    apellido_paterno VARCHAR NOT NULL,
    apellido_materno VARCHAR,
    fecha_nacimiento DATE
);

-- Tabla pulseras
CREATE TABLE pulseras (
    id_pulsera SERIAL PRIMARY KEY,
    id_paciente INTEGER REFERENCES pacientes(id_paciente)
);

-- Tabla lecturas
CREATE TABLE lecturas (
    id_lectura SERIAL PRIMARY KEY,
    id_pulsera INTEGER REFERENCES pulseras(id_pulsera),
    ritmo_cardiaco INTEGER,
    temperatura_c NUMERIC(4,2),
    esta_puesta BOOLEAN,
    comentario TEXT,
    momento_lectura TIMESTAMP DEFAULT CURRENT_TIMESTAMP
);
```

## Soporte

Para más información:
- [Documentación de Next.js](https://nextjs.org/docs)
- [Documentación de React](https://react.dev)
- [Guía de TypeScript](https://www.typescriptlang.org/docs)

## Licencia

Proyecto académico para monitoreo de personas adultas mayores.
