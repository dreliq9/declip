from declip.pipelines.production import generate_ass, _reframe_filter, _schema_transition


def test_generate_ass_groups_words_and_emits_karaoke_tags():
    words = [
        {"word": f"w{i}", "start": i * 0.5, "end": i * 0.5 + 0.4, "confidence": 1.0}
        for i in range(7)
    ]
    content = generate_ass(words, style="bold", resolution=(1080, 1920))
    assert "PlayResX: 1080" in content
    assert "PlayResY: 1920" in content
    assert content.count("Dialogue: 0,") == 2
    assert "{\\kf40}w0" in content


def test_storyboard_transition_aliases_match_schema_names():
    assert _schema_transition("fade") == "dissolve"
    assert _schema_transition("fadeblack") == "fade_black"
    assert _schema_transition("wipeleft") == "wipe_left"
    assert _schema_transition("dissolve") == "dissolve"


def test_center_crop_scales_up_before_cropping():
    filter_text, complex_filter = _reframe_filter(1080, 1920, "9:16", "center_crop")
    assert complex_filter is False
    assert "force_original_aspect_ratio=increase" in filter_text
    assert "crop=1080:1920" in filter_text


def test_blur_background_uses_complex_filter_graph():
    filter_text, complex_filter = _reframe_filter(1080, 1920, "9:16", "blur_bg")
    assert complex_filter is True
    assert "[0:v]split[bg][fg]" in filter_text
    assert "[vout]" in filter_text
