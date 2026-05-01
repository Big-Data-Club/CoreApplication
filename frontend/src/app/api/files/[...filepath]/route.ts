import { NextRequest, NextResponse } from "next/server";

/**
 * Proxy handler for /api/files/<filepath>
 * Fetches files from the LMS backend (MinIO via Go service) and streams them back.
 * This is needed because Vercel's next.config rewrites don't reliably proxy
 * to external HTTP backends in production (standalone output).
 */
export async function GET(
  request: NextRequest,
  { params }: { params: Promise<{ filepath: string[] }> }
) {
  const { filepath } = await params;
  const filePath = filepath.join("/");

  const lmsUrl = process.env.LMS_API_URL || "http://lms-backend:8081";
  const targetUrl = `${lmsUrl}/api/v1/files/serve/${filePath}`;

  try {
    const headers: HeadersInit = {};

    // Forward authorization if present
    const authHeader = request.headers.get("authorization");
    if (authHeader) {
      headers["Authorization"] = authHeader;
    }

    // Forward range header for video streaming
    const rangeHeader = request.headers.get("range");
    if (rangeHeader) {
      headers["Range"] = rangeHeader;
    }

    const response = await fetch(targetUrl, {
      headers,
      redirect: "manual",
    });

    if (!response.ok && response.status !== 206) {
      return NextResponse.json(
        { error: "File not found" },
        { status: response.status }
      );
    }

    // Stream the response body through
    const responseHeaders = new Headers();

    const headersToForward = [
      "content-type",
      "content-length",
      "content-disposition",
      "content-range",
      "accept-ranges",
      "etag",
      "last-modified",
    ];

    for (const header of headersToForward) {
      const value = response.headers.get(header);
      if (value) {
        responseHeaders.set(header, value);
      }
    }

    // Files are immutable (timestamped filenames)
    responseHeaders.set(
      "Cache-Control",
      "public, max-age=31536000, immutable"
    );
    responseHeaders.set("Access-Control-Allow-Origin", "*");

    return new NextResponse(response.body, {
      status: response.status,
      headers: responseHeaders,
    });
  } catch (error) {
    console.error(`[files-proxy] Failed to fetch ${targetUrl}:`, error);
    return NextResponse.json(
      { error: "Failed to fetch file from storage" },
      { status: 502 }
    );
  }
}
