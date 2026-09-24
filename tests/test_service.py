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


# ------------------------------------------------------------ page /depot
PAGE_PASSWORD = "mot-de-passe-page-42"


def page_client(settings, world, password=PAGE_PASSWORD):
    return client(dataclasses.replace(settings, page_password=password), world)


def basic(password, user="udr"):
    import base64
    return {"Authorization": "Basic " + base64.b64encode(f"{user}:{password}".encode()).decode()}


def test_page_is_disabled_without_a_long_enough_password(settings, world):
    assert client(settings, world).get("/depot", headers=basic("")).status_code == 503
    assert page_client(settings, world, "court").get("/depot", headers=basic("court")).status_code == 503


def test_page_asks_for_the_password(settings, world):
    c = page_client(settings, world)
    res = c.get("/depot")
    assert res.status_code == 401 and res.headers["WWW-Authenticate"].startswith("Basic")
    assert c.get("/depot", headers=basic("mauvais")).status_code == 401
    # le jeton du service n'ouvre pas la page
    assert c.get("/depot", headers=basic(TOKEN)).status_code == 401
    page = c.get("/depot", headers=basic(PAGE_PASSWORD, user="n'importe"))
    assert page.status_code == 200 and "Déposer et approuver" in page.get_data(as_text=True)


def test_page_deposit_runs_the_pipeline(settings, world, make_pack):
    c = page_client(settings, world)
    pack = make_pack(lambda p: p.update(posts={"facebook": p["posts"]["facebook"]}))
    headers = {**basic(PAGE_PASSWORD), "X-UDR-Depot": "1"}
    body = c.post("/depot/envoi", data=form(pack), headers=headers).get_json()
    assert body["ok"] and body["networks"][0]["status"] == "brouillon"


def test_page_deposit_requires_password_and_page_header(settings, world, make_pack):
    c = page_client(settings, world)
    assert c.post("/depot/envoi", data=form(make_pack()), headers={"X-UDR-Depot": "1"}).status_code == 401
    # formulaire posté depuis un autre site : pas d'en-tête personnalisé
    assert c.post("/depot/envoi", data=form(make_pack()), headers=basic(PAGE_PASSWORD)).status_code == 400
    # la page ne s'ouvre pas avec le jeton Bearer, ni /packs avec le mot de passe de la page
    assert c.post("/packs", data=form(make_pack()), headers=basic(PAGE_PASSWORD)).status_code == 401
    assert world.calls == [] and world.uploads == []


def test_test_pack_download(settings, world):
    import zipfile
    c = page_client(settings, world)
    assert c.get("/depot/pack-de-test.zip").status_code == 401
    res = c.get("/depot/pack-de-test.zip", headers=basic(PAGE_PASSWORD))
    if res.status_code == 500:
        import shutil
        import pytest
        if not shutil.which("ffmpeg"):
            pytest.skip("ffmpeg requis pour générer le pack de test")
    assert res.status_code == 200
    names = zipfile.ZipFile(io.BytesIO(res.data)).namelist()
    assert len(names) == 3 and any(n.endswith("/posts.json") for n in names)
    posts = json.loads(zipfile.ZipFile(io.BytesIO(res.data)).read(next(n for n in names if n.endswith("posts.json"))))
    assert posts["publish"]["mode"] == "draft" and list(posts["posts"]) == ["facebook"]


def test_accounts_page_lists_ids_without_tokens(settings, world):
    from conftest import FakeResponse

    original = world.request

    def request(method, url, **kwargs):
        if url.endswith("/v1/social-accounts"):
            return FakeResponse(200, {"data": [
                {"id": "spc_fb", "platform": "facebook", "username": "Un dernier regard",
                 "status": "connected", "access_token": "JETON-SECRET"},
                {"id": "spc_autre", "platform": "tiktok_business", "username": "udr", "status": "connected"},
            ]})
        return original(method, url, **kwargs)

    world.request = request
    c = page_client(settings, world)
    assert c.get("/depot/comptes").status_code == 401
    text = c.get("/depot/comptes", headers=basic(PAGE_PASSWORD)).get_data(as_text=True)
    assert "spc_fb" in text and "PFM_ACCOUNT_FACEBOOK : déjà en place" in text
    assert "PFM_ACCOUNT_TIKTOK" in text and "JETON-SECRET" not in text


def test_status_page(settings, world, make_pack):
    c = page_client(settings, world)
    pack = make_pack(lambda p: p.update(posts={"facebook": p["posts"]["facebook"]}))
    c.post("/depot/envoi", data=form(pack), headers={**basic(PAGE_PASSWORD), "X-UDR-Depot": "1"})
    assert c.get("/depot/suivi?pack=UDR_test_V1").status_code == 401
    assert c.get("/depot/suivi?pack=../x", headers=basic(PAGE_PASSWORD)).status_code == 400
    text = c.get("/depot/suivi?pack=UDR_test_V1", headers=basic(PAGE_PASSWORD)).get_data(as_text=True)
    assert "Facebook : BROUILLON" in text
