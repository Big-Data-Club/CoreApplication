import { google } from 'googleapis';

const youtube = google.youtube('v3');

export interface YouTubeUploadOptions {
  title: string;
  description?: string;
  tags?: string[];
  privacyStatus?: 'public' | 'private' | 'unlisted';
  categoryId?: string;
}

export interface YouTubeUploadResult {
  videoId: string;
  url: string;
  embedUrl: string;
  thumbnailUrl: string;
  title: string;
}

class YouTubeService {
  private oauth2Client: any;

  constructor() {
    this.oauth2Client = new google.auth.OAuth2(
      process.env.YOUTUBE_CLIENT_ID,
      process.env.YOUTUBE_CLIENT_SECRET,
      process.env.YOUTUBE_REDIRECT_URI
    );
  }

  /**
   * Get authorization URL for OAuth2
   */
  getAuthUrl(): string {
    const scopes = [
      'https://www.googleapis.com/auth/youtube.upload',
      'https://www.googleapis.com/auth/youtube',
    ];

    return this.oauth2Client.generateAuthUrl({
      access_type: 'offline',
      scope: scopes,
      prompt: 'consent',
    });
  }

  /**
   * Set credentials from OAuth2 tokens
   */
  async setCredentials(code: string) {
    const { tokens } = await this.oauth2Client.getToken(code);
    this.oauth2Client.setCredentials(tokens);
    return tokens;
  }

  /**
   * Upload video to YouTube
   */
  async uploadVideo(
    fileBuffer: Buffer,
    fileName: string,
    options: YouTubeUploadOptions
  ): Promise<YouTubeUploadResult> {
    try {
      const response = await youtube.videos.insert({
        auth: this.oauth2Client,
        part: ['snippet', 'status'],
        requestBody: {
          snippet: {
            title: options.title,
            description: options.description || '',
            tags: options.tags || [],
            categoryId: options.categoryId || '22', // 22 = People & Blogs
          },
          status: {
            privacyStatus: options.privacyStatus || 'unlisted',
            selfDeclaredMadeForKids: false,
          },
        },
        media: {
          body: fileBuffer,
          mimeType: 'video/*',
        },
      });

      const videoId = response.data.id!;
      const videoUrl = `https://www.youtube.com/watch?v=${videoId}`;
      const embedUrl = `https://www.youtube.com/embed/${videoId}`;
      const thumbnailUrl = `https://img.youtube.com/vi/${videoId}/hqdefault.jpg`;

      return {
        videoId,
        url: videoUrl,
        embedUrl,
        thumbnailUrl,
        title: options.title,
      };
    } catch (error: any) {
      console.error('YouTube upload error:', error);
      throw new Error(`Failed to upload to YouTube: ${error.message}`);
    }
  }

  /**
   * Get video details
   */
  async getVideoDetails(videoId: string) {
    try {
      const response = await youtube.videos.list({
        auth: this.oauth2Client,
        part: ['snippet', 'contentDetails', 'status'],
        id: [videoId],
      });

      return response.data.items?.[0];
    } catch (error: any) {
      console.error('Error getting video details:', error);
      throw new Error(`Failed to get video details: ${error.message}`);
    }
  }
}

export default new YouTubeService();