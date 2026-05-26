import os
import re
import math
import shutil
import logging
import asyncio
from typing import Optional, List
from pydantic import BaseModel, Field, AliasChoices
from PIL import Image, ImageDraw, ImageFont

from app.core.database import get_ai_conn
from app.core.llm import chat_complete_structured, reset_async_clients
from app.core.llm_gateway import TASK_VIDEO_SCRIPT_GEN
from app.schemas.video_schemas import VideoPlan, VideoScript, SlideContent
from app.services.video_renderer import video_renderer
from app.services.youtube_upload_service import youtube_upload_service
from app.worker.kafka_producer import publish_ai_job_status

logger = logging.getLogger(__name__)

# ── Pydantic models for Hierarchical Director Agent ───────────────────────

class SlidePlan(BaseModel):
    slide_number: int = Field(description="Slide sequence number starting from 1")
    title_intent: str = Field(description="The intended topic/title of this slide")
    objective: str = Field(description="What concepts this slide should cover")
    relevant_node_ids: List[int] = Field(
        validation_alias=AliasChoices("relevant_node_ids", "nodeIds", "node_ids", "nodeIDs"),
        description="List of node IDs from the course outline that should be discussed on this slide"
    )

class VideoDirectorPlan(BaseModel):
    hook: str = Field(description="Opening hook to grab attention")
    estimated_slides: int = Field(description="Total number of slides (between 3 and 10)")
    target_audience: str = Field(description="Who this video is for")
    flow_logic: str = Field(description="Logical transition structure")
    slides: List[SlidePlan] = Field(description="List of slide plans")
    outro_narration: str = Field(description="Closing outro narration draft")


def select_and_compress_nodes(rows: list, character_budget: int) -> str:
    """
    Intelligent context building algorithm for educational overview videos.
    Preserves structural integrity, handles sentence boundaries, and scales description
    details adaptively based on the character budget.
    """
    nodes = []
    for r in rows:
        nodes.append({
            "id": r["id"],
            "parent_id": r["parent_id"],
            "title": r["name_vi"] or r["name_en"] or r["name"],
            "description": (r["description"] or "").strip(),
            "level": r["level"] or 0
        })

    def get_sentences(text: str, max_sentences: int) -> str:
        if not text:
            return ""
        # Match sentences ending with ., ?, or ! followed by space or newline
        sentences = re.split(r'(?<=[.!?])\s+', text)
        sentences = [s.strip() for s in sentences if s.strip()]
        if not sentences:
            return text
        selected = sentences[:max_sentences]
        return " ".join(selected)

    def format_context(node_list: list, desc_strategy: str, max_sentences: int = 2) -> str:
        lines = []
        for n in node_list:
            desc = n["description"]
            if desc_strategy == "full":
                pass
            elif desc_strategy == "sentences":
                desc = get_sentences(desc, max_sentences)
            elif desc_strategy == "parent_only_sentence":
                # Omit description for sub-nodes (level > 0)
                if n["level"] > 0 or n["parent_id"] is not None:
                    desc = ""
                else:
                    desc = get_sentences(desc, 1)
            else: # "none"
                desc = ""
            
            if desc:
                lines.append(f"- ID: {n['id']}\n  Topic: {n['title']}\n  Description: {desc}")
            else:
                lines.append(f"- ID: {n['id']}\n  Topic: {n['title']}")
        return "\n".join(lines)

    # Strategy 1: Try full descriptions
    context = format_context(nodes, "full")
    if len(context) <= character_budget:
        return context

    # Strategy 2: Try first 2 sentences for all nodes
    context = format_context(nodes, "sentences", max_sentences=2)
    if len(context) <= character_budget:
        return context

    # Strategy 3: Try first 1 sentence for all nodes
    context = format_context(nodes, "sentences", max_sentences=1)
    if len(context) <= character_budget:
        return context

    # Strategy 4: Try 1 sentence only for parent (level 0) nodes, names only for sub-nodes
    context = format_context(nodes, "parent_only_sentence")
    if len(context) <= character_budget:
        return context

    # Strategy 5: Omit descriptions entirely, only include names
    return format_context(nodes, "none")


def draw_concept_diagram(nodes: list, relations: list, output_path: str, template_type: str = "dark"):
    """
    Renders a beautiful concept graph/diagram of nodes and relations using Pillow.
    Saves to output_path. Size is 750x600.
    """
    width, height = 750, 600
    img = Image.new("RGB", (width, height), color=(15, 32, 59) if template_type.lower() == "dark" else (245, 247, 250))
    draw = ImageDraw.Draw(img)
    
    # 1. Colors
    if template_type.lower() == "dark":
        node_bg = (23, 42, 69)
        node_border = (100, 255, 218)
        text_color = (204, 214, 246)
        line_color = (136, 146, 176)
    else:
        node_bg = (255, 255, 255)
        node_border = (26, 54, 93)
        text_color = (74, 85, 104)
        line_color = (160, 174, 192)

    # Resolve fonts
    font_size = 14
    paths = []
    if os.name == "nt":  # Windows
        paths = [
            "C:\\Windows\\Fonts\\arial.ttf",
            "C:\\Windows\\Fonts\\segoeui.ttf",
        ]
    else:  # Linux/Docker
        paths = [
            "/usr/share/fonts/truetype/dejavu/DejaVuSans.ttf",
            "/usr/share/fonts/truetype/freefont/FreeSans.ttf",
        ]

    font = None
    for p in paths:
        if os.path.exists(p):
            try:
                font = ImageFont.truetype(p, font_size)
                break
            except Exception:
                continue
    if not font:
        font = ImageFont.load_default()

    # 2. Layout Positioning
    n = len(nodes)
    coords = {}
    
    if n == 0:
        draw.text((width//2, height//2), "Concept Overview", fill=text_color, anchor="mm", font=font)
        img.save(output_path)
        return
        
    elif n == 1:
        coords[nodes[0]["id"]] = (width // 2, height // 2)
    elif n == 2:
        coords[nodes[0]["id"]] = (width // 3, height // 2)
        coords[nodes[1]["id"]] = (2 * width // 3, height // 2)
    else:
        # Circle layout
        center_x, center_y = width // 2, height // 2
        radius = min(width, height) // 3.2
        for i, node in enumerate(nodes):
            angle = i * (2 * math.pi / n)
            x = center_x + int(radius * math.cos(angle))
            y = center_y + int(radius * math.sin(angle))
            coords[node["id"]] = (x, y)

    # 3. Draw relations/lines first
    for rel in relations:
        src = rel["source_node_id"]
        tgt = rel["target_node_id"]
        if src in coords and tgt in coords:
            x1, y1 = coords[src]
            x2, y2 = coords[tgt]
            draw.line([x1, y1, x2, y2], fill=line_color, width=2)
            # Draw label in middle
            mx, my = (x1 + x2) // 2, (y1 + y2) // 2
            rel_type = rel.get("relation_type", "related")
            draw.text((mx, my - 10), rel_type, fill=line_color, font=font, anchor="mm")

    # 4. Draw node boxes on top
    box_w, box_h = 160, 60
    for node in nodes:
        x, y = coords[node["id"]]
        x1, y1 = x - box_w // 2, y - box_h // 2
        x2, y2 = x + box_w // 2, y + box_h // 2
        draw.rounded_rectangle([x1, y1, x2, y2], radius=8, fill=node_bg, outline=node_border, width=2)
        
        # Simple text wrap inside box
        title = node["title"]
        words = title.split(" ")
        line1 = " ".join(words[:2])
        line2 = " ".join(words[2:])
        
        if line2:
            draw.text((x, y - 10), line1, fill=text_color, font=font, anchor="mm")
            draw.text((x, y + 10), line2, fill=text_color, font=font, anchor="mm")
        else:
            draw.text((x, y), line1, fill=text_color, font=font, anchor="mm")

    img.save(output_path)


async def schedule_local_cleanup(path: str, delay_seconds: int = 600):
    """
    Schedules cleanup of the temporary folder after a given delay.
    """
    logger.info(f"Scheduled local cleanup for path {path} in {delay_seconds} seconds")
    await asyncio.sleep(delay_seconds)
    if os.path.exists(path):
        try:
            shutil.rmtree(path)
            logger.info(f"Scheduled cleanup: successfully removed {path}")
        except Exception as e:
            logger.error(f"Scheduled cleanup failed for path {path}: {e}")


async def generate_video(
    job_id: str,
    target_type: str,
    target_id: int,
    custom_prompt: Optional[str],
    language: str,
    template_type: str,
    created_by: int,
    content_ids: Optional[List[int]] = None
) -> dict:
    """
    Overview Video Generation Pipeline Orchestrator.
    Uses Hierarchical Multi-Agent / Parallel generation to prevent context overflow,
    and supports dynamic image embedding (Path A: Extracted PDF Diagrams, Path B: dynamic graph drawings).
    """
    # 0. Reset async clients for safety in worker thread
    reset_async_clients()

    job_dir = f"/tmp/video_jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"Starting video generation job {job_id} in {job_dir}")

    success = False
    try:
        # ── Phase 1: Context Aggregation (0% → 15%) ──
        logger.info(f"[{job_id}] Phase 1: Context Aggregation...")
        await publish_ai_job_status(job_id, "processing", progress=5)
        
        # Director Budget: Always keep high-level outline compact for the planner
        director_budget = 15000 

        async with get_ai_conn() as conn:
            if target_type == "course":
                rows = await conn.fetch(
                    "SELECT id, parent_id, name, name_vi, name_en, description, level FROM knowledge_nodes WHERE course_id = $1 ORDER BY order_index, id",
                    target_id
                )
            elif target_type == "section" and content_ids:
                rows = await conn.fetch(
                    "SELECT id, parent_id, name, name_vi, name_en, description, level FROM knowledge_nodes WHERE source_content_id = ANY($1::bigint[]) ORDER BY order_index, id",
                    content_ids
                )
            else:
                rows = []

        context = select_and_compress_nodes(rows, director_budget)
        if not context:
            context = "General overview of the course. No specific topic outline was found in the database."

        nodes = []
        for r in rows:
            nodes.append({
                "id": r["id"],
                "title": r["name_vi"] or r["name_en"] or r["name"],
                "description": (r["description"] or "").strip()
            })

        await publish_ai_job_status(job_id, "processing", progress=15)

        # ── Phase 2: Master Director Planner (15% → 30%) ──
        logger.info(f"[{job_id}] Phase 2: Video Planning...")
        await publish_ai_job_status(job_id, "processing", progress=20)

        lang_name = "Vietnamese" if language == "vi" else "English"
        
        director_system = (
            "You are an educational curriculum architect and video director. "
            "Your job is to structure an educational overview video based on the course outline provided. "
            "Outline the video hook, target audience, flow logic, and a slide-by-slide plan (between 3 and 10 slides). "
            "For each slide, specify its objective and list the node IDs (e.g. 101, 102) from the course outline that should be covered on that slide. "
            f"Write all textual outlines in {lang_name}."
        )

        director_user = (
            f"Here is the course outline/topics:\n{context}\n\n"
            f"User Prompt constraints: {custom_prompt or 'No custom instructions'}\n\n"
            f"Generate a slide-by-slide VideoDirectorPlan matching the required JSON schema."
        )

        director_plan: VideoDirectorPlan = await chat_complete_structured(
            messages=[
                {"role": "system", "content": director_system},
                {"role": "user", "content": director_user}
            ],
            response_model=VideoDirectorPlan,
            temperature=0.3,
            task=TASK_VIDEO_SCRIPT_GEN
        )
        logger.info(f"[{job_id}] Video Director Plan generated: {director_plan.estimated_slides} slides.")
        await publish_ai_job_status(job_id, "processing", progress=30)

        # ── Phase 3: Parallel Slide Scriptwriters & Visual Sourcing (30% → 60%) ──
        logger.info(f"[{job_id}] Phase 3: Parallel Slide Writing & Visual Sourcing...")
        await publish_ai_job_status(job_id, "processing", progress=35)

        async def generate_slide_content(slide_plan: SlidePlan, slide_idx: int) -> tuple[SlideContent, Optional[str]]:
            # 1. Gather context for this specific slide's nodes
            slide_node_ids = slide_plan.relevant_node_ids
            slide_nodes = [n for n in nodes if n["id"] in slide_node_ids]
            
            slide_context_lines = []
            for n in slide_nodes:
                slide_context_lines.append(f"- Topic: {n['title']}\n  Description: {n['description']}")
            slide_context = "\n".join(slide_context_lines)
            if not slide_context:
                slide_context = f"Topic: {slide_plan.title_intent}\nObjective: {slide_plan.objective}"

            # 2. Image Sourcing
            local_img_path = None
            visual_type = "text_only"
            image_url = None
            
            # Path A: Check document chunks for image tags
            if slide_node_ids:
                async with get_ai_conn() as conn:
                    rows_chunks = await conn.fetch(
                        r"SELECT chunk_text FROM document_chunks WHERE node_id = ANY($1) AND status = 'ready' AND chunk_text LIKE '%!\[%\](/files/%'",
                        slide_node_ids
                    )
                    
                    found_url = None
                    for r in rows_chunks:
                        match = re.search(r'!\[.*?\]\((/files/.*?)\)', r["chunk_text"])
                        if match:
                            found_url = match.group(1)
                            break
                            
                    if found_url:
                        logger.info(f"[{job_id}] Path A: Found document image {found_url} for node IDs {slide_node_ids}")
                        from app.services.minio_storage import download_bytes
                        object_key = found_url.replace("/files/", "")
                        img_bytes = await download_bytes(object_key)
                        if img_bytes:
                            local_img_path = os.path.join(job_dir, f"slide_{slide_idx}_raw.png")
                            with open(local_img_path, "wb") as f:
                                f.write(img_bytes)
                            image_url = found_url
                            visual_type = "document_image"

            # Path B: Fallback to dynamic concept graph if Path A not found
            if not local_img_path and slide_node_ids:
                logger.info(f"[{job_id}] Path B: Sourcing dynamic knowledge graph for node IDs {slide_node_ids}")
                slide_nodes_data = []
                async with get_ai_conn() as conn:
                    db_nodes = await conn.fetch(
                        "SELECT id, name_vi, name_en, name FROM knowledge_nodes WHERE id = ANY($1)",
                        slide_node_ids
                    )
                    for dn in db_nodes:
                        slide_nodes_data.append({
                            "id": dn["id"],
                            "title": dn["name_vi"] or dn["name_en"] or dn["name"]
                        })
                        
                    db_rels = await conn.fetch(
                        "SELECT source_node_id, target_node_id, relation_type FROM knowledge_node_relations "
                        "WHERE course_id = $1 AND (source_node_id = ANY($2) AND target_node_id = ANY($2))",
                        target_id, slide_node_ids
                    )
                    slide_rels_data = [dict(r) for r in db_rels]
                    
                if slide_nodes_data:
                    local_img_path = os.path.join(job_dir, f"slide_{slide_idx}_raw.png")
                    try:
                        draw_concept_diagram(slide_nodes_data, slide_rels_data, local_img_path, template_type)
                        visual_type = "knowledge_graph"
                        image_url = f"local://slide_{slide_idx}_raw.png"
                    except Exception as e:
                        logger.error(f"[{job_id}] Path B generation failed: {e}")
                        local_img_path = None

            # 3. Call LLM Slide Writer
            writer_system = (
                "You are an expert video scriptwriter and educational content creator. "
                "Your job is to write a highly engaging script for a SINGLE slide in a slide-based overview video. "
                "Provide a concise title, body text (brief bullet points, maximum 3 lines/sentences), "
                "and the exact narration text to be read by the TTS system. "
                f"Write the output in {lang_name}."
            )
            
            writer_user = (
                f"Slide Number: {slide_idx}\n"
                f"Slide Title Intent: {slide_plan.title_intent}\n"
                f"Slide Objective: {slide_plan.objective}\n\n"
                f"Context for this slide:\n{slide_context}\n\n"
                "Generate the SlideContent JSON matching the required schema."
            )

            slide_res: SlideContent = await chat_complete_structured(
                messages=[
                    {"role": "system", "content": writer_system},
                    {"role": "user", "content": writer_user}
                ],
                response_model=SlideContent,
                temperature=0.4,
                task=TASK_VIDEO_SCRIPT_GEN
            )
            
            slide_res.image_url = image_url
            slide_res.visual_type = visual_type
            return slide_res, local_img_path

        # Run slide writers concurrently for speed optimization
        slides_with_paths = await asyncio.gather(*[
            generate_slide_content(sp, i+1) for i, sp in enumerate(director_plan.slides)
        ])
        
        draft_slides = [sp[0] for sp in slides_with_paths]
        local_img_paths = [sp[1] for sp in slides_with_paths]

        await publish_ai_job_status(job_id, "processing", progress=50)

        # ── Phase 4: Editor Script Refiner (50% → 60%) ──
        logger.info(f"[{job_id}] Phase 4: Script Editing & Coherence Review...")
        
        editor_system = (
            "You are a professional video editor and script refiner. "
            "Your job is to read all individual slides generated for an educational overview video, "
            "verify that the narration flow is smooth and the transition between slides is cohesive. "
            "You must return a VideoScript object containing all slides. "
            "Do NOT modify the number of slides or remove slides. Keep the exact text of the slides unless "
            "minor adjustments are needed for grammatical flow and narrative coherence. "
            f"All text must remain in {lang_name}."
        )

        drafts_text = []
        for idx, ds in enumerate(draft_slides):
            drafts_text.append(
                f"--- Slide {idx+1} ---\n"
                f"Title: {ds.title}\n"
                f"Body: {ds.body}\n"
                f"Narration: {ds.narration}\n"
            )

        editor_user = (
            f"Video Title Intent: {director_plan.slides[0].title_intent if director_plan.slides else 'Course Overview'}\n"
            f"Hook: {director_plan.hook}\n"
            f"Outro Narration: {director_plan.outro_narration}\n\n"
            f"Generated Draft Slides:\n"
            f"{chr(10).join(drafts_text)}\n\n"
            f"Ensure consistent style and smooth flow. Generate the final VideoScript."
        )

        script: VideoScript = await chat_complete_structured(
            messages=[
                {"role": "system", "content": editor_system},
                {"role": "user", "content": editor_user}
            ],
            response_model=VideoScript,
            temperature=0.3,
            task=TASK_VIDEO_SCRIPT_GEN
        )

        # Zip visual attachments back onto final output
        for i, s in enumerate(script.slides):
            if i < len(draft_slides):
                s.image_url = draft_slides[i].image_url
                s.visual_type = draft_slides[i].visual_type

        logger.info(f"[{job_id}] Final Video Script aggregated successfully: {script.video_title}")
        await publish_ai_job_status(job_id, "processing", progress=60)

        # ── Phase 5: Rendering (60% → 90%) ──
        logger.info(f"[{job_id}] Phase 5: Video Rendering...")
        slide_videos = []
        n_slides = len(script.slides)

        for i, s in enumerate(script.slides):
            logger.info(f"[{job_id}] Rendering slide {i+1}/{n_slides}...")
            
            image_path = os.path.join(job_dir, f"slide_{i}.png")
            audio_path = os.path.join(job_dir, f"slide_{i}.mp3")
            video_path = os.path.join(job_dir, f"slide_{i}.mp4")

            local_raw_path = local_img_paths[i] if i < len(local_img_paths) else None

            # Render Slide Image (Split Layout if image is present)
            video_renderer.render_slide_image(s.title, s.body, template_type, image_path, local_raw_path)
            
            # Generate Audio
            duration = await video_renderer.render_slide_audio(s.narration, language, audio_path)
            
            # Assemble Video Slide
            video_renderer.assemble_slide_video(image_path, audio_path, duration, video_path)
            
            slide_videos.append(video_path)
            
            # Publish incremental progress
            progress = 60 + int(30 * (i + 1) / n_slides)
            await publish_ai_job_status(job_id, "processing", progress=progress)

        # Concatenate slide videos
        final_video_path = os.path.join(job_dir, "final.mp4")
        video_renderer.concatenate_videos(slide_videos, final_video_path)
        
        await publish_ai_job_status(job_id, "processing", progress=90)

        # ── Phase 6: MinIO Upload for Preview (90% → 100%) ──
        logger.info(f"[{job_id}] Phase 6: MinIO Upload for Preview...")
        await publish_ai_job_status(job_id, "processing", progress=95)
        
        with open(final_video_path, "rb") as f:
            video_bytes = f.read()
        
        minio_key = f"video-previews/{job_id}.mp4"
        from app.services.minio_storage import upload_bytes
        preview_url = await upload_bytes(minio_key, video_bytes, content_type="video/mp4")
        
        if not preview_url:
            raise RuntimeError("Failed to upload video preview to MinIO")
            
        desc = (
            f"Overview: {script.video_title}\n\n"
            f"{script.outro_narration}\n\n"
            f"Generated automatically by AI Course Overview Video Pipeline."
        )

        # Schedule local directory cleanup in 10 minutes (600 seconds)
        asyncio.create_task(schedule_local_cleanup(job_dir, delay_seconds=600))
        
        success = True
        
        logger.info(f"[{job_id}] Preview uploaded to MinIO: {preview_url}")
        await publish_ai_job_status(job_id, "processing", progress=100)
        
        return {
            "status": "preview_ready",
            "preview_url": preview_url,
            "video_title": script.video_title,
            "video_description": desc,
            "job_id": job_id
        }

    except Exception as exc:
        logger.error(f"[{job_id}] Exception in video generation pipeline: {exc}", exc_info=True)
        raise exc

    finally:
        # Cleanup temp directory only on failure (success = False)
        if not success and os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
                logger.info(f"Cleaned up temporary job directory {job_dir} due to failure")
            except OSError as e:
                logger.error(f"Failed to delete temp dir {job_dir}: {e}")
