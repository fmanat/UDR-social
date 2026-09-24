"""Garde-fous sur le dépôt : pas de secret, workflow n8n cohérent."""

import json
import re
import subprocess

from conftest import ROOT

WORKFLOW = json.loads((ROOT / "workflows" / "udr-publish.json").read_text(encoding="utf-8"))


def test_workflow_chain_and_recipient():
    names = {n["name"]: n for n in WORKFLOW["nodes"]}
    form = names["Formulaire de dépôt"]
    labels = [f["fieldLabel"] for f in form["parameters"]["formFields"]["values"]]
    assert labels == ["posts_json", "video_vertical", "video_horizontal"]
    http = names["Service de publication (Railway)"]
    sent = [p["inputDataFieldName"] for p in http["parameters"]["bodyParameters"]["parameters"]]
    assert sent == labels
    assert http["parameters"]["authentication"] == "genericCredentialType"
    for node in ("Rapport par e-mail", "Alerte : service injoignable"):
        assert names[node]["parameters"]["toEmail"] == "jean@undernierregard.fr"
    assert WORKFLOW["connections"]["Service de publication (Railway)"]["main"][1][0]["node"] == \
        "Alerte : service injoignable"


def test_workflow_carries_no_credentials_or_secrets():
    text = json.dumps(WORKFLOW)
    assert '"credentials"' not in text
    assert not re.search(r"Bearer\s+\w{8,}", text)


def test_no_env_file_tracked_and_no_secret_like_values():
    tracked = subprocess.run(["git", "ls-files"], cwd=ROOT, capture_output=True, text=True).stdout.split()
    assert ".env" not in tracked
    for line in (ROOT / ".env.example").read_text().splitlines():
        if "=" in line and not line.startswith("#"):
            key, value = line.split("=", 1)
            assert value in ("", "0", "5", "dl8itl9nw", "udr-publish", "sha1", "./data"), key
