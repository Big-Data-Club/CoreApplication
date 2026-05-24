import os
import re
import shutil
import logging
from typing import Optional, List
from app.core.database import get_ai_conn
from app.core.llm import chat_complete_structured, reset_async_clients
from app.core.llm_gateway import TASK_VIDEO_SCRIPT_GEN
from app.schemas.video_schemas import VideoPlan, VideoScript
from app.services.video_renderer import video_renderer
from app.services.youtube_upload_service import youtube_upload_service
from app.worker.kafka_producer import publish_ai_job_status

logger = logging.getLogger(__name__)

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
                lines.append(f"- Topic: {n['title']}\n  Description: {desc}")
            else:
                lines.append(f"- Topic: {n['title']}")
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
    """
    # 0. Reset async clients for safety in worker thread
    reset_async_clients()

    job_dir = f"/tmp/video_jobs/{job_id}"
    os.makedirs(job_dir, exist_ok=True)
    logger.info(f"Starting video generation job {job_id} in {job_dir}")

    try:
        # ── Phase 1: Context Aggregation (0% → 15%) ──
        logger.info(f"[{job_id}] Phase 1: Context Aggregation...")
        await publish_ai_job_status(job_id, "processing", progress=5)
        
        # Determine character budget based on LLM bindings
        character_budget = 15000  # Default conservative budget (~4,000 tokens)
        try:
            from app.core.llm_gateway.registry import get_registry
            registry = get_registry()
            chain = await registry.get_binding_chain(TASK_VIDEO_SCRIPT_GEN)
            if chain:
                primary_binding = chain[0]
                model = primary_binding.model
                if model.provider_code in ("gemini", "anthropic"):
                    character_budget = 1000000  # 1M characters (~250k tokens)
                elif model.context_window > 100000:
                    character_budget = 300000
                logger.info(f"[{job_id}] Target model: {model.model_name} (provider: {model.provider_code}). Character budget: {character_budget}")
        except Exception as exc:
            logger.warning(f"Failed to query LLM registry for budget sizing: {exc}")

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

        context = select_and_compress_nodes(rows, character_budget)
        if not context:
            context = "General overview of the course. No specific topic outline was found in the database."

        await publish_ai_job_status(job_id, "processing", progress=15)

        # ── Phase 2: Master Planner (15% → 30%) ──
        logger.info(f"[{job_id}] Phase 2: Video Planning...")
        await publish_ai_job_status(job_id, "processing", progress=20)

        lang_name = "Vietnamese" if language == "vi" else "English"
        
        plan_system = (
            "You are an educational curriculum architect and video planner. "
            "Your job is to structure an educational overview video based on the course concepts provided. "
            "Outline the video hook, core concepts to cover, target audience, flow logic, and the estimated number of slides (between 3 and 10). "
            f"Write all textual outlines in {lang_name}."
        )

        plan_user = (
            f"Here is the course outline/topics:\n{context}\n\n"
            f"User Prompt constraints: {custom_prompt or 'No custom instructions'}\n\n"
            f"Generate a slide-by-slide VideoPlan matching the required JSON schema."
        )

        plan: VideoPlan = await chat_complete_structured(
            messages=[
                {"role": "system", "content": plan_system},
                {"role": "user", "content": plan_user}
            ],
            response_model=VideoPlan,
            temperature=0.3,
            task=TASK_VIDEO_SCRIPT_GEN
        )
        logger.info(f"[{job_id}] Video Plan generated: {plan.estimated_slides} slides.")
        await publish_ai_job_status(job_id, "processing", progress=30)

        # ── Phase 3: Scriptwriter (30% → 45%) ──
        logger.info(f"[{job_id}] Phase 3: Script Writing...")
        await publish_ai_job_status(job_id, "processing", progress=35)

        script_system = (
            "You are an expert video scriptwriter and educational content creator. "
            "Your job is to write a highly engaging script for a slide-based overview video. "
            f"For each slide, provide a concise title, short slide body text (brief bullet points, maximum 3 lines/sentences), "
            "and the exact narration text to be read by the TTS system. "
            f"Ensure you write the output in {lang_name}."
        )

        script_user = (
            f"Outline context:\n{context}\n\n"
            f"Video Plan details:\n"
            f"- Target Audience: {plan.target_audience}\n"
            f"- Hook: {plan.hook}\n"
            f"- Core Concepts: {', '.join(plan.core_concepts)}\n"
            f"- Flow: {plan.flow_logic}\n"
            f"- Estimated Slides: {plan.estimated_slides}\n\n"
            f"Generate a VideoScript. The number of slides MUST BE exactly {plan.estimated_slides}."
        )

        script: VideoScript = await chat_complete_structured(
            messages=[
                {"role": "system", "content": script_system},
                {"role": "user", "content": script_user}
            ],
            response_model=VideoScript,
            temperature=0.4,
            task=TASK_VIDEO_SCRIPT_GEN
        )
        logger.info(f"[{job_id}] Video Script generated successfully: {script.video_title}")
        await publish_ai_job_status(job_id, "processing", progress=45)

        # ── Phase 4: Rendering (45% → 80%) ──
        logger.info(f"[{job_id}] Phase 4: Video Rendering...")
        slide_videos = []
        n_slides = len(script.slides)

        for i, s in enumerate(script.slides):
            logger.info(f"[{job_id}] Rendering slide {i+1}/{n_slides}...")
            
            image_path = os.path.join(job_dir, f"slide_{i}.png")
            audio_path = os.path.join(job_dir, f"slide_{i}.mp3")
            video_path = os.path.join(job_dir, f"slide_{i}.mp4")

            # Draw text on template
            video_renderer.render_slide_image(s.title, s.body, template_type, image_path)
            
            # Generate Audio
            duration = await video_renderer.render_slide_audio(s.narration, language, audio_path)
            
            # Assemble Video Slide
            video_renderer.assemble_slide_video(image_path, audio_path, duration, video_path)
            
            slide_videos.append(video_path)
            
            # Publish incremental progress
            progress = 45 + int(30 * (i + 1) / n_slides)
            await publish_ai_job_status(job_id, "processing", progress=progress)

        # Concatenate slide videos
        final_video_path = os.path.join(job_dir, "final.mp4")
        video_renderer.concatenate_videos(slide_videos, final_video_path)
        
        await publish_ai_job_status(job_id, "processing", progress=80)

        # ── Phase 5: YouTube Upload (80% → 100%) ──
        logger.info(f"[{job_id}] Phase 5: YouTube Upload...")
        await publish_ai_job_status(job_id, "processing", progress=90)
        
        desc = (
            f"Overview: {script.video_title}\n\n"
            f"{script.outro_narration}\n\n"
            f"Generated automatically by AI Course Overview Video Pipeline."
        )
        
        upload_result = youtube_upload_service.upload_video(
            filepath=final_video_path,
            title=script.video_title,
            description=desc,
            privacy="unlisted"
        )
        
        logger.info(f"[{job_id}] Video successfully uploaded: {upload_result}")
        await publish_ai_job_status(job_id, "processing", progress=100)
        return upload_result

    except Exception as exc:
        logger.error(f"[{job_id}] Exception in video generation pipeline: {exc}", exc_info=True)
        raise exc

    finally:
        # Cleanup temp directory
        if os.path.exists(job_dir):
            try:
                shutil.rmtree(job_dir)
                logger.info(f"Cleaned up temporary job directory {job_dir}")
            except OSError as e:
                logger.error(f"Failed to delete temp dir {job_dir}: {e}")
