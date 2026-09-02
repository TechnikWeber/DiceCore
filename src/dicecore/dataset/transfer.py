"""
Carrying a dataset between machines.

The case this exists for: your friend owns the d20s. He collects a few hundred labelled
throws of his own dice on his own tower, sends you a file, and you train one model that
knows his dice and yours. Without this, a set is stuck on the machine that collected it.

A plain zip of exactly what is on disk — the frames as JPEG, one JSON label per frame, and
the set's own description. No archive format of our own, because the point of the boring
on-disk layout was that anything could read it, and a zip of it keeps that true: unzip it
and you can look at every picture and every label with the tools you already have.
"""

from __future__ import annotations

import io
import json
import zipfile
from pathlib import Path
from typing import Any

from .store import DatasetStore, Sample

#: Written into the archive so an import can tell a DiceCore set from any other zip.
MANIFEST = "dicecore-set.json"
VERSION = 1

#: Refuse an import bigger than this. A set is a few hundred small JPEGs; anything much
#: larger is either not a dataset or is going to fill a Pi's card.
MAX_BYTES = 512 * 1024 * 1024


def export_set(store: DatasetStore, set_id: str) -> bytes:
    """The whole set as a zip, in memory. A few hundred frames is tens of megabytes."""
    directory = store.set_dir(set_id)
    meta = json.loads((directory / "set.json").read_text())
    samples = list(store.iter_samples(set_id))

    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
        archive.writestr(MANIFEST, json.dumps({
            "version": VERSION,
            "set": meta,
            "d10_style": store.d10_style,
            "frames": len(samples),
            "dice": sum(len(s.dice) for s in samples),
            "confirmed": sum(1 for s in samples for d in s.dice if d.confirmed),
        }, indent=2))
        archive.writestr("set.json", json.dumps(meta, indent=2))
        for sample in samples:
            frame = store.frame_path(set_id, sample.id)
            if frame.is_file():
                archive.write(frame, f"frames/{sample.id}.jpg")
            archive.writestr(f"labels/{sample.id}.json",
                             json.dumps(sample.to_json(), indent=2))
    return buffer.getvalue()


def describe(payload: bytes) -> dict[str, Any]:
    """What is in this archive, without unpacking it anywhere."""
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        if MANIFEST not in archive.namelist():
            raise ValueError("That zip is not a DiceCore set — no manifest inside.")
        manifest = json.loads(archive.read(MANIFEST))
    if int(manifest.get("version", 0)) != VERSION:
        raise ValueError("That set was written by a different version of DiceCore "
                         f"({manifest.get('version')}).")
    return manifest


def import_set(store: DatasetStore, payload: bytes, name: str = "") -> dict[str, Any]:
    """
    Unpack an exported set into a new one of its own.

    Always a *new* set, never merged into an existing one: two people's dice under two
    people's lamps are two sets, and quietly mixing them is how a model ends up learning the
    average of two setups and being worse at both. Training can take several sets at once,
    so keeping them apart costs nothing.
    """
    if len(payload) > MAX_BYTES:
        raise ValueError(f"That archive is {len(payload) // (1024 * 1024)} MB, over the "
                         f"{MAX_BYTES // (1024 * 1024)} MB limit.")
    manifest = describe(payload)
    original = manifest.get("set") or {}
    record = store.create_set(name or original.get("name") or "imported set",
                             note=original.get("note", ""))
    directory = store.set_dir(record.id)

    frames = labels = 0
    with zipfile.ZipFile(io.BytesIO(payload)) as archive:
        for entry in archive.infolist():
            if entry.is_dir():
                continue
            # Never trust a path out of an archive: "../../etc/cron.d/x" is a real attack
            # and a zip is exactly where it comes from.
            stem = Path(entry.filename).name
            if entry.filename.startswith("frames/") and stem.endswith(".jpg"):
                (directory / "frames" / stem).write_bytes(archive.read(entry))
                frames += 1
            elif entry.filename.startswith("labels/") and stem.endswith(".json"):
                try:
                    sample = Sample.from_json(json.loads(archive.read(entry)))
                except (ValueError, KeyError, TypeError):
                    continue      # one bad label must not lose the rest of the set
                (directory / "labels" / f"{sample.id}.json").write_text(
                    json.dumps(sample.to_json(), indent=2))
                labels += 1

    return {"set": record.to_json(), "frames": frames, "labels": labels,
            "manifest": manifest}
