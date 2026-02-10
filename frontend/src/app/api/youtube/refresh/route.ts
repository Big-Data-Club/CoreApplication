import { NextRequest, NextResponse } from 'next/server';
import youtubeTokenManager from '@/services/youtubeTokenManager';

export async function POST(request: NextRequest) {
  try {
    await youtubeTokenManager.refreshTokens();

    return NextResponse.json({
      success: true,
      message: 'YouTube tokens refreshed successfully',
    });
  } catch (error: any) {
    console.error('YouTube refresh error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to refresh YouTube tokens' },
      { status: 500 }
    );
  }
}