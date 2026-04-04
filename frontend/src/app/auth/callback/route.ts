import { cookies } from "next/headers";
import { redirect } from "next/navigation";
import { NextRequest } from "next/server";

/**
 * GET /auth/callback
 *
 * Route Handler — receives access_token & refresh_token from the backend
 * OAuth redirect, sets HTTPOnly cookies on the Next.js origin, then redirects to dashboard.
 *
 * This is the ONLY correct way to set cookies in Next.js App Router:
 * - Server Components: READ only (cannot set cookies)
 * - Route Handlers (this file): READ + WRITE cookies ✅
 * - Server Actions: READ + WRITE cookies ✅
 */
export async function GET(request: NextRequest) {
  const searchParams = request.nextUrl.searchParams;
  const access_token = searchParams.get("access_token");
  const refresh_token = searchParams.get("refresh_token");
  const error = searchParams.get("error");

  if (error) {
    redirect(`/auth/login?error=${encodeURIComponent(error)}`);
  }

  if (!access_token || !refresh_token) {
    console.error("[AuthCallback] Missing tokens in URL params");
    redirect("/auth/login?error=no_tokens");
  }

  // Set HTTPOnly cookies from the Route Handler (same origin as frontend)
  const cookieStore = await cookies();

  cookieStore.set("access_token", access_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: false, // Set to true in production (HTTPS)
    maxAge: 60 * 60, // 1 hour
    path: "/",
  });

  cookieStore.set("refresh_token", refresh_token, {
    httpOnly: true,
    sameSite: "lax",
    secure: false,
    maxAge: 60 * 60 * 24 * 7, // 7 days
    path: "/",
  });

  // Redirect to dashboard after setting cookies
  redirect("/");
}
