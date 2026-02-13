// app/api/youtube/upload/route.ts
import { NextRequest, NextResponse } from 'next/server';
import youtubeTokenManager from '@/services/youtubeTokenManager';
import { google } from 'googleapis';
import { Readable } from 'stream';

export async function POST(request: NextRequest) {
  try {
    // Check if YouTube upload is enabled
    if (process.env.NEXT_PUBLIC_YOUTUBE_UPLOAD_ENABLED !== 'true') {
      return NextResponse.json(
        { error: 'YouTube upload is not enabled' },
        { status: 403 }
      );
    }

    // Get authorization header
    const authHeader = request.headers.get('authorization');
    if (!authHeader) {
      return NextResponse.json(
        { error: 'No authorization header' },
        { status: 401 }
      );
    }

    // Check if YouTube is connected
    const hasValidTokens = await youtubeTokenManager.hasValidTokens();
    if (!hasValidTokens) {
      return NextResponse.json(
        { error: 'YouTube is not connected. Please ask admin to connect YouTube first.' },
        { status: 400 }
      );
    }

    // Parse form data
    const formData = await request.formData();
    const file = formData.get('file') as File;
    const title = formData.get('title') as string;
    const description = formData.get('description') as string;
    const privacyStatus = (formData.get('privacyStatus') as 'public' | 'private' | 'unlisted') || 'unlisted';

    if (!file) {
      return NextResponse.json(
        { error: 'No file provided' },
        { status: 400 }
      );
    }

    // Validate file type
    if (!file.type.startsWith('video/')) {
      return NextResponse.json(
        { error: 'File must be a video' },
        { status: 400 }
      );
    }

    // Validate file size (max 2GB)
    const maxSize = 2 * 1024 * 1024 * 1024; // 2GB
    if (file.size > maxSize) {
      return NextResponse.json(
        { error: 'File too large. Maximum size is 2GB' },
        { status: 400 }
      );
    }

    // Get authenticated client
    const oauth2Client = await youtubeTokenManager.getAuthenticatedClient();

    // Convert file to buffer
    const bytes = await file.arrayBuffer();
    const buffer = Buffer.from(bytes);

    const stream = Readable.from(buffer);

    // Upload to YouTube
    const youtube = google.youtube({ version: 'v3', auth: oauth2Client });
    const response = await youtube.videos.insert({
      part: ['snippet', 'status'],
      requestBody: {
        snippet: {
          title: title || file.name,
          description: description || 'Uploaded from LMS',
          tags: ['LMS', 'Education'],
          categoryId: '27', // Education category
        },
        status: {
          privacyStatus: privacyStatus,
          selfDeclaredMadeForKids: false,
        },
      },
      media: {
        body: stream,
        mimeType: file.type,
      },
    });

    const videoId = response.data.id!;
    const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;
    const embedUrl = `https://www.youtube.com/embed/${videoId}`;
    const thumbnailUrl = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

    // Return YouTube video info
    return NextResponse.json({
      success: true,
      data: {
        file_id: videoId,
        file_name: title || file.name,
        file_url: videoUrl,
        file_path: embedUrl,
        file_size: file.size,
        file_type: 'video',
        video_type: 'youtube',
        video_url: videoUrl,
        embed_url: embedUrl,
        thumbnail_url: thumbnailUrl,
      },
    });
  } catch (error: any) {
    console.error('YouTube upload error:', error);
    return NextResponse.json(
      { 
        error: error.message || 'Failed to upload video to YouTube',
        details: error.response?.data || error.toString()
      },
      { status: 500 }
    );
  }
}

export async function GET() {
  try {
    const hasValidTokens = await youtubeTokenManager.hasValidTokens();
    
    return NextResponse.json({
      status: 'ok',
      message: 'YouTube upload API',
      enabled: process.env.NEXT_PUBLIC_YOUTUBE_UPLOAD_ENABLED === 'true',
      connected: hasValidTokens,
    });
  } catch {
    return NextResponse.json({
      status: 'ok',
      message: 'YouTube upload API',
      enabled: process.env.NEXT_PUBLIC_YOUTUBE_UPLOAD_ENABLED === 'true',
      connected: false,
    });
  }
}