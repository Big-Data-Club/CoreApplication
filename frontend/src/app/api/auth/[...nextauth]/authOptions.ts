import { NextAuthOptions } from "next-auth";
import CredentialsProvider from "next-auth/providers/credentials";

declare module "next-auth" {
  interface Session {
    accessToken?: string;
    error?: string;
    user: {
      id?: number | string;
      name?: string | null;
      email?: string | null;
      role?: string;
    };
  }

  interface User {
    role?: string;
    token?: string;
  }

  interface JWT {
    role?: string;
    accessToken?: string;
    refreshToken?: string;
    accessTokenExpires?: number;
    error?: string;
  }
}

async function refreshAccessToken(token: any) {
  try {
    const response = await fetch(`${process.env.BACKEND_URL}/api/auth/refresh`, {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ refreshToken: token.refreshToken }),
    });

    if (!response.ok) {
        throw new Error("Refresh failed");
    }

    const data = await response.json();
    
    // Extract cookies
    const setCookie = response.headers.get("set-cookie");
    const authToken = setCookie?.match(/authToken=([^;]+)/)?.[1];
    const refreshToken = setCookie?.match(/refreshToken=([^;]+)/)?.[1];

    return {
      ...token,
      accessToken: authToken || token.accessToken,
      accessTokenExpires: Date.now() + data.expiresIn,
      refreshToken: refreshToken || token.refreshToken,
    };
  } catch (error) {
    console.error("RefreshAccessTokenError", error);
    return {
      ...token,
      error: "RefreshAccessTokenError",
    };
  }
}

export const authOptions: NextAuthOptions = {
  providers: [
    CredentialsProvider({
      name: "Credentials",
      credentials: {
        email: { label: "Email", type: "email" },
        password: { label: "Password", type: "password" },
      },
      async authorize(credentials) {
        if (!credentials?.email || !credentials?.password) {
          return null;
        }

        try {
          const res = await fetch(`${process.env.BACKEND_URL}/api/auth/login`, {
            method: "POST",
            body: JSON.stringify({
              email: credentials.email,
              password: credentials.password,
            }),
            headers: { "Content-Type": "application/json" },
          });

          if (!res.ok) {
            return null;
          }
          
          const data = await res.json();
          const setCookie = res.headers.get("set-cookie");
          const authToken = setCookie?.match(/authToken=([^;]+)/)?.[1];
          const refreshToken = setCookie?.match(/refreshToken=([^;]+)/)?.[1];

          return {
            id: String(data.userId),
            name: data.name,
            email: data.email,
            role: data.role,
            token: authToken,
            refreshToken: refreshToken,
            expiresIn: data.expiresIn,
          };
        } catch {
          return null;
        }
      },
    }),
    CredentialsProvider({
      id: "google-backend",
      name: "Google Backend",
      credentials: {
        userId: { type: "text" },
        name: { type: "text" },
        email: { type: "text" },
        role: { type: "text" },
        token: { type: "text" },
        refreshToken: { type: "text" },
        expiresIn: { type: "text" },
      },
      async authorize(credentials) {
        if (!credentials?.userId || !credentials?.token) return null;
        return {
          id: credentials.userId,
          name: credentials.name,
          email: credentials.email,
          role: credentials.role,
          token: credentials.token,
          refreshToken: credentials.refreshToken,
          expiresIn: Number(credentials.expiresIn),
        };
      },
    }),
  ],
  session: {
    strategy: "jwt",
    maxAge: 7 * 24 * 60 * 60, // 7 days (NextAuth session can live longer because we refresh the underlying JWT)
  },
  callbacks: {
    async jwt({ token, user, account }) {
      // Initial sign in
      if (user && account) {
        return {
          ...token,
          accessToken: (user as any).token,
          refreshToken: (user as any).refreshToken,
          accessTokenExpires: Date.now() + ((user as any).expiresIn || 3600000),
          role: (user as any).role,
          sub: user.id,
          user: {
             name: user.name,
             email: user.email,
          }
        };
      }

      // Return previous token if the access token has not expired yet
      // We refresh 5 minutes before actual expiry to be safe
      if (Date.now() < (token as any).accessTokenExpires - 300000) {
        return token;
      }

      // Access token has expired, try to update it
      return refreshAccessToken(token);
    },
    async session({ session, token }) {
      if (session.user) {
        session.user.role = token.role as string;
        (session.user as any).id = Number(token.sub);
        (session as any).error = token.error;
        (session as any).accessToken = token.accessToken;
      }
      return session;
    },
    async signIn({ user, account, credentials }) {
      // Automatically set authToken cookie on login
      // next-auth handles this, but ensure backend tokens are also set
      return true;
    },
    async redirect({ url, baseUrl }) {
      // Ensure redirect is to a valid URL
      if (url.startsWith("/")) return `${baseUrl}${url}`;
      if (new URL(url).origin === baseUrl) return url;
      return baseUrl;
    },
  },
  events: {
    async signOut({ token }) {
      // Optional: Call backend to revoke tokens
      try {
        const accessToken = (token as any).accessToken;
        if (accessToken) {
          await fetch(`${process.env.BACKEND_URL}/api/auth/logout`, {
            method: "POST",
            headers: {
              "Content-Type": "application/json",
              "Authorization": `Bearer ${accessToken}`,
            },
          });
        }
      } catch (error) {
        console.error("Logout error:", error);
        // Continue logout even if backend fails
      }
    },
  },
  pages: {
    signIn: "/login",
  },
  secret: process.env.NEXTAUTH_SECRET,
};
