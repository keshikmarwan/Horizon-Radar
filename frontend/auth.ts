import NextAuth from 'next-auth';
import Credentials from 'next-auth/providers/credentials';
import { timingSafeEqual } from 'crypto';

function safeEqual(a: string, b: string): boolean {
  const aBuf = Buffer.from(a);
  const bBuf = Buffer.from(b);
  if (aBuf.length !== bBuf.length) return false;
  return timingSafeEqual(aBuf, bBuf);
}

export const { handlers, auth, signIn, signOut } = NextAuth({
  secret: process.env.AUTH_SECRET,
  session: {
    strategy: 'jwt',
    maxAge: 60 * 60 * 8,
  },
  providers: [
    Credentials({
      name: 'Admin Login',
      credentials: {
        username: { label: 'Username', type: 'text' },
        password: { label: 'Password', type: 'password' },
      },
      async authorize(credentials) {
        const expectedUser = process.env.ADMIN_USERNAME ?? 'admin';
        const expectedPass = process.env.ADMIN_PASSWORD ?? 'admin123';

        const username = String(credentials?.username ?? '');
        const password = String(credentials?.password ?? '');

        if (!safeEqual(username, expectedUser)) return null;
        if (!safeEqual(password, expectedPass)) return null;

        return { id: 'admin', email: 'admin@horizonradar.local', name: 'Administrator' };
      },
    }),
  ],
  pages: {
    signIn: '/',
  },
});
