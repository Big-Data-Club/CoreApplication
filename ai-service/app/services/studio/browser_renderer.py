"""Browser PDF/frame rendering with mandatory layout checks and media probes."""
from __future__ import annotations

import asyncio
import json
import math
from contextlib import asynccontextmanager
from pathlib import Path

from app.services.studio.html_renderer import render_html
from app.services.studio.storyboard import Storyboard


async def command(*args: str, timeout: float = 180) -> bytes:
    process = await asyncio.create_subprocess_exec(*map(str, args), stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.PIPE)
    try:
        output, error = await asyncio.wait_for(process.communicate(), timeout)
    except BaseException:
        if process.returncode is None:
            process.kill()
        await process.wait()
        raise
    if process.returncode:
        raise ValueError(f"{args[0]} failed: {error.decode(errors='replace')[-1000:]}")
    return output


async def probe(path: Path) -> dict:
    data = await command("ffprobe", "-v", "error", "-show_streams", "-show_format", "-of", "json", path)
    return json.loads(data)


async def audio_duration(path: Path) -> float:
    # MP3 container durations include encoder delay/padding. Measure decoded
    # PCM, which is what the final concatenation actually plays.
    measured = path
    if path.suffix.lower() != ".wav":
        measured = path.with_suffix(".wav")
        await command("ffmpeg", "-y", "-v", "error", "-i", path, "-ar", "48000", "-ac", "1", "-c:a", "pcm_s16le", measured)
    info = await probe(measured)
    if not any(s.get("codec_type") == "audio" for s in info["streams"]):
        raise ValueError("Narration has no audio stream")
    duration = float(info["format"]["duration"])
    if not math.isfinite(duration) or not 0 < duration <= 300:
        raise ValueError("Scene audio duration must be between 0 and 300 seconds")
    return duration


@asynccontextmanager
async def browser_page(board: Storyboard, html: str):
    from playwright.async_api import async_playwright
    from app.core.config import get_settings
    async with async_playwright() as playwright:
        browser = await playwright.chromium.launch(executable_path=get_settings().studio_chromium_executable)
        try:
            page = await browser.new_page(viewport={"width": board.video.width, "height": board.video.height}, device_scale_factor=1)
            # Generated pages are self-contained; disallow remote resources.
            await page.route("**/*", lambda route: route.abort())
            await page.set_content(html, wait_until="load")
            await page.add_style_tag(content="button{display:none!important}")
            await page.evaluate("document.fonts.ready")
            yield page
        finally:
            await browser.close()


async def screenshot_qa(page, board: Storyboard, directory: Path) -> dict:
    directory.mkdir(exist_ok=True, parents=True)
    samples = []
    views = await page.evaluate("window.studioSceneViews")
    for index, view in enumerate(views):
        fractions = {0.2, 0.4, 0.6, 0.8}
        pages = view["codePages"]
        covered = {min(pages-1, int(fraction*pages)) for fraction in fractions}
        fractions.update((code_page+0.5)/pages for code_page in range(pages) if code_page not in covered)
        for fraction in sorted(fractions):
            await page.evaluate("([i,p])=>window.seekScene(i,p)", [index, fraction])
            errors = await page.evaluate("window.inspectLayout()")
            path = directory / f"{view['id']}_{round(fraction*100)}.png"
            await page.screenshot(path=str(path))
            samples.append({"scene": view["id"], "progress": fraction, "screenshot": f"qa/{path.name}", "errors": errors})
            if errors:
                raise ValueError(f"Layout QA failed in {view['id']}: {'; '.join(errors)[:700]}. Shorten text or split the scene.")
    return {"passed": True, "samples": samples}


async def render_pdf(board: Storyboard, html: str, directory: Path) -> tuple[bytes, dict]:
    async with browser_page(board, html) as page:
        report = await screenshot_qa(page, board, directory / "qa")
        await page.evaluate("""()=>{document.querySelectorAll('.scene').forEach(s=>s.style.display='grid');document.querySelectorAll('[data-reveal]').forEach(e=>e.style.opacity='1');document.querySelectorAll('.caption').forEach(e=>e.textContent='')}""")
        # All labels are checked again in their final, fully revealed state.
        for index in range(await page.evaluate("window.studioSceneViews.length")):
            await page.evaluate("i=>window.seekScene(i,1)", index)
            errors = await page.evaluate("window.inspectLayout()")
            if errors:
                raise ValueError("PDF layout QA failed: " + "; ".join(errors)[:700])
        await page.evaluate("document.querySelectorAll('.scene').forEach(s=>s.style.display='grid')")
        data = await page.pdf(print_background=True, prefer_css_page_size=True)
        return data, report


def validate_video(info: dict, board: Storyboard) -> dict:
    video = next((s for s in info["streams"] if s.get("codec_type") == "video"), {})
    audio = next((s for s in info["streams"] if s.get("codec_type") == "audio"), {})
    expected = sum(scene.duration or 0 for scene in board.scenes)
    actual = float(info["format"]["duration"])
    if (video.get("width"), video.get("height")) != (board.video.width, board.video.height):
        raise ValueError("Final video resolution mismatch")
    if video.get("codec_name") != "h264" or video.get("pix_fmt") != "yuv420p" or audio.get("codec_name") != "aac":
        raise ValueError("Final video must be H.264/yuv420p with AAC")
    numerator, denominator = map(int, video.get("r_frame_rate", "0/1").split("/"))
    if not denominator or abs(numerator/denominator-board.video.fps) > 0.01 or abs(actual-expected) > 0.1:
        raise ValueError("Final video frame rate or audio/video timing mismatch")
    for stream in (video, audio):
        if abs(float(stream.get("duration", actual)) - expected) > 0.1:
            raise ValueError("Final stream duration differs from measured narration")
    return {"passed": True, "duration": actual, "measured_audio_duration": expected,
            "width": video["width"], "height": video["height"], "fps": board.video.fps,
            "video_codec": "h264", "audio_codec": "aac", "pixel_format": "yuv420p"}


async def render_video(board: Storyboard, directory: Path, theme: str) -> dict:
    """Audio defines all boundaries; global frame time prevents cumulative rounding drift."""
    if any(not scene.duration for scene in board.scenes):
        raise ValueError("Measure every scene audio before rendering")
    for scene in board.scenes:
        scene.duration = await audio_duration(directory / "narration" / f"{scene.id}.mp3")
    html = render_html(board, theme, video=True)
    (directory / "video.html").write_text(html, encoding="utf-8")
    (directory / "storyboard.json").write_text(board.model_dump_json(indent=2), encoding="utf-8")
    total = sum(scene.duration for scene in board.scenes)
    if total > 3600:
        raise ValueError("Split videos longer than one hour into separate projects")
    async with browser_page(board, html) as page:
        qa = await screenshot_qa(page, board, directory / "qa")
        process = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-f", "image2pipe", "-framerate", str(board.video.fps),
            "-vcodec", "png", "-i", "pipe:0", "-an", "-c:v", "libx264", "-preset", "fast",
            "-crf", "18", "-pix_fmt", "yuv420p", str(directory / "visual.mp4"),
            stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )
        error_task = asyncio.create_task(process.stderr.read())
        try:
            index = 0; offset = 0.0
            for frame in range(math.ceil(total * board.video.fps)):
                elapsed = frame / board.video.fps
                while index < len(board.scenes)-1 and elapsed >= offset+board.scenes[index].duration:
                    offset += board.scenes[index].duration
                    index += 1
                local = min(1, (elapsed-offset)/board.scenes[index].duration)
                await page.evaluate("([i,p])=>window.seekScene(i,p)", [index, local])
                process.stdin.write(await page.screenshot(type="png"))
                await process.stdin.drain()
            process.stdin.close()
            await asyncio.wait_for(process.wait(), 180)
            error = await error_task
            if process.returncode:
                raise ValueError("Frame encoding failed: " + error.decode(errors="replace")[-700:])
        except BaseException:
            if process.returncode is None:
                process.kill()
            await process.wait()
            error_task.cancel()
            await asyncio.gather(error_task, return_exceptions=True)
            raise
    # Decode/concatenate scene audio once, then encode AAC once. Repeated AAC
    # priming/padding per scene would otherwise accumulate at concatenation.
    inputs = []
    for scene in board.scenes:
        inputs.extend(["-i", str(directory / "narration" / f"{scene.id}.wav")])
    chain = ''.join(f'[{i}:a]' for i in range(len(board.scenes)))
    await command("ffmpeg", "-y", "-v", "error", *inputs, "-filter_complex",
                  f"{chain}concat=n={len(board.scenes)}:v=0:a=1[a]", "-map", "[a]", "-c:a", "pcm_s16le", directory / "narration.wav")
    await command("ffmpeg", "-y", "-v", "error", "-i", directory / "visual.mp4", "-i", directory / "narration.wav",
                  "-map", "0:v:0", "-map", "1:a:0", "-c:v", "copy", "-c:a", "aac", "-b:a", "192k",
                  "-t", f"{total:.6f}", "-movflags", "+faststart", directory / "video.mp4")
    qa["media"] = validate_video(await probe(directory / "video.mp4"), board)
    (directory / "qa.json").write_text(json.dumps(qa, ensure_ascii=False, indent=2), encoding="utf-8")
    return qa
