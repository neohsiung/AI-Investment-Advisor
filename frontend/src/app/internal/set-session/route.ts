import { NextRequest, NextResponse } from "next/server";

/**
 * POST /api/auth/set-session
 * 
 * Receives tokens from the frontend /auth/callback page and sets them as
 * HTTPOnly cookies on the Next.js origin (localhost:3000).
 * 
 * This is the correct pattern for cross-port OAuth flows where the backend
 * (localhost:8000) can't set cookies readable by the frontend (localhost:3000).
 */
export async function POST(request: NextRequest) {
  try {
    const { access_token, refresh_token } = await request.json();

    if (!access_token || !refresh_token) {
      return NextResponse.json({ error: "Missing tokens" }, { status: 400 });
    }

    const response = NextResponse.json({ status: "ok" });

    // Set HTTPOnly cookies on the SAME origin as the frontend (localhost:3000)
    // This solves the cross-port cookie issue completely.
    response.cookies.set("access_token", access_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: false, // true in production (HTTPS)
      maxAge: 60 * 60, // 1 hour
      path: "/",
    });

    response.cookies.set("refresh_token", refresh_token, {
      httpOnly: true,
      sameSite: "lax",
      secure: false,
      maxAge: 60 * 60 * 24 * 7, // 7 days
      path: "/",
    });

    return response;
  } catch (error) {
    console.error("[set-session] Error:", error);
    return NextResponse.json({ error: "Invalid request" }, { status: 400 });
  }
}
