/** @type {import('next').NextConfig} */
const nextConfig = {
    reactStrictMode: true,
    output: process.env.NODE_ENV === "production" ? "standalone" : undefined,
    images: {
        remotePatterns: [
            {
                protocol: "http",
                hostname: "localhost",
                port: "8000",
                pathname: "/**",
            },
        ],
    },
};

export default nextConfig;
