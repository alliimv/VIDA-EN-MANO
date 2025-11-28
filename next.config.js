/** @type {import('next').NextConfig} */
const nextConfig = {
  reactStrictMode: true,
  serverRuntimeConfig: {
    // Variables solo disponibles en el servidor
  },
  publicRuntimeConfig: {
    // Variables disponibles en cliente y servidor
  },
}

module.exports = nextConfig
