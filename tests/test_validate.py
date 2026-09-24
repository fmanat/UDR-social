import dataclasses
import shutil
from datetime import datetime, timezone

from udr_publish.validate import validate_pack

NOW = datetime(2026, 9, 24, 8, 0, tzinfo=timezone.utc)


def test_example_pack_is_valid_in_draft(make_pack, settings):
    result = validate_pack(make_pack(), settings, now=NOW)
    assert result.ok, result.errors
    assert result.pack.mode == "draft"
    assert [p.network.key for p in result.pack.plans] == [
        "facebook", "instagram", "youtube", "youtube_shorts", "tiktok", "linkedin", "x"]
    assert any("espace réservé" in w for w in result.warnings)


def test_live_refused_when_server_disallows_it(make_pack, settings):
    pack = make_pack(lambda p: p["publish"].update(mode="live"))
    result = validate_pack(pack, settings, now=NOW)
    assert not result.ok
    assert any("PUBLISH_ALLOW_LIVE" in e for e in result.errors)


def test_live_with_past_date_is_refused(make_pack, settings):
    live = dataclasses.replace(settings, allow_live=True)
    pack = make_pack(lambda p: p["publish"].update(mode="live", schedule="2026-09-24T09:00:00+02:00"))
    result = validate_pack(pack, live, now=NOW)
    assert not result.ok
    assert any("déjà passée" in e for e in result.errors)


def test_draft_with_past_date_keeps_going_without_date(make_pack, settings):
    pack = make_pack(lambda p: p["publish"].update(schedule="2026-09-01T09:00:00+02:00"))
    result = validate_pack(pack, settings, now=NOW)
    assert result.ok
    fb = result.pack.plans[0]
    assert fb.scheduled_at is None
    linkedin = [p for p in result.pack.plans if p.network.key == "linkedin"][0]
    assert linkedin.scheduled_at is not None  # linkedin_schedule reste dans le futur


def test_missing_mode_defaults_to_draft(make_pack, settings):
    result = validate_pack(make_pack(lambda p: p["publish"].pop("mode")), settings, now=NOW)
    assert result.ok and result.pack.mode == "draft"


def test_unknown_network_and_missing_fields_are_refused(make_pack, settings):
    def mutate(p):
        p["posts"]["mastodon"] = {"media": "vertical", "text": "x"}
        del p["posts"]["youtube"]["title"]
    result = validate_pack(make_pack(mutate), settings, now=NOW)
    assert not result.ok
    joined = " ".join(result.errors)
    assert "mastodon" in joined and "title" in joined


def test_disabled_network_is_skipped(make_pack, settings):
    result = validate_pack(make_pack(lambda p: p["posts"]["x"].update(enabled=False)), settings, now=NOW)
    assert result.ok
    assert "x" in result.pack.skipped
    assert "x" not in [p.network.key for p in result.pack.plans]


def test_non_master_video_is_refused(make_pack, settings, videos):
    pack = make_pack()
    shutil.copy(videos / "bad.mp4", pack / "UDR_memoire_territoire_V1_9x16.mp4")
    result = validate_pack(pack, settings, now=NOW)
    assert not result.ok
    joined = " ".join(result.errors)
    assert "1080×1920 attendu" in joined
    assert "25 i/s attendu" in joined
    assert "stéréo attendu" in joined
    assert "128 kbit/s attendu" in joined


def test_missing_video_is_refused(make_pack, settings):
    pack = make_pack()
    (pack / "UDR_memoire_territoire_V1_16x9.mp4").unlink()
    result = validate_pack(pack, settings, now=NOW)
    assert not result.ok
    assert any("absente du pack" in e for e in result.errors)


def test_invalid_json_is_refused(tmp_path, settings):
    (tmp_path / "posts.json").write_text("{pas du json", encoding="utf-8")
    result = validate_pack(tmp_path, settings, now=NOW)
    assert not result.ok and "JSON" in result.errors[0]
