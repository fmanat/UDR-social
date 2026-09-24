"""Journal local des envois (JSONL, ajout seul) et verrou par pack.

Chaque ligne est un événement horodaté. L'état d'un pack se reconstruit en
relisant ses événements : c'est la mémoire qui empêche un second envoi.
Sur Railway, le dossier de données doit être un volume persistant.
"""

from __future__ import annotations

import contextlib
import fcntl
import json
import os
from datetime import datetime, timezone
from pathlib import Path
from typing import Iterator


def utcnow() -> str:
    return datetime.now(timezone.utc).isoformat(timespec="seconds")


class Journal:
    def __init__(self, path: Path, locks_dir: Path):
        self.path = path
        self.locks_dir = locks_dir
        path.parent.mkdir(parents=True, exist_ok=True)
        locks_dir.mkdir(parents=True, exist_ok=True)

    def append(self, pack_id: str, event: str, **fields) -> dict:
        record = {"ts": utcnow(), "pack_id": pack_id, "event": event, **fields}
        line = json.dumps(record, ensure_ascii=False) + "\n"
        with self.path.open("a", encoding="utf-8") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            fh.write(line)
            fh.flush()
            os.fsync(fh.fileno())
            fcntl.flock(fh, fcntl.LOCK_UN)
        return record

    def events(self, pack_id: str) -> list[dict]:
        if not self.path.is_file():
            return []
        out = []
        with self.path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                try:
                    record = json.loads(line)
                except json.JSONDecodeError:
                    continue
                if record.get("pack_id") == pack_id:
                    out.append(record)
        return out

    def network_state(self, pack_id: str) -> dict[str, dict]:
        """Dernier post connu par réseau (création, adoption, mise à jour, promotion)."""
        state: dict[str, dict] = {}
        for record in self.events(pack_id):
            if record["event"] == "post":
                state[record["network"]] = record
            elif record["event"] == "result" and record["network"] in state:
                state[record["network"]] = {**state[record["network"]], "last_result": record}
        return state

    def uploads(self, pack_id: str) -> dict[tuple[str, str], dict]:
        """Uploads Cloudinary déjà faits, par (emplacement, sha256)."""
        return {(r["slot"], r["sha256"]): r for r in self.events(pack_id) if r["event"] == "upload"}

    @contextlib.contextmanager
    def lock(self, pack_id: str) -> Iterator[None]:
        """Verrou exclusif : deux dépôts simultanés du même pack s'exécutent l'un après l'autre."""
        lock_path = self.locks_dir / f"{pack_id}.lock"
        with lock_path.open("w") as fh:
            fcntl.flock(fh, fcntl.LOCK_EX)
            try:
                yield
            finally:
                fcntl.flock(fh, fcntl.LOCK_UN)
