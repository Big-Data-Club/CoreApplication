from __future__ import annotations

import re
import unicodedata
from xml.etree import ElementTree as ET

import pytest

from app.services.studio.code_layout import code_pages
from app.services.studio.html_renderer import diagram, render_html
from app.services.studio.plan_schema import VisualSpec
from app.services.studio.storyboard import compile_storyboard
from tests.test_studio_media import lesson

PTHREAD_CODE = """#include <pthread.h>

void *work(void *arg) {
  int *value = (int *)arg;
  *value += 1;
  return NULL;
}

int main(void) {
  pthread_t thread;
  int value = 0;
  pthread_create(&thread, NULL, work, &value);
  pthread_join(thread, NULL);
  return value != 1;
}
"""


def code_lesson(code=PTHREAD_CODE):
    plan = lesson()
    section = plan.sections[0]
    section.title = "Viết chương trình đa luồng với pthreads và fork‑join"
    section.visual_type = "code_execution"
    section.visual_spec = VisualSpec(code=code)
    section.slide_bullets = ["Tạo thread", "Chờ thread hoàn tất"]
    section.animation_steps = ["create", "work", "join"]
    return plan


@pytest.mark.parametrize("portrait", [False, True])
@pytest.mark.parametrize("code", [PTHREAD_CODE, "pthread_create(" + "argument, "*30 + "NULL);",
                                  "\t// Tiếng Việt: dữ liệu và 线程\n" + "x();\n"*61])
def test_code_pages_preserve_all_source_and_readable_bounds(portrait, code):
    pages = code_pages(code, portrait)
    assert all(len(page) <= 12 for page in pages)
    restored = {}
    for page in pages:
        for row in page:
            restored[row.source_line] = restored.get(row.source_line, "") + row.text
            width = sum(0 if unicodedata.combining(c) else 2 if unicodedata.east_asian_width(c) in {"W", "F"} else 1 for c in row.text)
            assert width <= (42 if portrait else 68)
    assert list(restored.values()) == [line.expandtabs(4) for line in code.splitlines()]


@pytest.mark.parametrize("aspect", ["16:9", "9:16"])
def test_dense_code_gets_all_pdf_sheets_but_keeps_one_video_narration(aspect):
    board = compile_storyboard(code_lesson(), {"aspect_ratio": aspect}, video=True)
    original = board.model_dump()
    page_count = len(code_pages(PTHREAD_CODE, aspect == "9:16"))
    slides = render_html(board)
    video = render_html(board, video=True)
    assert page_count > 1
    assert len(re.findall(r'<section class="scene"', slides)) == page_count
    assert len(re.findall(r'<section class="scene"', video)) == 1
    assert video.count('data-code-page="') == page_count
    assert f'data-code-pages="{page_count}"' in video
    assert board.model_dump() == original
    assert len(board.scenes) == 1 and board.scenes[0].duration is None
    assert "pthread_join" in slides


def test_wrapped_long_line_is_escaped_and_never_treated_as_html():
    code = 'puts("<script>alert(1)</script>' + 'x'*110 + '");'
    board = compile_storyboard(code_lesson(code), {})
    svg = ET.fromstring(diagram(board.scenes[0], False))
    rows = [element.text or "" for element in svg.iter() if element.attrib.get("data-safe") == "code"]
    assert "".join(rows) == code
    assert len(rows) > 1
    assert not any(element.tag.endswith("script") for element in svg.iter())


def test_short_code_keeps_a_single_page_without_changing_its_scene_id():
    board = compile_storyboard(code_lesson("pthread_join(thread, NULL);"), {})
    html = render_html(board)
    assert html.count('<section class="scene"') == 1
    assert "scene_01_code_" not in html


def test_wrapped_pthread_call_stays_together_on_a_page():
    pages = code_pages(PTHREAD_CODE, True)
    locations = [index for index, page in enumerate(pages) for row in page if row.source_line == 12]
    assert len(locations) > 1 and len(set(locations)) == 1
    assert not pages[1][0].continuation
    assert pages[1][0].text.startswith("  pthread_create(")
    assert any(row.continuation and "&value);" in row.text for row in pages[1])
