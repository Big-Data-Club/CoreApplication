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

def test_resize_and_crop(tmp_path):
    import os
    from PIL import Image
    from app.services.video_renderer import video_renderer

    # Create dummy source image (wider than target)
    src_path = os.path.join(tmp_path, "source.png")
    img = Image.new("RGB", (1000, 500), color="red")
    img.save(src_path)

    # Crop/resize to target (750x600)
    resized = video_renderer._resize_and_crop(img, 750, 600)
    assert resized.width == 750
    assert resized.height == 600

def test_split_layout_rendering(tmp_path):
    import os
    from PIL import Image
    from app.services.video_renderer import video_renderer

    # Create dummy side image
    side_img_path = os.path.join(tmp_path, "side.png")
    side_img = Image.new("RGB", (400, 400), color="blue")
    side_img.save(side_img_path)

    output_path = os.path.join(tmp_path, "output.png")
    # Render slide image with side image
    video_renderer.render_slide_image(
        title="Test Split Layout Title",
        body="* Bullet point 1\n* Bullet point 2",
        template_type="dark",
        output_path=output_path,
        local_image_path=side_img_path
    )

    assert os.path.exists(output_path)
    result_img = Image.open(output_path)
    assert result_img.width > 0 and result_img.height > 0

def test_draw_concept_diagram(tmp_path):
    import os
    from app.services.video_generation_service import draw_concept_diagram

    nodes = [
        {"id": 1, "title": "MapReduce Intro"},
        {"id": 2, "title": "Mapper details"},
        {"id": 3, "title": "Reducer details"}
    ]
    relations = [
        {"source_node_id": 1, "target_node_id": 2, "relation_type": "prerequisite"},
        {"source_node_id": 1, "target_node_id": 3, "relation_type": "prerequisite"}
    ]

    output_path = os.path.join(tmp_path, "concept_diagram.png")
    draw_concept_diagram(nodes, relations, output_path, "dark")

    assert os.path.exists(output_path)
    from PIL import Image
    result_img = Image.open(output_path)
    assert result_img.size == (750, 600)
