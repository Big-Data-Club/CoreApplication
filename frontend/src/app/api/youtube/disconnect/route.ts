import { NextRequest, NextResponse } from 'next/server';
import youtubeTokenManager from '@/services/youtubeTokenManager';

export async function POST(request: NextRequest) {
  try {
    await youtubeTokenManager.deleteTokens();

    return NextResponse.json({
      success: true,
      message: 'YouTube disconnected successfully',
    });
  } catch (error: any) {
    console.error('YouTube disconnect error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to disconnect YouTube' },
      { status: 500 }
    );
  }
}