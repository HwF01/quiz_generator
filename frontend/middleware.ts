import { NextRequest, NextResponse } from "next/server";

const PROTECTED = ["/practice", "/upload", "/profile", "/wrong", "/favorites"];

export function middleware(req: NextRequest) {
  const { pathname } = req.nextUrl;
  if (!PROTECTED.some((p) => pathname === p || pathname.startsWith(`${p}/`))) {
    return NextResponse.next();
  }
  if (!req.cookies.get("quiz_auth")?.value) {
    const url = req.nextUrl.clone();
    url.pathname = "/login";
    url.searchParams.set("next", pathname);
    return NextResponse.redirect(url);
  }
  return NextResponse.next();
}

export const config = {
  matcher: [
    "/practice/:path*",
    "/upload",
    "/upload/:path*",
    "/profile",
    "/profile/:path*",
    "/wrong",
    "/wrong/:path*",
    "/favorites",
    "/favorites/:path*",
  ],
};
