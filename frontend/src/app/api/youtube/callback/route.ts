import { NextRequest, NextResponse } from 'next/server';

export async function GET(request: NextRequest) {
  try {
    const searchParams = request.nextUrl.searchParams;
    const code = searchParams.get('code');
    const error = searchParams.get('error');

    if (error) {
      return NextResponse.redirect(
        new URL(`/lms/admin/youtube-manage?youtube_auth=error&message=${error}`, process.env.NEXTAUTH_URL)
      );
    }

    if (!code) {
      return NextResponse.redirect(
        new URL('/lms/admin/youtube-manage?youtube_auth=error&message=No code provided', process.env.NEXTAUTH_URL)
      );
    }

    // Redirect to admin page with code
    return NextResponse.redirect(
      new URL(`/lms/admin/youtube-manage?youtube_auth=success&code=${code}`, process.env.NEXTAUTH_URL)
    );
  } catch (error: any) {
    console.error('YouTube callback error:', error);
    return NextResponse.redirect(
      new URL(`/lms/admin/youtube-manage?youtube_auth=error&message=${encodeURIComponent(error.message)}`, process.env.NEXTAUTH_URL)
    );
  }
}