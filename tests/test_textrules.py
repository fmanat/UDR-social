from udr_publish.textrules import instagram_problems, js_len, text_problems

from conftest import EXAMPLE


def test_example_texts_are_sent_unchanged():
    for key, post in EXAMPLE["posts"].items():
        assert text_problems(key, post["text"], post.get("title")) == [], key


def test_js_length_counts_utf16_units():
    assert js_len("🔗") == 2
    assert js_len("é") == 1


def test_x_over_280_is_refused():
    assert any("280" in p for p in text_problems("x", "a" * 281))
    assert text_problems("x", "a" * 280) == []


def test_caption_over_2200_is_refused_everywhere():
    for key in ("facebook", "linkedin", "tiktok"):
        assert any("2200" in p for p in text_problems(key, "a" * 2201))


def test_linkedin_400_chars_is_fine():
    assert text_problems("linkedin", "mot " * 100) == []


def test_instagram_whitespace_and_duplicates_are_refused():
    assert instagram_problems("deux  espaces")
    assert instagram_problems("fin de ligne \nsuite")
    assert instagram_problems("#Vosges et #vosges")
    assert instagram_problems("a\n\n\nb")
    assert instagram_problems(" ".join(f"#h{i}" for i in range(31)))
    assert instagram_problems("ok\n.\n.\n#hommage #mémoire") == []


def test_youtube_title_rules():
    assert any("retours à la ligne" in p for p in text_problems("youtube", "desc", "titre\nsuite"))
    assert any("< et >" in p for p in text_problems("youtube", "desc", "a <b>"))
    assert any("100" in p for p in text_problems("youtube", "desc", "t" * 101))
    assert any("manquant" in p for p in text_problems("youtube", "desc", None))
    assert any("< et >" in p for p in text_problems("youtube_shorts", "desc <x>", "ok"))
