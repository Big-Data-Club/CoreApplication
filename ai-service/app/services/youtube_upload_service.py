import os
import json
import logging
from googleapiclient.discovery import build
from googleapiclient.http import MediaFileUpload
from google.oauth2.credentials import Credentials

logger = logging.getLogger(__name__)

class YouTubeUploadService:
    def __init__(self):
        self.tokens_path = os.getenv("YOUTUBE_TOKENS_PATH", "/app/youtube-data/youtube-tokens.json")
        self.client_id = os.getenv("YOUTUBE_CLIENT_ID")
        self.client_secret = os.getenv("YOUTUBE_CLIENT_SECRET")

    def _get_credentials(self) -> Credentials:
        if not os.path.exists(self.tokens_path):
            raise FileNotFoundError(f"YouTube tokens file not found at: {self.tokens_path}. Please connect YouTube in LMS Admin Dashboard.")
            
        with open(self.tokens_path, "r", encoding="utf-8") as f:
            data = json.load(f)
            
        tokens = data.get("tokens")
        if not tokens:
            raise ValueError("Invalid YouTube tokens file format: missing 'tokens' object")
            
        scopes = tokens.get("scope")
        if isinstance(scopes, str):
            scopes = scopes.split(" ")

        return Credentials(
            token=tokens.get("access_token"),
            refresh_token=tokens.get("refresh_token"),
            token_uri="https://oauth2.googleapis.com/token",
            client_id=self.client_id,
            client_secret=self.client_secret,
            scopes=scopes
        )

    def upload_video(self, filepath: str, title: str, description: str, privacy: str = "unlisted") -> dict:
        """
        Uploads a video to YouTube using the authenticated user's credentials.
        Returns: {'youtube_video_id': str, 'youtube_url': str}
        """
        if not os.path.exists(filepath):
            raise FileNotFoundError(f"Video file not found at: {filepath}")

        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "snippet": {
                "title": title[:100],  # YouTube title limit is 100 chars
                "description": description[:5000],  # limit 5000 chars
                "tags": ["BDC", "AI", "E-Learning", "Overview"],
                "categoryId": "27"  # Education
            },
            "status": {
                "privacyStatus": privacy.lower(),  # "unlisted", "public", "private"
                "selfDeclaredMadeForKids": False
            }
        }

        media = MediaFileUpload(
            filepath,
            mimetype="video/mp4",
            resumable=True
        )

        logger.info(f"Starting upload of {filepath} to YouTube...")
        request = youtube.videos().insert(
            part="snippet,status",
            body=body,
            media_body=media
        )

        response = None
        while response is None:
            status, response = request.next_chunk()
            if status:
                logger.info(f"Uploaded {int(status.progress() * 100)}%...")

        video_id = response.get("id")
        logger.info(f"Video uploaded successfully. Video ID: {video_id}")

        return {
            "youtube_video_id": video_id,
            "youtube_url": f"https://www.youtube.com/watch?v={video_id}"
        }

    def set_video_public(self, video_id: str):
        """
        Updates the privacy status of a video to public.
        """
        creds = self._get_credentials()
        youtube = build("youtube", "v3", credentials=creds)

        body = {
            "id": video_id,
            "status": {
                "privacyStatus": "public"
            }
        }

        logger.info(f"Updating privacy status of video {video_id} to public...")
        request = youtube.videos().update(
            part="status",
            body=body
        )
        request.execute()
        logger.info(f"Video {video_id} is now public.")

youtube_upload_service = YouTubeUploadService()
