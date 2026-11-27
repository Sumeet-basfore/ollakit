"""ollakit organize: sort files into folders with a local model, reversibly.

Safety rules (from skills/file-organizer): never delete, dry-run by default,
confirm before applying, journal every move for undo, preserve mtimes
(shutil.move does), resolve collisions instead of overwriting.
"""

import datetime
import json
import shutil
import sys
from pathlib import Path

from . import client
from .config import cache_dir

TAXONOMY = ["Documents", "Images", "Videos", "Archives", "Code", "Music", "Other"]
BATCH_SIZE = 30

SYSTEM_PROMPT = (
    "You classify files into folders. Input is a JSON array of files. Output ONLY a JSON "
    "array with EXACTLY ONE entry per input file, in the same order: "
    '[{"file": str, "category": one of ["Documents", "Images", "Videos", "Archives", '
    '"Code", "Music", "Other"], "name": str|null}] where "name" is an optional cleaner '
    "filename (keep the extension). Example input [\"a.jpg\",\"b.zip\"] → output "
    '[{"file":"a.jpg","category":"Images","name":null},{"file":"b.zip","category":"Archives","name":null}]. '
    "Infer category from the file extension and name. No prose."
)


def build_args(argv: list[str]):
    import argparse

    parser = argparse.ArgumentParser(prog="ollakit organize")
    parser.add_argument("directory", nargs="?")
    parser.add_argument("--recursive", action="store_true")
    parser.add_argument("--apply", action="store_true")
    parser.add_argument("--undo", metavar="JOURNAL", help="revert a previous apply")
    parser.add_argument("--model")
    parser.add_argument("--yes", action="store_true", help="skip the confirmation prompt")
    return parser.parse_args(argv)


def scan(directory: Path, recursive: bool = False) -> list[dict]:
    pattern = directory.rglob("*") if recursive else directory.glob("*")
    entries = []
    for path in sorted(pattern):
        if not path.is_file() or path.name.startswith("."):
            continue
        stat = path.stat()
        entries.append(
            {"name": path.name, "path": path, "size": stat.st_size, "mtime": stat.st_mtime}
        )
    return entries


def classify(entries: list[dict], model: str) -> list[dict]:
    results = []
    for i in range(0, len(entries), BATCH_SIZE):
        batch = [
            {"name": e["name"], "size": e["size"], "mtime": datetime.datetime.fromtimestamp(
                e["mtime"]).strftime("%Y-%m-%d")}
            for e in entries[i : i + BATCH_SIZE]
        ]
        raw = client.chat(
            model,
            [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": json.dumps(batch)},
            ],
            json_mode=True,
        )
        data = client.parse_json(raw)
        if isinstance(data, dict):
            data = [data]
        if isinstance(data, list):
            results.extend(d for d in data if isinstance(d, dict))
        # Small models are unreliable with batch JSON: they return one object,
        # or one object with duplicate "file" keys. Recover what we can, then
        # classify any missing files one-by-one, which is reliable.
        if len(results) < len(batch):
            import re

            for snippet in re.findall(r"\{[^{}]*\}", raw):
                try:
                    obj = json.loads(snippet)
                except json.JSONDecodeError:
                    continue
                if isinstance(obj, dict) and obj.get("file") not in {
                    r.get("file") for r in results
                }:
                    results.append(obj)
        seen = {r.get("file") for r in results}
        for e in entries[i : i + BATCH_SIZE]:
            if e["name"] in seen:
                continue
            single = json.dumps(
                [{"name": e["name"], "size": e["size"], "mtime": datetime.datetime.fromtimestamp(
                    e["mtime"]).strftime("%Y-%m-%d")}]
            )
            raw_single = client.chat(
                model,
                [
                    {"role": "system", "content": SYSTEM_PROMPT},
                    {"role": "user", "content": single},
                ],
                json_mode=True,
            )
            try:
                obj = client.parse_json(raw_single)
            except json.JSONDecodeError:
                continue
            if isinstance(obj, dict):
                obj = [obj]
            if isinstance(obj, list):
                results.extend(d for d in obj if isinstance(d, dict) and d.get("file"))
    return results


def unique_dst(dst: Path) -> Path:
    if not dst.exists():
        return dst
    stem, suffix = dst.stem, dst.suffix
    for n in range(2, 1000):
        candidate = dst.with_name(f"{stem} ({n}){suffix}")
        if not candidate.exists():
            return candidate
    raise SystemExit(f"Cannot find a free name for {dst}")


def valid_new_name(name: str | None, src: Path) -> str | None:
    if not name or name == src.name:
        return None
    name = name.strip()
    if "/" in name or "\\" in name or name.startswith("."):
        return None
    return name if Path(name).suffix else name + src.suffix


def plan_for(directory: Path, model: str, recursive: bool = False) -> list:
    entries = scan(directory, recursive)
    if not entries:
        return []
    classified = classify(entries, model)
    by_name = {c.get("file"): c for c in classified if isinstance(c, dict)}

    class Move:
        def __init__(self, src, dst):
            self.src, self.dst = src, dst

    moves = []
    for entry in entries:
        c = by_name.get(entry["name"], {})
        category = c.get("category")
        if category not in TAXONOMY:
            category = "Other"
        new_name = valid_new_name(c.get("name"), entry["path"]) or entry["name"]
        moves.append(
            Move(entry["path"], unique_dst(directory / category / new_name))
        )
    return moves


def render_plan(moves: list) -> None:
    if not moves:
        print("Nothing to organize.")
        return
    for m in moves:
        rel_dst = m.dst.relative_to(m.src.parent)
        print(f"{m.src.name:40} -> {rel_dst}")
    print(f"\n{len(moves)} file(s) would move.")


def journal_path() -> Path:
    stamp = datetime.datetime.now().strftime("%Y%m%d-%H%M%S")
    return cache_dir() / f"organize-{stamp}.json"


def apply(moves: list) -> Path:
    jp = journal_path()
    journal = []
    for m in moves:
        # dst uniqueness was checked at plan time; re-check in case the
        # directory changed between the plan and the confirmation.
        if m.dst.exists():
            m.dst = unique_dst(m.dst)
        m.dst.parent.mkdir(parents=True, exist_ok=True)
        shutil.move(str(m.src), str(m.dst))  # preserves mtime
        journal.append({"src": str(m.src), "dst": str(m.dst)})
    jp.write_text(json.dumps(journal, indent=2))
    print(f"\nMoved {len(journal)} file(s). Undo with: ollakit organize --undo {jp}")
    return jp


def undo(jp: Path) -> None:
    journal = json.loads(Path(jp).read_text())
    restored = 0
    for move in reversed(journal):
        src, dst = Path(move["src"]), Path(move["dst"])
        if dst.exists():
            src.parent.mkdir(parents=True, exist_ok=True)
            shutil.move(str(dst), str(src))
            restored += 1
        elif src.exists():
            restored += 1  # already undone
    print(f"Restored {restored}/{len(journal)} file(s).")


def confirm(moves: list, assume_yes: bool) -> bool:
    if assume_yes:
        return True
    answer = input(f"\nApply {len(moves)} move(s)? [y/N] ")
    return answer.strip().lower() in ("y", "yes")


def run(args) -> int:
    if args.undo:
        undo(args.undo)
        return 0
    if not args.directory:
        raise SystemExit("organize: a directory is required (or pass --undo <journal>)")
    directory = Path(args.directory).expanduser().resolve()
    if not directory.is_dir():
        raise SystemExit(f"Not a directory: {directory}")
    model = client.pick_chat_model(args.model)
    moves = plan_for(directory, model, args.recursive)
    render_plan(moves)
    if not moves:
        return 0
    if not args.apply:
        print("\nDry run: nothing changed. Pass --apply to execute.")
        return 0
    if not confirm(moves, args.yes):
        print("Aborted; nothing changed.")
        return 0
    apply(moves)
    return 0


if __name__ == "__main__":
    sys.exit(run(build_args(sys.argv[1:])))
