"""
Unit tests for ThoughtStreamParser to verify real-time CoT token stream separation.
"""
import pytest
from app.agents.core.react_loop import ThoughtStreamParser


def test_parser_basic_cot_and_content():
    parser = ThoughtStreamParser()
    
    # 1. Feed start tag + thought content
    evs1 = parser.feed("<thought>Analyzing user intent")
    assert evs1 == [("thought", "Analyzing user intent")]
    
    # 2. Feed thought continuation + end tag + content start
    evs2 = parser.feed("... Done.</thought>Here is the answer")
    assert evs2 == [
        ("thought", "... Done."),
        ("content", "Here is the answer")
    ]
    
    # 3. Feed remaining content
    evs3 = parser.feed(" to your question.")
    assert evs3 == [("content", " to your question.")]
    
    assert parser.thought_buffer == "Analyzing user intent... Done."
    assert parser.content_buffer == "Here is the answer to your question."


def test_parser_no_cot():
    parser = ThoughtStreamParser()
    
    # Standard response without <thought> prefix
    evs1 = parser.feed("Direct response ")
    assert evs1 == [("content", "Direct response ")]
    
    evs2 = parser.feed("without thought tags.")
    assert evs2 == [("content", "without thought tags.")]
    
    assert parser.thought_buffer == ""
    assert parser.content_buffer == "Direct response without thought tags."


def test_parser_split_end_tag():
    parser = ThoughtStreamParser()
    
    evs1 = parser.feed("<thought>Deep reasoning</thou")
    # thou part of the end tag should be buffered to avoid printing partial tags as thought
    assert evs1 == [("thought", "Deep reasoning")]
    
    evs2 = parser.feed("ght>Response text")
    assert evs2 == [("content", "Response text")]
    
    assert parser.thought_buffer == "Deep reasoning"
    assert parser.content_buffer == "Response text"


def test_parser_split_start_tag():
    parser = ThoughtStreamParser()
    
    evs1 = parser.feed("<tho")
    assert evs1 == [] # Buffered while resolving tag
    
    evs2 = parser.feed("ught>Thinking process</thought>Hello")
    assert evs2 == [
        ("thought", "Thinking process"),
        ("content", "Hello")
    ]
    
    assert parser.thought_buffer == "Thinking process"
    assert parser.content_buffer == "Hello"
