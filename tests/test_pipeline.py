import dataclasses
import json

from udr_publish import report as R
from udr_publish.pipeline import Publisher

from conftest import ACCOUNTS, EXAMPLE, FAKE_API_KEY


def only(*keys):
    def mutate(p):
        p["posts"] = {k: v for k, v in p["posts"].items() if k in keys}
    return mutate


def statuses(rep):
    return {e["network"]: e["status"] for e in rep["networks"]}


def test_draft_creates_one_draft_per_network_with_texts_unchanged(make_pack, settings, world):
    rep = Publisher(settings, session=world).run(make_pack())
    assert rep["ok"], rep["report_text"]
    assert set(statuses(rep).values()) == {R.BROUILLON}
    creates = [c for c in world.calls if c[0] == "POST"]
    assert len(creates) == 7
    for _, _, body, _ in creates:
        key = body["external_id"].split(":")[1]
        assert body["caption"] == EXAMPLE["posts"][key]["text"]          # tel quel
        assert body["isDraft"] is True
        assert body["media"][0]["url"].startswith("https://res.cloudinary.com/dl8itl9nw/video/upload/v")
        if key.startswith("youtube"):
            config = body["account_configurations"][0]["configuration"]
            assert config["title"] == EXAMPLE["posts"][key]["title"]
            assert config["privacy_status"] == "public"
    by_key = {b["external_id"].split(":")[1]: b for _, _, b, _ in creates}
    assert by_key["tiktok"]["account_configurations"][0]["configuration"] == {"privacy_status": "public"}
    assert by_key["linkedin"]["scheduled_at"] == "2030-01-02T08:30:00+01:00"
    assert by_key["facebook"]["scheduled_at"] == "2030-01-01T19:30:00+01:00"
    # une vidéo par format, pas plus
    assert len(world.uploads) == 2
    fb = [e for e in rep["networks"] if e["network"] == "facebook"][0]
    assert fb["links"]["post_for_me"] == f"https://app.postforme.dev/team_1/proj_1/posts/{fb['pfm_post_id']}"
    assert fb["links"]["video"].endswith("/udr-publish/UDR_test_V1/horizontal.mp4")


def test_same_pack_twice_does_not_send_twice(make_pack, settings, world):
    pack = make_pack(only("facebook", "instagram"))
    Publisher(settings, session=world).run(pack)
    rep = Publisher(settings, session=world).run(pack)
    assert set(statuses(rep).values()) == {R.BROUILLON_INCHANGE}
    assert world.count("POST") == 2 and world.count("PUT") == 0
    assert len(world.uploads) == 2  # vidéos réutilisées, pas ré-uploadées


def test_changed_draft_is_updated_not_duplicated(make_pack, settings, world):
    Publisher(settings, session=world).run(make_pack(only("facebook")))
    rep = Publisher(settings, session=world).run(
        make_pack(lambda p: (only("facebook")(p), p["posts"]["facebook"].update(text="Nouveau texte."))))
    assert statuses(rep) == {"facebook": R.BROUILLON_MAJ}
    assert world.count("POST") == 1 and world.count("PUT") == 1
    assert list(world.posts.values())[0]["caption"] == "Nouveau texte."


def test_live_promotes_the_draft_then_never_resends(make_pack, settings, world):
    Publisher(settings, session=world).run(make_pack(only("facebook", "x")))
    live = dataclasses.replace(settings, allow_live=True)
    live_pack = make_pack(lambda p: (only("facebook", "x")(p), p["publish"].update(mode="live")))
    rep = Publisher(live, session=world).run(live_pack)
    assert set(statuses(rep).values()) == {R.PROGRAMME}
    puts = [c for c in world.calls if c[0] == "PUT"]
    assert len(puts) == 2 and all(c[2]["isDraft"] is False for c in puts)
    assert world.count("POST") == 2
    again = Publisher(live, session=world).run(live_pack)
    assert set(statuses(again).values()) == {R.DEJA_ENVOYE}
    assert world.count("POST") == 2 and world.count("PUT") == 2  # aucun renvoi
    assert len(world.uploads) == 1  # Facebook et X partagent la vidéo horizontale, jamais ré-uploadée


def test_scheduled_post_deleted_by_hand_is_sent_again_on_redeposit(make_pack, settings, world):
    live = dataclasses.replace(settings, allow_live=True)
    pack = make_pack(lambda p: (only("facebook")(p), p["publish"].update(mode="live")))
    Publisher(live, session=world).run(pack)
    world.posts.clear()  # supprimé dans le tableau de bord Post For Me
    rep = Publisher(live, session=world).run(pack)
    assert statuses(rep) == {"facebook": R.PROGRAMME}
    assert world.count("POST") == 2


def test_failure_on_one_network_does_not_cancel_the_others(make_pack, settings, world):
    world.fail_accounts[ACCOUNTS["instagram"]] = (
        400, {"message": ["invalid social accounts, not owned by user"], "error": "Bad Request"})
    rep = Publisher(settings, session=world).run(make_pack(only("facebook", "instagram", "linkedin")))
    assert statuses(rep) == {"facebook": R.BROUILLON, "instagram": R.ERREUR, "linkedin": R.BROUILLON}
    assert not rep["ok"]
    ig = [e for e in rep["networks"] if e["network"] == "instagram"][0]
    assert "invalid social accounts" in ig["message"]
    assert "invalid social accounts" in rep["report_text"]
    # le réseau en erreur est retenté au dépôt suivant, les autres non
    del world.fail_accounts[ACCOUNTS["instagram"]]
    rep2 = Publisher(settings, session=world).run(make_pack(only("facebook", "instagram", "linkedin")))
    assert statuses(rep2) == {"facebook": R.BROUILLON_INCHANGE, "instagram": R.BROUILLON,
                              "linkedin": R.BROUILLON_INCHANGE}


def test_missing_account_only_fails_that_network(make_pack, settings, world):
    accounts = {**settings.pfm_accounts, "tiktok": None}
    rep = Publisher(dataclasses.replace(settings, pfm_accounts=accounts), session=world).run(
        make_pack(only("facebook", "tiktok")))
    assert statuses(rep) == {"tiktok": R.ERREUR, "facebook": R.BROUILLON}
    assert "PFM_ACCOUNT_TIKTOK" in rep["report_text"]
    assert [u["public_id"] for u in world.uploads] == ["udr-publish/UDR_test_V1/horizontal"]


def test_cloudinary_failure_is_reported_per_network(make_pack, settings, world):
    world.cloudinary_fail = True
    rep = Publisher(settings, session=world).run(make_pack(only("facebook")))
    assert statuses(rep) == {"facebook": R.ERREUR}
    assert "Invalid Signature" in rep["networks"][0]["message"]
    assert world.count("POST") == 0


def test_post_known_to_postforme_but_not_journaled_is_adopted(make_pack, settings, world, tmp_path):
    pack = make_pack(only("facebook"))
    Publisher(settings, session=world).run(pack)
    settings.journal_path.unlink()  # journal perdu (ex. redéploiement sans volume)
    rep = Publisher(settings, session=world).run(pack)
    assert world.count("POST") == 1  # pas de doublon
    assert statuses(rep) == {"facebook": R.BROUILLON_MAJ}


def test_refused_pack_touches_nothing(make_pack, settings, world):
    rep = Publisher(settings, session=world).run(make_pack(lambda p: p["posts"]["x"].update(text="a" * 300)))
    assert rep["refused"] and not rep["ok"]
    assert world.calls == [] and world.uploads == []
    assert "PACK REFUSÉ" in rep["report_text"]


def test_dry_run_sends_nothing(make_pack, settings, world):
    rep = Publisher(settings, session=world).run(make_pack(), dry_run=True)
    assert set(statuses(rep).values()) == {R.SIMULATION}
    assert world.calls == [] and world.uploads == []


def test_check_reports_published_error_and_tiktok_to_verify(make_pack, settings, world):
    live = dataclasses.replace(settings, allow_live=True)
    Publisher(live, session=world).run(
        make_pack(lambda p: (only("facebook", "tiktok", "x")(p), p["publish"].update(mode="live"))))
    ids = {p["external_id"].split(":")[1]: pid for pid, p in world.posts.items()}
    for pid in ids.values():
        world.posts[pid]["status"] = "processed"
    world.results[ids["facebook"]] = [{"success": True, "error": None, "details": {},
                                       "platform_data": {"id": "1", "url": "https://facebook.com/p/1"}}]
    world.results[ids["tiktok"]] = [{"success": False, "error": None,
                                     "details": {"status": "Processing",
                                                 "message": "Still Proccessing, check TikTok account to confirm status"},
                                     "platform_data": {"url": "https://www.tiktok.com/@udr"}}]
    world.results[ids["x"]] = [{"success": False, "error": "Failed to post to Twitter: duplicate content",
                                "details": {}, "platform_data": {}}]
    rep = Publisher(live, session=world).check("UDR_test_V1")
    assert statuses(rep) == {"facebook": R.PUBLIE, "tiktok": R.A_VERIFIER, "x": R.ERREUR}
    assert "https://facebook.com/p/1" in rep["report_text"]
    assert "peut avoir été publiée" in rep["report_text"]
    assert "duplicate content" in rep["report_text"]


def test_secrets_never_reach_report_or_journal(make_pack, settings, world):
    world.fail_accounts[ACCOUNTS["facebook"]] = (401, {"message": f"bad key {FAKE_API_KEY}"})
    rep = Publisher(settings, session=world).run(make_pack(only("facebook")))
    assert FAKE_API_KEY not in json.dumps(rep)
    assert FAKE_API_KEY not in settings.journal_path.read_text()
    assert "***" in rep["report_text"]


def test_journal_records_every_step(make_pack, settings, world):
    Publisher(settings, session=world).run(make_pack(only("facebook")))
    events = [json.loads(line)["event"] for line in settings.journal_path.read_text().splitlines()]
    assert events == ["received", "upload", "post"]
