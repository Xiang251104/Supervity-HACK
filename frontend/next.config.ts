import nodePath from 'node:path'
import type { NextConfig } from 'next'

// Handle basePath - Next.js requires either empty string or path starting with /
// but NOT just "/" alone
const getBasePath = () => {
  const path = process.env.NEXT_PUBLIC_BASE_PATH || ''
  // "/" is not a valid basePath, treat it as empty
  if (path === '/') return ''
  return path
}

const nextConfig: NextConfig = {
  basePath: getBasePath(),

  // Pin the workspace root to this directory. Without it, Next walks up looking
  // for a lockfile and can latch onto an unrelated package-lock.json further up
  // the tree (e.g. one sitting in the user's home directory), which changes file
  // tracing and produces confusing build output.
  turbopack: {
    root: nodePath.join(__dirname),
  },
  outputFileTracingRoot: nodePath.join(__dirname),

  env: {
    NEXT_PUBLIC_API_URL:
      process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8001',
    INTERNAL_API_URL: process.env.INTERNAL_API_URL || 'http://backend:8000',
  },
  serverExternalPackages: [],

  // Tree-shake heavy icon/component libraries
  experimental: {
    optimizePackageImports: [
      '@radix-ui/react-icons',
      'lucide-react',
      'recharts',
      'framer-motion',
    ],
  },

  // Ensure TypeScript errors fail the build
  typescript: {
    ignoreBuildErrors: false,
  },

  // Disable source maps in production for faster builds
  productionBrowserSourceMaps: false,
}

export default nextConfig
