import dataclasses
import io
import json

from service.app import create_app
from udr_publish.pipeline import Publisher

TOKEN = "service-token-XYZ-987"


def client(settings, world):
    app = create_app(settings, publisher_factory=lambda: Publisher(settings, session=world))
    app.testing = True
    return app.test_client()


def form(pack_dir):
    posts = json.loads((pack_dir / "posts.json").read_text())
    return {
        "posts_json": (io.BytesIO((pack_dir / "posts.json").read_bytes()), "posts.json"),
        "video_vertical": (io.BytesIO((pack_dir / posts["media"]["vertical"]).read_bytes()), "n_importe.mp4"),
        "video_horizontal": (io.BytesIO((pack_dir / posts["media"]["horizontal"]).read_bytes()), "autre.mp4"),
    }


def test_healthz_is_public(settings, world):
    assert client(settings, world).get("/healthz").get_json() == {"ok": True, "live_enabled": False}


def test_deposit_requires_the_shared_secret(settings, world, make_pack):
    c = client(settings, world)
    assert c.post("/packs", data=form(make_pack())).status_code == 401
    bad = {"Authorization": "Bearer mauvais"}
    assert c.post("/packs", data=form(make_pack()), headers=bad).status_code == 401
    assert world.calls == []


def test_service_without_token_refuses_everything(settings, world, make_pack):
    c = client(dataclasses.replace(settings, service_token=None), world)
    assert c.post("/packs", data=form(make_pack()), headers={"Authorization": "Bearer "}).status_code == 503


def test_deposit_runs_the_pipeline_and_returns_the_report(settings, world, make_pack):
    c = client(settings, world)
    pack = make_pack(lambda p: p.update(posts={"facebook": p["posts"]["facebook"]}))
    res = c.post("/packs", data=form(pack), headers={"Authorization": f"Bearer {TOKEN}"})
    assert res.status_code == 200
    body = res.get_json()
    assert body["ok"] and body["networks"][0]["status"] == "brouillon"
    assert body["report_subject"].startswith("[UDR publication] UDR_test_V1")
    assert "Facebook : BROUILLON" in body["report_text"]
    # les fichiers reçus sont supprimés après traitement
    assert list((settings.data_dir / "incoming").iterdir()) == []


def test_refused_pack_still_returns_200_with_report(settings, world, make_pack):
    c = client(settings, world)
    pack = make_pack(lambda p: p["posts"]["x"].update(text="a" * 300))
    body = c.post("/packs", data=form(pack), headers={"Authorization": f"Bearer {TOKEN}"}).get_json()
    assert body["refused"] and "PACK REFUSÉ" in body["report_text"]


def test_status_endpoint(settings, world, make_pack):
    c = client(settings, world)
    headers = {"Authorization": f"Bearer {TOKEN}"}
    pack = make_pack(lambda p: p.update(posts={"facebook": p["posts"]["facebook"]}))
    c.post("/packs", data=form(pack), headers=headers)
    body = c.get("/packs/UDR_test_V1/status", headers=headers).get_json()
    assert body["kind"] == "suivi" and body["networks"][0]["status"] == "brouillon"
    assert c.get("/packs/..%2Fetc/status", headers=headers).status_code in (400, 404)
