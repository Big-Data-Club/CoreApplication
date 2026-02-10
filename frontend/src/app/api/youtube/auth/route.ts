import { NextRequest, NextResponse } from 'next/server';
import youtubeService from '@/services/youtubeService';

export async function GET(request: NextRequest) {
  try {
    const authUrl = youtubeService.getAuthUrl();
    
    return NextResponse.json({
      success: true,
      authUrl,
    });
  } catch (error: any) {
    console.error('YouTube auth error:', error);
    return NextResponse.json(
      { error: 'Failed to generate auth URL' },
      { status: 500 }
    );
  }
}