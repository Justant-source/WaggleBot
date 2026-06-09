/** @type {import('next').NextConfig} */
const nextConfig = {
  output: 'standalone',
  async rewrites() {
    return [
      {
        source: '/api/:path*',
        destination: `${process.env.BACKEND_URL ?? 'http://backend:8080'}/api/:path*`,
      },
      {
        source: '/media/:path*',
        destination: `${process.env.BACKEND_URL ?? 'http://backend:8080'}/api/media/:path*`,
      },
    ]
  },
}
export default nextConfig
