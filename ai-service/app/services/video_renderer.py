import os
import subprocess
import logging
import asyncio
import edge_tts
from PIL import Image, ImageDraw, ImageFont

logger = logging.getLogger(__name__)

VOICE_MAP = {
    "vi": "vi-VN-HoaiMyNeural",
    "en": "en-US-AriaNeural",
}

class VideoRenderer:
    def __init__(self):
        # Base asset paths
        self.assets_dir = os.getenv("VIDEO_ASSETS_DIR", "/app/assets/board")
        if not os.path.exists(self.assets_dir):
            # Fallback to local workspace paths during local run
            self.assets_dir = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(__file__))), "assets", "board")

    def _get_font(self, font_size: int, bold: bool = False) -> ImageFont.ImageFont:
        paths = []
        if os.name == "nt":  # Windows
            paths = [
                "C:\\Windows\\Fonts\\arial.ttf" if not bold else "C:\\Windows\\Fonts\\arialbd.ttf",
                "C:\\Windows\\Fonts\\segoeui.ttf" if not bold else "C:\\Windows\\Fonts\\segoeuib.ttf",
            ]
        else:  # Linux/Docker
            paths = [
                "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf" if not bold else "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
                "/usr/share/fonts/truetype/freefont/FreeSans.ttf" if not bold else "/usr/share/fonts/truetype/freefont/FreeSansBold.ttf",
            ]

        for p in paths:
            if os.path.exists(p):
                try:
                    return ImageFont.truetype(p, font_size)
                except Exception:
                    continue

        return ImageFont.load_default()

    def _wrap_text(self, text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
        words = text.split(" ")
        lines = []
        current_line = []
        for word in words:
            current_line.append(word)
            line_str = " ".join(current_line)
            left, top, right, bottom = font.getbbox(line_str)
            w = right - left
            if w > max_width:
                if len(current_line) > 1:
                    current_line.pop()
                    lines.append(" ".join(current_line))
                    current_line = [word]
                else:
                    lines.append(line_str)
                    current_line = []
        if current_line:
            lines.append(" ".join(current_line))
        return lines

    async def render_slide_audio(self, text: str, language: str, output_path: str) -> float:
        """
        Generates TTS audio file for a slide narration and returns its duration in seconds.
        """
        voice = VOICE_MAP.get(language.lower(), "vi-VN-HoaiMyNeural")
        logger.info(f"Generating TTS audio with voice {voice} for text: {text[:50]}...")
        
        communicate = edge_tts.Communicate(text, voice)
        await communicate.save(output_path)
        
        # Determine duration
        duration = self._get_audio_duration(output_path)
        logger.info(f"TTS audio generated. Duration: {duration:.2f}s")
        return duration

    def _get_audio_duration(self, filepath: str) -> float:
        cmd = [
            "ffprobe",
            "-v", "error",
            "-show_entries", "format=duration",
            "-of", "default=noprint_wrappers=1:nokey=1",
            filepath
        ]
        try:
            output = subprocess.check_output(cmd, stderr=subprocess.DEVNULL).decode("utf-8").strip()
            return float(output)
        except Exception as e:
            logger.error(f"Failed to query audio duration via ffprobe: {e}. Defaulting to 7.0 seconds.")
            return 7.0

    def render_slide_image(self, title: str, body: str, template_type: str, output_path: str):
        """
        Draws title and body text onto the chosen slide background template.
        """
        # Resolve template file
        filename = "bdc_template_dark.png" if template_type.lower() == "dark" else "bdc_template_light.png"
        template_path = os.path.join(self.assets_dir, filename)
        
        if not os.path.exists(template_path):
            logger.warning(f"Slide template background not found at {template_path}. Creating fallback gradient image.")
            # Create a basic image fallback
            img = Image.new("RGB", (1920, 1080), color=(10, 25, 47) if template_type.lower() == "dark" else (240, 244, 248))
        else:
            img = Image.open(template_path).convert("RGB")

        draw = ImageDraw.Draw(img)
        
        # Layout metrics
        margin_left = 180
        max_text_width = 1560
        title_y = 230
        body_start_y = 380
        
        # Colors
        if template_type.lower() == "dark":
			# Bright cyan/blue/white color palette for dark template
            title_color = (100, 255, 218)  # Cyan
            body_color = (204, 214, 246)   # Light gray-blue
        else:
			# Premium deep dark indigo/slate colors for light template
            title_color = (26, 54, 93)     # Dark blue
            body_color = (74, 85, 104)     # Dark slate

        # Fonts
        title_font = self._get_font(60, bold=True)
        body_font = self._get_font(32, bold=False)

        # Draw Title
        title_lines = self._wrap_text(title, title_font, max_text_width)
        y = title_y
        for line in title_lines:
            draw.text((margin_left, y), line, fill=title_color, font=title_font)
            # Line height
            left, top, right, bottom = title_font.getbbox(line)
            y += (bottom - top) + 15

        # Draw Body
        body_lines = self._wrap_text(body, body_font, max_text_width)
        y = max(y + 20, body_start_y)
        for line in body_lines:
            draw.text((margin_left, y), line, fill=body_color, font=body_font)
            left, top, right, bottom = body_font.getbbox(line)
            y += (bottom - top) + 15

        img.save(output_path)
        logger.info(f"Rendered slide image saved to {output_path}")

    def assemble_slide_video(self, image_path: str, audio_path: str, duration: float, output_path: str):
        """
        FFmpeg command compiling 1 slide image + 1 audio track into 1 sub-clip.
        """
        cmd = [
            "ffmpeg",
            "-loop", "1",
            "-i", image_path,
            "-i", audio_path,
            "-c:v", "libx264",
            "-tune", "stillimage",
            "-r", "25",
            "-c:a", "aac",
            "-b:a", "192k",
            "-ar", "44100",
            "-pix_fmt", "yuv420p",
            "-t", str(duration),
            "-y",
            output_path
        ]
        logger.info(f"Running FFmpeg slide compile: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8")
            raise RuntimeError(f"FFmpeg slide clip compilation failed: {err_msg}")

    def concatenate_videos(self, video_paths: list[str], output_path: str):
        """
        FFmpeg concat demuxer join. Fast and zero re-encoding!
        """
        # Create inputs file
        temp_dir = os.path.dirname(output_path)
        list_file_path = os.path.join(temp_dir, "concat_list.txt")
        
        with open(list_file_path, "w", encoding="utf-8") as f:
            for vp in video_paths:
                # Escape single quotes for ffmpeg format
                escaped_vp = vp.replace("'", "'\\''")
                f.write(f"file '{escaped_vp}'\n")

        cmd = [
            "ffmpeg",
            "-f", "concat",
            "-safe", "0",
            "-i", list_file_path,
            "-c", "copy",
            "-y",
            output_path
        ]
        logger.info(f"Running FFmpeg concat: {' '.join(cmd)}")
        result = subprocess.run(cmd, stdout=subprocess.DEVNULL, stderr=subprocess.PIPE)
        
        # Clean up list file
        try:
            os.remove(list_file_path)
        except OSError:
            pass

        if result.returncode != 0:
            err_msg = result.stderr.decode("utf-8")
            raise RuntimeError(f"FFmpeg concatenation failed: {err_msg}")

        logger.info(f"Concatenated video saved to {output_path}")

video_renderer = VideoRenderer()
