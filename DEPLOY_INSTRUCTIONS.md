# Instrucciones de Despliegue

## Resumen de Migración

Tu aplicación ha sido migrada de **Flask (Python)** a **Next.js (JavaScript/TypeScript)**. Ahora es compatible con plataformas de hosting modernas.

## Opciones de Despliegue

### Opción 1: Vercel (Recomendado - Más Fácil)

Vercel es la plataforma creada por los desarrolladores de Next.js y es la forma más sencilla de desplegar tu aplicación.

**Pasos:**

1. Crea una cuenta en [vercel.com](https://vercel.com)
2. Instala Vercel CLI:
   ```bash
   npm install -g vercel
   ```
3. Crea tu archivo `.env.local` con las variables de entorno:
   ```bash
   DATABASE_URL=tu_connection_string_postgresql
   SESSION_SECRET=tu_secret_key_aleatorio
   ```
4. Despliega:
   ```bash
   vercel
   ```
5. En el dashboard de Vercel, configura las variables de entorno (Settings → Environment Variables)

### Opción 2: Firebase Hosting (Más Complejo)

**IMPORTANTE:** Firebase Hosting solo sirve contenido estático. Para Next.js con API Routes necesitas una de estas opciones:

#### 2a. Firebase + Cloud Functions (Complejo, No Recomendado)
- Requiere convertir las API Routes a Cloud Functions
- Más costoso
- Más complejo de configurar

#### 2b. Firebase Hosting + Vercel Backend
- Despliega el backend en Vercel
- Usa Firebase solo para archivos estáticos
- Híbrido, no ideal

### Opción 3: Railway.app (Sencillo con PostgreSQL Incluido)

Railway es excelente porque incluye PostgreSQL gratis.

**Pasos:**

1. Crea una cuenta en [railway.app](https://railway.app)
2. Instala Railway CLI:
   ```bash
   npm install -g @railway/cli
   ```
3. Inicia sesión:
   ```bash
   railway login
   ```
4. Crea un nuevo proyecto:
   ```bash
   railway init
   ```
5. Agrega PostgreSQL:
   ```bash
   railway add
   ```
   Selecciona "PostgreSQL"

6. Configura las variables de entorno en Railway dashboard
7. Despliega:
   ```bash
   railway up
   ```

## Configuración de Variables de Entorno

**Para cualquier plataforma, necesitas configurar:**

```env
DATABASE_URL=postgresql://usuario:password@host:puerto/database
SESSION_SECRET=un_string_aleatorio_de_al_menos_32_caracteres
```

### Generar SESSION_SECRET

```bash
node -e "console.log(require('crypto').randomBytes(32).toString('hex'))"
```

## Estructura del Proyecto Migrado

```
vida_en_mano/
├── app/                    # Páginas de Next.js
│   ├── api/               # API Routes (reemplazan Flask routes)
│   │   ├── auth/         # Autenticación
│   │   ├── pacientes/    # Endpoints de pacientes
│   │   └── pulsera/      # Endpoints de pulseras
│   ├── dashboard/        # Página del dashboard
│   ├── semaforo/         # Página del semáforo
│   └── page.tsx          # Página de login
├── lib/                   # Utilidades
│   ├── db.ts             # Conexión a PostgreSQL
│   ├── session.ts        # Manejo de sesiones
│   └── utils.ts          # Funciones auxiliares
├── public/               # Archivos estáticos
├── next.config.js        # Configuración de Next.js
├── package.json          # Dependencias Node.js
└── tsconfig.json         # Configuración TypeScript
```

## Comandos Importantes

### Desarrollo Local
```bash
# Instalar dependencias
npm install

# Configurar variables de entorno
cp .env.example .env.local
# Edita .env.local con tus valores

# Iniciar servidor de desarrollo
npm run dev
```

### Build para Producción
```bash
# Construir la aplicación
npm run build

# Iniciar en producción
npm start
```

## Conectar PostgreSQL

Tu base de datos PostgreSQL existente funcionará sin cambios. Solo necesitas:

1. Asegurarte de que la base de datos sea accesible desde internet
2. Configurar `DATABASE_URL` con el connection string correcto

## Diferencias con Flask

1. **Sesiones**: Ahora usan iron-session en lugar de Flask sessions
2. **Templates**: Ahora son componentes React en lugar de Jinja2
3. **Rutas**:
   - `/` → Login
   - `/dashboard` → Dashboard
   - `/semaforo` → Semáforo
   - `/api/auth/login` → Autenticación
   - `/api/pacientes` → Datos de pacientes
   - `/api/pulsera/[id]/lectura` → Enviar lecturas de pulsera

## Recomendación Final

**Para máxima simplicidad: Usa Vercel**

1. Es gratis para proyectos pequeños
2. Despliegue automático desde Git
3. Variables de entorno fáciles de configurar
4. Compatible 100% con Next.js
5. HTTPS automático
6. No requiere configuración adicional

Si necesitas ayuda, revisa:
- [Documentación de Next.js](https://nextjs.org/docs)
- [Documentación de Vercel](https://vercel.com/docs)
