// lib/youtubeTokenManager.ts
import fs from 'fs';
import path from 'path';
import { google } from 'googleapis';

interface YouTubeTokens {
  access_token: string;
  refresh_token: string;
  scope: string;
  token_type: string;
  expiry_date: number;
}

interface YouTubeConnectionData {
  tokens: YouTubeTokens;
  channel_name?: string;
  channel_id?: string;
  connected_at: string;
}

class YouTubeTokenManager {
  private tokensFilePath: string;
  private oauth2Client: any;

  constructor() {
    // Store tokens in a file (in production, use database)
    this.tokensFilePath = path.join(process.cwd(), 'data', 'youtube-tokens.json');
    
    this.oauth2Client = new google.auth.OAuth2(
      process.env.YOUTUBE_CLIENT_ID,
      process.env.YOUTUBE_CLIENT_SECRET,
      process.env.YOUTUBE_REDIRECT_URI
    );

    // Ensure data directory exists
    this.ensureDataDirectory();
  }

  private ensureDataDirectory() {
    const dir = path.dirname(this.tokensFilePath);
    if (!fs.existsSync(dir)) {
      fs.mkdirSync(dir, { recursive: true });
    }
  }

  /**
   * Save tokens to file
   */
  async saveTokens(tokens: any, channelInfo?: { name: string; id: string }): Promise<void> {
    const data: YouTubeConnectionData = {
      tokens,
      channel_name: channelInfo?.name,
      channel_id: channelInfo?.id,
      connected_at: new Date().toISOString(),
    };

    fs.writeFileSync(this.tokensFilePath, JSON.stringify(data, null, 2));
  }

  /**
   * Load tokens from file
   */
  async loadTokens(): Promise<YouTubeConnectionData | null> {
    try {
      if (!fs.existsSync(this.tokensFilePath)) {
        return null;
      }

      const data = fs.readFileSync(this.tokensFilePath, 'utf-8');
      return JSON.parse(data);
    } catch (error) {
      console.error('Error loading tokens:', error);
      return null;
    }
  }

  /**
   * Delete tokens
   */
  async deleteTokens(): Promise<void> {
    if (fs.existsSync(this.tokensFilePath)) {
      fs.unlinkSync(this.tokensFilePath);
    }
  }

  /**
   * Check if tokens exist and are valid
   */
  async hasValidTokens(): Promise<boolean> {
    const data = await this.loadTokens();
    if (!data || !data.tokens) {
      return false;
    }

    // Check if token is expired
    const now = Date.now();
    if (data.tokens.expiry_date && data.tokens.expiry_date < now) {
      // Try to refresh
      try {
        await this.refreshTokens();
        return true;
      } catch {
        return false;
      }
    }

    return true;
  }

  /**
   * Get authenticated OAuth2 client
   */
  async getAuthenticatedClient() {
    const data = await this.loadTokens();
    if (!data || !data.tokens) {
      throw new Error('No YouTube tokens found. Please connect YouTube first.');
    }

    this.oauth2Client.setCredentials(data.tokens);

    // Auto-refresh if needed
    const now = Date.now();
    if (data.tokens.expiry_date && data.tokens.expiry_date < now) {
      await this.refreshTokens();
    }

    return this.oauth2Client;
  }

  /**
   * Exchange authorization code for tokens
   */
  async exchangeCodeForTokens(code: string): Promise<void> {
    const { tokens } = await this.oauth2Client.getToken(code);
    this.oauth2Client.setCredentials(tokens);

    // Get channel info
    const youtube = google.youtube({ version: 'v3', auth: this.oauth2Client });
    const response = await youtube.channels.list({
      part: ['snippet'],
      mine: true,
    });

    const channel = response.data.items?.[0];
    const channelInfo = channel ? {
      name: channel.snippet?.title || 'Unknown',
      id: channel.id || 'unknown',
    } : undefined;

    await this.saveTokens(tokens, channelInfo);
  }

  /**
   * Refresh access token
   */
  async refreshTokens(): Promise<void> {
    const data = await this.loadTokens();
    if (!data || !data.tokens) {
      throw new Error('No tokens to refresh');
    }

    this.oauth2Client.setCredentials(data.tokens);
    const { credentials } = await this.oauth2Client.refreshAccessToken();
    
    await this.saveTokens(credentials, {
      name: data.channel_name || 'Unknown',
      id: data.channel_id || 'unknown',
    });
  }

  /**
   * Get connection status
   */
  async getStatus() {
    const data = await this.loadTokens();
    if (!data) {
      return {
        connected: false,
      };
    }

    return {
      connected: true,
      channel_name: data.channel_name,
      channel_id: data.channel_id,
      connected_at: data.connected_at,
      expires_at: data.tokens.expiry_date ? new Date(data.tokens.expiry_date).toISOString() : null,
    };
  }
}

export default new YouTubeTokenManager();