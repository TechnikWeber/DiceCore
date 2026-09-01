"""
The command line.

Everything here is also reachable from the web UI — the CLI exists for the two situations a
browser is wrong for: the first five minutes on a fresh box (`doctor`, `synth`), and
training on a PC that has no reason to run a server.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from . import __version__
from .config import Settings, config_path, state_dir


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="dicecore", description="Read real dice with a camera.")
    parser.add_argument("--version", action="version", version=f"dicecore {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    serve = sub.add_parser("serve", help="run the API and the setup page")
    serve.add_argument("--host", default=None)
    serve.add_argument("--port", type=int, default=None)

    roll = sub.add_parser("roll", help="read the dice once and print the result")
    roll.add_argument("--json", action="store_true", help="print the full result as JSON")
    roll.add_argument("--no-wait", action="store_true", help="do not wait for the dice to settle")

    synth = sub.add_parser("synth", help="write synthetic rolls so the simulator has something")
    synth.add_argument("folder", nargs="?", default=None)
    synth.add_argument("--count", type=int, default=12)
    synth.add_argument("--kinds", default="d6", help="comma separated, e.g. d6,d20")

    sub.add_parser("doctor", help="what this machine can do, and what the camera says")
    sub.add_parser("sets", help="list dataset sets")

    module = sub.add_parser("camera-module", help="write a CSI module into config.txt (needs root)")
    module.add_argument("id", help="module id, or 'list'")
    module.add_argument("--overlay", default="", help="overlay name when id is 'custom'")

    train = sub.add_parser("train", help="train a model from a dataset set (needs PyTorch)")
    train.add_argument("set_id")
    train.add_argument("--epochs", type=int, default=30)
    train.add_argument("--out", default=None)

    args = parser.parse_args(argv)
    settings, complaints = Settings.load()
    for complaint in complaints:
        print(f"warning: {complaint}", file=sys.stderr)

    return globals()[f"_cmd_{args.command.replace('-', '_')}"](args, settings)


def _cmd_serve(args, settings: Settings) -> int:
    try:
        import uvicorn
    except ImportError:
        print("The server needs `pip install 'dicecore[server]'`.", file=sys.stderr)
        return 1
    from .server import create_app

    host = args.host or settings.server.host
    port = args.port or settings.server.port
    print(f"DiceCore {__version__} — setup page on http://{host}:{port}/")
    print(f"config: {config_path()}   state: {state_dir()}")
    uvicorn.run(create_app(settings), host=host, port=port, log_level="info")
    return 0


def _cmd_roll(args, settings: Settings) -> int:
    from .capture import CaptureError
    from .engine import EngineError
    from .reader import Reader

    reader = Reader(settings)
    try:
        result = reader.read(wait_for_still=not args.no_wait)
    except (CaptureError, EngineError) as exc:
        print(exc, file=sys.stderr)
        return 2
    if args.json:
        print(json.dumps(result.to_json(), indent=2))
    else:
        print(f"{result.notation}   total {result.total}   ({result.engine}, {result.took_ms} ms)")
        for warning in result.warnings:
            print(f"  ! {warning}")
    return 0


def _cmd_synth(args, settings: Settings) -> int:
    from .synth import write_scenes

    folder = Path(args.folder) if args.folder else settings.frames_dir
    kinds = tuple(k.strip() for k in args.kinds.split(",") if k.strip())
    written = write_scenes(folder, count=args.count, kinds=kinds)
    print(f"{len(written)} scenes in {folder}")
    print(f"Point capture.source at 'folder' and capture.folder at {folder} to read them.")
    return 0


def _cmd_doctor(args, settings: Settings) -> int:
    from .system import boot_config, diagnostics

    caps = diagnostics.probe()
    print(f"machine        {caps.pi or caps.machine}")
    print(f"read pips      {'yes' if caps.can_run_classic else 'no'}  (numpy + OpenCV)")
    print(f"run a model    {'yes' if caps.can_run_model else 'no'}  (onnxruntime)")
    print(f"train a model  {'yes' if caps.can_train else 'no'}  (PyTorch)")
    report = diagnostics.detect_cameras()
    print(f"camera tool    {report.tool or 'none'}")
    print(f"CSI cameras    {', '.join(report.csi) or 'none'}")
    print(f"video nodes    {', '.join(report.video_nodes) or 'none'}")
    boot_state, path = boot_config.read_boot_state()
    print(f"boot config    {path or 'not a Pi'} → module {boot_config.module_id_for(boot_state)}")
    for line in [report.problem, boot_config.explain_boot_config(boot_state, len(report.csi))]:
        if line:
            print(f"  ! {line}")
    for line in caps.advice():
        print(f"  · {line}")
    return 0


def _cmd_sets(args, settings: Settings) -> int:
    from .dataset import DatasetStore
    from .training.data import readiness

    store = DatasetStore(settings.dataset_dir)
    sets = store.list_sets()
    if not sets:
        print(f"No dataset sets in {settings.dataset_dir}. Create one in the web UI.")
        return 0
    for record in sets:
        state = readiness(store, record.id)
        print(f"{record.id:<28} {state.total:>5} dice  {len(state.classes):>3} faces  "
              f"{'ready' if state.ready else 'not ready'}")
    return 0


def _cmd_camera_module(args, settings: Settings) -> int:
    from .system import boot_config

    if args.id == "list":
        for module in boot_config.CSI_MODULES:
            print(f"{module.id:<20} {module.label}")
        return 0
    module = boot_config.module_by_id(args.id)
    if module is None:
        print(f"Unknown module {args.id!r}. Try `dicecore camera-module list`.", file=sys.stderr)
        return 2
    overlay = args.overlay if args.id == "custom" else module.overlay
    if args.id == "custom" and not boot_config.valid_overlay_name(overlay or ""):
        print(f"{overlay!r} is not a valid overlay name.", file=sys.stderr)
        return 2
    try:
        path = boot_config.write_camera_module(overlay)
    except PermissionError:
        print("Writing config.txt needs root — try again with sudo.", file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError) as exc:
        print(exc, file=sys.stderr)
        return 1
    settings.capture.csi_module = module.id
    if module.tuning_file:
        settings.capture.tuning_file = module.tuning_file
    settings.save()
    print(f"{path} updated. Reboot for it to take effect.")
    return 0


def _cmd_train(args, settings: Settings) -> int:
    from .dataset import DatasetStore
    from .training.data import readiness
    from .training.trainer import torch_available, train_model

    ok, why = torch_available()
    if not ok:
        print(why, file=sys.stderr)
        return 1
    store = DatasetStore(settings.dataset_dir)
    state = readiness(store, args.set_id)
    for reason in state.reasons:
        print(f"  ! {reason}")
    if not state.ready:
        return 2
    out = Path(args.out) if args.out else settings.models_dir / args.set_id

    def progress(fields: dict) -> None:
        if fields.get("stage") == "training":
            print(f"  epoch {fields['epoch']:>3}/{fields['epochs']}  "
                  f"loss {fields['loss']:.4f}  accuracy {fields['accuracy']:.1%}")
        elif fields.get("message"):
            print(f"  {fields['message']}")

    meta = train_model(store, args.set_id, out, epochs=args.epochs, progress=progress)
    print(f"{out} written — {meta.accuracy:.1%} on validation, {meta.samples} dice, "
          f"{len(meta.classes)} faces.")
    print("Point the engine at it: set engine.mode=model in the UI, or in the config file.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
