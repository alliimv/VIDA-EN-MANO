import type { Metadata } from 'next'
import './globals.css'

export const metadata: Metadata = {
  title: 'Monitoreo Adultos Mayores',
  description: 'Sistema de monitoreo de pacientes con pulseras inteligentes',
}

export default function RootLayout({
  children,
}: {
  children: React.ReactNode
}) {
  return (
    <html lang="es">
      <body>{children}</body>
    </html>
  )
}
