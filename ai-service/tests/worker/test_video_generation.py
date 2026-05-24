import pytest
from pydantic import ValidationError
from app.schemas.video_schemas import VideoPlan, SlideContent, VideoScript
from app.services.video_renderer import VideoRenderer, VOICE_MAP

def test_video_plan_validation():
    # Valid plan
    plan = VideoPlan(
        hook="Welcome to the course",
        core_concepts=["Big Data", "MapReduce"],
        flow_logic="Introduction -> MapReduce -> Exercises",
        estimated_slides=5,
        target_audience="Beginners"
    )
    assert plan.estimated_slides == 5

    # Invalid estimated_slides (too low)
    with pytest.raises(ValidationError):
        VideoPlan(
            hook="Welcome",
            core_concepts=["Topic"],
            flow_logic="Intro",
            estimated_slides=2,  # min is 3
            target_audience="All"
        )

def test_slide_content_limits():
    # Valid slide content
    slide = SlideContent(
        title="Slide 1",
        body="This is slide body content",
        narration="Narration script for slide 1"
    )
    assert slide.title == "Slide 1"

    # Title too long (>60)
    with pytest.raises(ValidationError):
        SlideContent(
            title="A" * 61,
            body="Valid body",
            narration="Valid narration"
        )

def test_renderer_text_wrapping():
    renderer = VideoRenderer()
    font = renderer._get_font(20, bold=False)
    
    long_text = "This is a very long text that will exceed the maximum text wrapping width of the image draw area"
    lines = renderer._wrap_text(long_text, font, 200)
    
    assert len(lines) > 1
    assert " ".join(lines) == long_text

def test_voice_mapping():
    assert VOICE_MAP["vi"] == "vi-VN-HoaiMyNeural"
    assert VOICE_MAP["en"] == "en-US-AriaNeural"
