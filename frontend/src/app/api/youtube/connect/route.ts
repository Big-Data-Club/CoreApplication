import { NextRequest, NextResponse } from 'next/server';
import youtubeTokenManager from '@/services/youtubeTokenManager';

export async function POST(request: NextRequest) {
  try {
    const { code } = await request.json();

    if (!code) {
      return NextResponse.json(
        { error: 'Authorization code is required' },
        { status: 400 }
      );
    }

    // Exchange code for tokens and save
    await youtubeTokenManager.exchangeCodeForTokens(code);

    return NextResponse.json({
      success: true,
      message: 'YouTube connected successfully',
    });
  } catch (error: any) {
    console.error('YouTube connect error:', error);
    return NextResponse.json(
      { error: error.message || 'Failed to connect YouTube' },
      { status: 500 }
    );
  }
}