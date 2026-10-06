"""Observe real HF source/config/Arrow files. No expected-placement assertions here."""
import argparse
import gc
import hashlib
import json
import os
from pathlib import Path
import socket
import subprocess
import sys

DATASET = "lhoestq/demo1"
DATASET_REV = "87ecf163bedca9d80598b528940a9c4f99e14c11"
MODEL = "hf-internal-testing/tiny-random-bert"
MODEL_REV = "f171d7baecaf37b5da5a3616d8833b9969753535"


def sha(path):
    return hashlib.file_digest(Path(path).open("rb"), "sha256").hexdigest()


def inventory(root):
    found = []
    for path in sorted(root.rglob("*")):
        if path.is_symlink():
            found.append({"path": str(path), "type": "symlink", "target": os.readlink(path),
                          "resolved": str(path.resolve()), "bytes": path.stat().st_size,
                          "sha256": sha(path)})
        elif path.is_file():
            st = path.stat()
            found.append({"path": str(path), "type": "file", "bytes": st.st_size,
                          "allocated_bytes": st.st_blocks * 512, "sha256": sha(path)})
    return found


def rows_digest(dataset):
    digest = hashlib.sha256()
    for row in dataset:
        digest.update(json.dumps(row, sort_keys=True, ensure_ascii=False, separators=(",", ":")).encode())
        digest.update(b"\n")
    return digest.hexdigest()


def add_length(row):
    return {"review_length": len(row["review"])}


def add_upper(row):
    return {"upper_review": row["review"].upper()}


def describe(dataset):
    return {"rows": len(dataset), "columns": dataset.column_names,
            "row_sha256": rows_digest(dataset), "cache_files": dataset.cache_files,
            "fingerprint": dataset._fingerprint}


def cache_state(dataset):
    return [{"filename": item["filename"], "sha256": sha(item["filename"]),
             "bytes": Path(item["filename"]).stat().st_size,
             "mtime_ns": Path(item["filename"]).stat().st_mtime_ns}
            for item in dataset.cache_files]


def run_cli(*args):
    proc = subprocess.run([str(Path(sys.executable).parent / "hf"), *args],
                          text=True, capture_output=True, timeout=90)
    return {"argv": ["hf", *args], "exit_code": proc.returncode,
            "stdout": proc.stdout, "stderr": proc.stderr}


parser = argparse.ArgumentParser()
parser.add_argument("--root", type=Path, required=True)
parser.add_argument("--condition", required=True)
parser.add_argument("--mode", choices=["normal", "offline"], default="normal")
args = parser.parse_args()
root = args.root.resolve()
condition = args.condition
assert str(root).startswith("/opt/vramlab-hf7/runs/"), "Only dedicated lab paths allowed"

# Imports themselves are part of the experiment; do not hoist these.
import_trace = []
import_state_before_change = None
import_state_start = {m: m in sys.modules for m in ("huggingface_hub.constants", "datasets.config", "transformers")}
if condition.startswith("import-"):
    if condition == "import-bound-both":
        from huggingface_hub import constants as early_hub
        import datasets as early_datasets
        import_trace.extend(["from huggingface_hub import constants", "import datasets"])
    elif condition == "import-bound-hub":
        from huggingface_hub import constants as early_hub
        import_trace.append("from huggingface_hub import constants")
    elif condition == "import-lazy-root":
        import huggingface_hub
        import_trace.append("import huggingface_hub")
    import_state_before_change = {m: m in sys.modules for m in
                                 ("huggingface_hub.constants", "datasets.config", "transformers")}
    os.environ["HF_HOME"] = str(root / "late")
    import_trace.append("set HF_HOME=late")

network_attempts = []
offline_controls = {}
if args.mode == "offline":
    def deny_connect(self, address):
        network_attempts.append(str(address))
        raise RuntimeError("clean offline verification forbids network connections")
    socket.socket.connect = deny_connect
    socket.socket.connect_ex = deny_connect
    try:
        with socket.socket() as test_socket:
            test_socket.connect(("192.0.2.1", 443))
    except RuntimeError as exc:
        offline_controls["socket_guard"] = {"blocked": True, "message": str(exc),
                                             "attempts": list(network_attempts)}
    assert offline_controls.get("socket_guard", {}).get("blocked"), "Network guard not functioning"
    network_attempts.clear()

from huggingface_hub import constants as hub_constants
import datasets
from datasets import Dataset, load_dataset, load_from_disk
from transformers import AutoConfig
if args.mode == "offline":
    from huggingface_hub import hf_hub_download
    from huggingface_hub.errors import LocalEntryNotFoundError
    try:
        hf_hub_download(MODEL, "config.json", revision=MODEL_REV,
                        cache_dir=str(root / "offline-empty"), local_files_only=True, token=False)
    except LocalEntryNotFoundError as exc:
        offline_controls["empty_cache_miss"] = {"failed_as_expected": True, "exception": type(exc).__name__}
    assert offline_controls.get("empty_cache_miss", {}).get("failed_as_expected"), "Empty cache unexpectedly passed"
import_trace.extend(["from huggingface_hub import constants", "import datasets", "from transformers import AutoConfig"])

configuration_args = {"revision": MODEL_REV, "token": False}
load_args = {"revision": DATASET_REV, "split": "train", "token": False}
if condition == "config-argument":
    configuration_args["cache_dir"] = str(root / "explicit-model")
if condition == "datasets-argument":
    load_args["cache_dir"] = str(root / "explicit-arrow")
if args.mode == "offline":
    configuration_args["local_files_only"] = True

config = AutoConfig.from_pretrained(MODEL, **configuration_args)
base = load_dataset(DATASET, **load_args)
mapped = base.map(add_length, load_from_cache_file=True)
reuse_before = cache_state(mapped)
mapped_again = base.map(add_length, load_from_cache_file=True)
reuse_after = cache_state(mapped_again)
record = {
    "condition": condition, "mode": args.mode, "root": str(root),
    "python": sys.version, "versions": {"datasets": datasets.__version__,
        "huggingface_hub": __import__("huggingface_hub").__version__,
        "transformers": __import__("transformers").__version__},
    "inputs": {"dataset": DATASET, "dataset_revision": DATASET_REV,
               "model": MODEL, "model_revision": MODEL_REV},
    "import_trace": import_trace,
    "import_state_start": import_state_start,
    "import_state_before_change": import_state_before_change,
    "import_state_after": {m: m in sys.modules for m in ("huggingface_hub.constants", "datasets.config", "transformers")},
    "environment": {k: os.environ[k] for k in ["HOME", "XDG_CACHE_HOME", "HF_HOME", "HF_HUB_CACHE",
        "HF_DATASETS_CACHE", "TRANSFORMERS_CACHE", "HF_HUB_OFFLINE", "HF_DATASETS_OFFLINE"] if k in os.environ},
    "constants": {"HF_HOME": hub_constants.HF_HOME, "HF_HUB_CACHE": hub_constants.HF_HUB_CACHE,
                  "HF_DATASETS_CACHE": str(datasets.config.HF_DATASETS_CACHE)},
    "model_config_class": type(config).__name__, "model_type": config.model_type,
    "torch_installed": __import__("importlib.util").util.find_spec("torch") is not None,
    "base": describe(base), "mapped": describe(mapped),
    "map_reuse": {"before": reuse_before, "after": reuse_after,
                  "mapped_again": describe(mapped_again)},
    "after_load_inventory": inventory(root),
}

if condition == "cleanup":
    abandoned_files = [x["filename"] for x in mapped.cache_files]
    del mapped_again
    del mapped
    gc.collect()
    active = base.map(add_upper, load_from_cache_file=True)
    before = inventory(root)
    active_before = describe(active)
    removed_count = active.cleanup_cache_files()
    after_arrow = inventory(root)
    listing = run_cli("cache", "ls")
    dry_run = run_cli("cache", "rm", "dataset/" + DATASET, "--dry-run")
    deletion = run_cli("cache", "rm", "dataset/" + DATASET, "--yes")
    if listing["exit_code"] or dry_run["exit_code"] or deletion["exit_code"]:
        raise RuntimeError(json.dumps({"listing": listing, "dry_run": dry_run, "deletion": deletion}))
    record["cleanup"] = {"abandoned_files": abandoned_files, "removed_count": removed_count,
        "before": before, "after_arrow": after_arrow, "after_hub": inventory(root),
        "listing": listing, "dry_run": dry_run, "deletion": deletion, "active_before": active_before,
        "active_after": describe(active), "base_after": describe(base)}

if condition == "saved-dataset":
    exported = root / "export"
    base.save_to_disk(str(exported))
    saved = load_from_disk(str(exported))
    before = inventory(root)
    mapped_saved = saved.map(add_length, load_from_cache_file=True)
    memory = Dataset.from_dict({"review": ["one", "two"]}).map(add_length)
    explicit = root / "arrow" / "explicit-map.arrow"
    explicit.parent.mkdir(exist_ok=True)
    redirected = saved.map(add_length, cache_file_name=str(explicit))
    record["saved_dataset"] = {"before_map": before, "after_map": inventory(root),
        "saved": describe(saved), "saved_mapped": describe(mapped_saved),
        "in_memory_mapped": describe(memory), "explicit_map": describe(redirected)}

record["network_connect_attempts"] = network_attempts
record["offline_controls"] = offline_controls
print(json.dumps(record, ensure_ascii=False, sort_keys=True))
