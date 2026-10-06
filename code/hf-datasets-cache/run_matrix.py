"""Fresh-process runner; retains failures and never overwrites a run or case."""
import argparse
import datetime as dt
import hashlib
import json
import os
from pathlib import Path
import subprocess
import sys
import time

CONDITIONS = ["defaults", "hf-home", "datasets-only", "hub-only", "split", "xdg", "home-over-xdg",
              "transformers-legacy", "datasets-argument", "config-argument", "import-before",
              "import-bound-both", "import-bound-hub", "import-lazy-root", "cleanup", "saved-dataset", "relocation"]


def copy_manifest(root):
    return [{"path": str(p.relative_to(root)), "bytes": p.stat().st_size,
             "symlink": os.readlink(p) if p.is_symlink() else None,
             "sha256": hashlib.file_digest(p.open("rb"), "sha256").hexdigest()}
            for p in sorted(root.rglob("*")) if p.is_file()]


def new_environment(root, condition):
    env = {"PATH": str(Path(sys.executable).parent) + ":/usr/bin:/bin", "LANG": "C.UTF-8",
           "HOME": str(root / "home"), "TMPDIR": str(root / "tmp"), "PYTHONUNBUFFERED": "1",
           "HF_HUB_DISABLE_TELEMETRY": "1", "HF_HUB_DISABLE_IMPLICIT_TOKEN": "1",
           "HF_HUB_DISABLE_UPDATE_CHECK": "1", "HF_HUB_DISABLE_PROGRESS_BARS": "1",
           "HF_HUB_DOWNLOAD_TIMEOUT": "45", "HF_HUB_ETAG_TIMEOUT": "45", "NO_COLOR": "1"}
    for key in ("HOME", "TMPDIR"):
        Path(env[key]).mkdir(parents=True)
    if condition in ("hf-home", "split", "home-over-xdg", "datasets-argument", "config-argument",
                      "cleanup", "saved-dataset", "relocation"):
        env["HF_HOME"] = str(root / "hf")
    if condition in ("datasets-only", "split", "datasets-argument", "saved-dataset"):
        env["HF_DATASETS_CACHE"] = str(root / "arrow")
    if condition in ("hub-only", "split"):
        env["HF_HUB_CACHE"] = str(root / "hub")
    if condition in ("xdg", "home-over-xdg"):
        env["XDG_CACHE_HOME"] = str(root / "xdg")
    if condition == "transformers-legacy":
        env["TRANSFORMERS_CACHE"] = str(root / "legacy")
    if condition.startswith("import-"):
        env["HF_HOME"] = str(root / "early")
    return env


def execute(argv, env):
    start = time.perf_counter()
    record = {"argv": argv, "started_utc": dt.datetime.now(dt.timezone.utc).isoformat()}
    try:
        done = subprocess.run(argv, env=env, text=True, capture_output=True, timeout=240)
        record.update(exit_code=done.returncode, stdout=done.stdout, stderr=done.stderr, timeout=False)
        if done.returncode == 0:
            record["result"] = json.loads(done.stdout)
    except subprocess.TimeoutExpired as exc:
        record.update(exit_code=None, stdout=str(exc.stdout), stderr=str(exc.stderr), timeout=True)
    record["wall_seconds"] = time.perf_counter() - start
    return record


parser = argparse.ArgumentParser()
parser.add_argument("--run", required=True)
parser.add_argument("--output", type=Path, required=True)
parser.add_argument("--repeat", type=int, default=3)
parser.add_argument("--conditions", nargs="+", default=CONDITIONS)
parser.add_argument("--runtime", type=Path)
parser.add_argument("--lock", type=Path)
parser.add_argument("--design", type=Path)
args = parser.parse_args()
base = Path("/opt/vramlab-hf7/runs") / args.run
if base.exists() or args.output.exists():
    raise SystemExit("Refusing to overwrite existing run")
base.mkdir(parents=True)
args.output.mkdir(parents=True)
probe = Path(__file__).with_name("probe_cache.py")
manifest = {"run": args.run, "conditions": args.conditions, "repeat": args.repeat,
            "runner_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
            "probe_sha256": hashlib.sha256(probe.read_bytes()).hexdigest(), "records": []}
manifest["bindings"] = {key: {"path": str(path), "sha256": hashlib.sha256(path.read_bytes()).hexdigest()}
                        for key, path in (("runtime", args.runtime), ("lock", args.lock), ("design", args.design)) if path}
(args.output / "plan.json").write_text(json.dumps(manifest, indent=2) + "\n")
failed = 0
for repetition in range(1, args.repeat + 1):
    for condition in args.conditions:
        root = base / f"{condition}-r{repetition:02}"
        if hashlib.sha256(probe.read_bytes()).hexdigest() != manifest["probe_sha256"]:
            raise RuntimeError("Probe changed during run")
        root.mkdir()
        env = new_environment(root, condition)
        argv = [sys.executable, str(probe), "--root", str(root), "--condition", condition]
        rec = execute(argv, env)
        rec.update(condition=condition, repetition=repetition)
        rec["probe_sha256"] = hashlib.sha256(probe.read_bytes()).hexdigest()
        if condition == "relocation" and rec["exit_code"] == 0:
            copied = root / "copied-hf"
            rec["copy_source_manifest"] = copy_manifest(root / "hf")
            copy_result = subprocess.run(["cp", "-a", str(root / "hf"), str(copied)], text=True, capture_output=True)
            rec["copy"] = {"argv": ["cp", "-a", str(root / "hf"), str(copied)], "exit_code": copy_result.returncode,
                           "stdout": copy_result.stdout, "stderr": copy_result.stderr}
            if copy_result.returncode == 0:
                rec["copy_destination_manifest"] = copy_manifest(copied)
                retained = root / "retained-original-hf"
                (root / "hf").rename(retained)
                rec["original_relocated_before_offline"] = {"original_absent": not (root / "hf").exists(),
                                                           "retained_path": str(retained)}
                offline_env = dict(env, HF_HOME=str(copied), HF_HUB_OFFLINE="1", HF_DATASETS_OFFLINE="1")
                rec["offline"] = execute([*argv, "--mode", "offline"], offline_env)
        name = f"{condition}-r{repetition:02}.json"
        content = json.dumps(rec, ensure_ascii=False, indent=2) + "\n"
        (args.output / name).write_text(content, encoding="utf-8")
        good = rec["exit_code"] == 0 and (condition != "relocation" or
            (rec.get("copy", {}).get("exit_code") == 0 and rec.get("offline", {}).get("exit_code") == 0))
        failed += not good
        manifest["records"].append({"file": name, "sha256": hashlib.sha256(content.encode()).hexdigest(), "ok": good})
        print(f"{name}: {'EXECUTED' if good else 'ERROR'} ({rec['wall_seconds']:.2f}s)", flush=True)
        (args.output / "status.json").write_text(json.dumps({"completed": len(manifest["records"]), "failed": failed,
            "total": args.repeat * len(args.conditions), "last": name}, indent=2) + "\n")
manifest["failed"] = failed
(args.output / "manifest.json").write_text(json.dumps(manifest, indent=2) + "\n")
raise SystemExit(1 if failed else 0)
