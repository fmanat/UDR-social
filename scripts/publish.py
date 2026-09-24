#!/usr/bin/env python3
"""Publication d'un pack Un dernier regard via Post For Me.

Exemples :
  python scripts/publish.py validate packs/UDR_test_V1       # vérifie sans rien envoyer
  python scripts/publish.py run packs/UDR_test_V1 --dry-run  # montre ce qui serait envoyé
  python scripts/publish.py run packs/UDR_test_V1            # dépôt (draft ou live selon posts.json)
  python scripts/publish.py check UDR_test_V1                # suivi : publié / en erreur / à vérifier
  python scripts/publish.py accounts                         # comptes Post For Me connectés (sans jetons)

Codes de sortie : 0 tout va bien, 1 au moins un réseau en erreur, 2 pack refusé.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from udr_publish.pipeline import Publisher  # noqa: E402
from udr_publish.settings import load_settings  # noqa: E402
from udr_publish.validate import validate_pack  # noqa: E402


def _print(rep: dict, as_json: bool) -> None:
    if as_json:
        print(json.dumps(rep, ensure_ascii=False, indent=2))
    else:
        print(rep["report_text"], end="")


def _exit_code(rep: dict) -> int:
    if rep.get("refused"):
        return 2
    return 0 if rep.get("ok") else 1


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    parser.add_argument("--env-file", type=Path, help="fichier .env (défaut : .env à la racine du dépôt)")
    sub = parser.add_subparsers(dest="command", required=True)

    p_run = sub.add_parser("run", help="valider et envoyer un pack")
    p_run.add_argument("pack_dir", type=Path)
    p_run.add_argument("--dry-run", action="store_true", help="valider et afficher les requêtes, sans rien envoyer")
    p_run.add_argument("--json", action="store_true", help="rapport au format JSON")

    p_val = sub.add_parser("validate", help="valider un pack sans rien envoyer")
    p_val.add_argument("pack_dir", type=Path)

    p_check = sub.add_parser("check", help="suivre les posts d'un pack déjà déposé")
    p_check.add_argument("pack_id")
    p_check.add_argument("--json", action="store_true")

    sub.add_parser("accounts", help="lister les comptes Post For Me connectés (id, réseau, nom)")

    args = parser.parse_args(argv)
    settings = load_settings(args.env_file)

    if args.command == "validate":
        result = validate_pack(args.pack_dir, settings)
        for warning in result.warnings:
            print(f"avertissement : {warning}")
        if not result.ok:
            print("PACK REFUSÉ :")
            for error in result.errors:
                print(f"  - {error}")
            return 2
        pack = result.pack
        print(f"Pack {pack.pack_id} valide — mode {pack.mode} — réseaux : "
              + ", ".join(p.network.label for p in pack.plans))
        return 0

    publisher = Publisher(settings)
    if args.command == "accounts":
        for account in publisher.pfm.list_accounts():
            print(f"{account['platform']:<16} {account['id']:<32} {account.get('username') or ''} ({account['status']})")
        return 0
    if args.command == "check":
        rep = publisher.check(args.pack_id)
        _print(rep, args.json)
        return _exit_code(rep)

    rep = publisher.run(args.pack_dir, dry_run=args.dry_run)
    _print(rep, args.json)
    if args.dry_run and not args.json and not rep.get("refused"):
        print("Requêtes qui seraient envoyées à Post For Me :")
        for entry in rep["networks"]:
            print(f"--- {entry['label']}")
            print(json.dumps(entry["payload"], ensure_ascii=False, indent=2))
    return _exit_code(rep)


if __name__ == "__main__":
    sys.exit(main())
