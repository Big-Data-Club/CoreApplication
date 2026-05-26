from pydantic import BaseModel, Field
from typing import Optional, List

class VideoGenerationPayload(BaseModel):
    target_type: str  # "course" or "section"
    target_id: int
    custom_prompt: Optional[str] = None
    language: str = "vi"
    template_type: str = "dark"  # "dark" or "light"
    created_by: int

class VideoPlan(BaseModel):
    """Phase 2 output: Educational Architect"""
    hook: str = Field(description="Opening hook to grab attention")
    core_concepts: List[str] = Field(description="Key concepts to cover")
    flow_logic: str = Field(description="Logical flow of the video")
    estimated_slides: int = Field(ge=3, le=10, description="Number of slides")
    target_audience: str = Field(description="Who this video is for")

class SlideContent(BaseModel):
    """Single slide in the video"""
    title: str = Field(..., max_length=60, description="Slide title")
    body: str = Field(..., max_length=300, description="Slide body text")
    narration: str = Field(..., description="TTS narration script for this slide")
    image_url: Optional[str] = Field(None, description="URL of an extracted document diagram or generated graph")
    visual_type: Optional[str] = Field("text_only", description="'text_only' | 'document_image' | 'knowledge_graph'")

class VideoScript(BaseModel):
    """Phase 3 output: Content Creator"""
    video_title: str = Field(..., max_length=100)
    slides: List[SlideContent] = Field(..., min_length=3, max_length=10)
    outro_narration: str = Field(..., description="Closing narration")
