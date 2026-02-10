import type { NextConfig } from "next";

const nextConfig: NextConfig = {
  images: {
    domains: [
      'api.dicebear.com', 
      'lh3.googleusercontent.com',
      'localhost',
      'backend',
      'lms-backend',
    ],
    remotePatterns: [
      {
        protocol: 'http',
        hostname: 'localhost',
        port: '8081',
        pathname: '/api/v1/files/serve/**',
      },
      {
        protocol: 'http',
        hostname: 'backend',
        port: '8080',
        pathname: '/uploads/**',
      },
      {
        protocol: 'http',
        hostname: 'lms-backend',
        port: '8081',
        pathname: '/api/v1/files/serve/**',
      },
      {
        protocol: 'https',
        hostname: '**',
      },
    ],
    formats: ['image/avif', 'image/webp'],
    minimumCacheTTL: 60,
  },

  output: 'standalone',
  productionBrowserSourceMaps: false,
  optimizeFonts: true,
  reactStrictMode: true,
  swcMinify: true,
  compress: true,
  poweredByHeader: false,
  
  experimental: {
    optimizePackageImports: [
      '@radix-ui/react-avatar',
      '@radix-ui/react-dialog',
      '@radix-ui/react-dropdown-menu',
      '@radix-ui/react-label',
      '@radix-ui/react-select',
      '@radix-ui/react-slot',
      '@radix-ui/react-tooltip',
      'lucide-react',
      'react-icons',
    ],
  },

  webpack: (config, { isServer }) => {
    // Optimize for production
    if (!isServer) {
      config.optimization.splitChunks = {
        chunks: 'all',
        cacheGroups: {
          default: false,
          vendors: false,
          vendor: {
            name: 'vendor',
            chunks: 'all',
            test: /node_modules/,
            priority: 20,
          },
          common: {
            name: 'common',
            minChunks: 2,
            chunks: 'all',
            priority: 10,
            reuseExistingChunk: true,
            enforce: true,
          },
        },
      };
    }

    return config;
  },

  async rewrites() {
    const backendUrl = process.env.BACKEND_URL || 'http://backend:8080';
    const lmsUrl = process.env.LMS_API_URL || 'http://lms-backend:8081';

    return [
      {
        source: '/apiv1/:path*',
        destination: `${backendUrl}/:path*`, 
      },
      {
        source: '/uploads/:path*',
        destination: `${backendUrl}/uploads/:path*`, 
      },
      {
        source: '/lmsapiv1/:path*',
        destination: `${lmsUrl}/api/v1/:path*`, 
      },
      {
        source: '/lmsapidocs/:path*',
        destination: `${lmsUrl}/:path*`, 
      },
      {
        source: '/files/:path*',
        destination: `${lmsUrl}/api/v1/files/serve/:path*`,
      },
    ];
  },

  async headers() {
    return [
      {
        source: '/files/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
      {
        source: '/uploads/:path*',
        headers: [
          {
            key: 'Cache-Control',
            value: 'public, max-age=31536000, immutable',
          },
        ],
      },
    ];
  },
};

export default nextConfig;