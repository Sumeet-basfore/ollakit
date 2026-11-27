"""ollakit ask: local RAG over a notes directory with Ollama embeddings."""

import argparse
import hashlib
import json
import math
import sys
from pathlib import Path

from . import client
from .config import cache_dir, load as load_config

TEXT_EXTS = {
    ".md", ".txt", ".py", ".js", ".ts", ".json", ".toml", ".yaml", ".yml",
    ".sh", ".rs", ".go", ".java", ".c", ".h", ".cpp", ".html", ".css",
    ".csv", ".ini", ".cfg", ".log",
}
SKIP_DIRS = {".git", "node_modules", ".venv", "__pycache__", "dist", "build"}
CHUNK_SIZE = 800
CHUNK_OVERLAP = 100
TOP_K = 5

ANSWER_PROMPT = (
    "Answer the question using ONLY the context below. If the context does not "
    "contain the answer, say so plainly. Be concise.\n\n"
    "Context:\n{context}\n\nQuestion: {question}"
)


def build_args(argv: list[str]):
    parser = argparse.ArgumentParser(prog="ollakit ask")
    parser.add_argument("question", nargs="?")
    parser.add_argument("--index", metavar="DIR", help="directory to index")
    parser.add_argument("--reindex", action="store_true")
    parser.add_argument("--chat", action="store_true")
    parser.add_argument("--model")
    parser.add_argument("--embed-model")
    parser.add_argument("--k", type=int, default=TOP_K, help="chunks to retrieve")
    return parser.parse_args(argv)


def chunk_text(text: str, size: int = CHUNK_SIZE, overlap: int = CHUNK_OVERLAP) -> list[str]:
    chunks = []
    start = 0
    while start < len(text):
        end = min(start + size, len(text))
        # prefer breaking on a newline inside the final 20% of the chunk
        nl = text.rfind("\n", start + int(size * 0.8), end)
        if nl != -1:
            end = nl + 1
        chunks.append(text[start:end].strip())
        if end >= len(text):
            break
        start = end - overlap
    return [c for c in chunks if c]


def collect_files(directory: Path) -> list[Path]:
    files = []
    for path in sorted(directory.rglob("*")):
        if not path.is_file():
            continue
        if any(part in SKIP_DIRS or part.startswith(".") for part in path.relative_to(directory).parts):
            continue
        if path.suffix.lower() in TEXT_EXTS:
            files.append(path)
    return files


def index_path_for(directory: Path) -> Path:
    digest = hashlib.sha1(str(directory.resolve()).encode()).hexdigest()[:12]
    return cache_dir() / f"ask-index-{digest}.json"


def _file_state(files: list[Path], root: Path) -> dict:
    return {
        str(f.relative_to(root)): {"mtime": f.stat().st_mtime, "size": f.stat().st_size}
        for f in files
    }


def build_index(root: Path, embed_model: str, path: Path, force: bool = False) -> dict:
    files = [f for f in collect_files(root) if f.resolve() != path.resolve()]
    if path.exists() and not force:
        old = json.loads(path.read_text())
        if old.get("model") == embed_model and old.get("root") == str(root):
            state = _file_state(files, root)
            keep = []
            for c in old["chunks"]:
                p = c["path"]
                if p in state and old["files"].get(p) and (
                    state[p]["mtime"] == old["files"][p]["mtime"]
                    and state[p]["size"] == old["files"][p]["size"]
                ):
                    keep.append(c)
            to_embed = [p for p in state if p not in {c["path"] for c in keep}]
        else:
            keep, to_embed = [], [str(f.relative_to(root)) for f in files]
    else:
        keep, to_embed = [], [str(f.relative_to(root)) for f in files]

    new_chunks = list(keep)
    for rel in to_embed:
        text = (root / rel).read_text(errors="replace")
        pieces = chunk_text(text)
        if not pieces:
            continue
        vecs = client.embed(embed_model, pieces)
        new_chunks.extend(
            {"path": rel, "text": piece, "vec": vec} for piece, vec in zip(pieces, vecs)
        )

    index = {
        "model": embed_model,
        "root": str(root),
        "files": _file_state(files, root),
        "chunks": new_chunks,
    }
    path.write_text(json.dumps(index))
    print(f"[ollakit] indexed {len(to_embed)} file(s), {len(new_chunks)} chunks -> {path}")
    return index


def _cosine(a: list[float], b: list[float]) -> float:
    dot = sum(x * y for x, y in zip(a, b))
    na = math.sqrt(sum(x * x for x in a))
    nb = math.sqrt(sum(x * x for x in b))
    if na == 0 or nb == 0:
        return 0.0
    return dot / (na * nb)


def retrieve(question: str, index: dict, embed_model: str, k: int = TOP_K, _qv=None) -> list[dict]:
    qv = _qv if _qv is not None else client.embed(embed_model, [question])[0]
    scored = sorted(
        ((_cosine(qv, c["vec"]), c) for c in index["chunks"]),
        key=lambda pair: pair[0],
        reverse=True,
    )
    return [c for _, c in scored[:k] if _ > 0]


def build_prompt(question: str, chunks: list[dict]) -> str:
    context = "\n\n---\n\n".join(
        f"[{c['path']}]\n{c['text']}" for c in chunks
    )
    return ANSWER_PROMPT.format(context=context, question=question)


def print_answer(answer: str, sources: list) -> None:
    print(answer)
    if sources:
        print("\nSources:")
        for path, n_chunks in sources:
            print(f"  {path}  ({n_chunks} chunk{'s' if n_chunks != 1 else ''})")


def answer_question(question: str, index: dict, embed_model: str, chat_model: str, k: int) -> None:
    chunks = retrieve(question, index, embed_model, k)
    if not chunks:
        print("The index is empty — nothing matches. Try --reindex.")
        return
    sources = []
    seen: dict[str, int] = {}
    for c in chunks:
        seen[c["path"]] = seen.get(c["path"], 0) + 1
    sources = list(seen.items())
    prompt = build_prompt(question, chunks)
    raw = client.chat(chat_model, [{"role": "user", "content": prompt}])
    print_answer(raw.strip(), sources)


def run(args) -> int:
    cfg = load_config()
    index_dir = Path(args.index or cfg["notes_dir"] or "").expanduser()
    if not index_dir or not index_dir.is_dir():
        raise SystemExit(
            "ask: no notes directory. Pass --index <dir> or set notes_dir in "
            "~/.config/ollakit/config.json"
        )
    embed_model = client.pick_embed_model(args.embed_model)
    chat_model = client.pick_chat_model(args.model)
    ipath = index_path_for(index_dir)
    if args.reindex or not ipath.exists():
        index = build_index(index_dir, embed_model, ipath, force=args.reindex)
    else:
        index = json.loads(ipath.read_text())
        if index.get("model") != embed_model or index.get("root") != str(index_dir):
            index = build_index(index_dir, embed_model, ipath, force=True)

    if args.chat:
        print(f"Chatting over {index_dir} (empty answer = stop). Ctrl-C or 'exit' to quit.")
        while True:
            try:
                question = input("\nyou> ").strip()
            except (EOFError, KeyboardInterrupt):
                break
            if not question or question.lower() in ("exit", "quit"):
                break
            answer_question(question, index, embed_model, chat_model, args.k)
        return 0

    if not args.question:
        raise SystemExit("ask: give a question, or use --chat for a session")
    answer_question(args.question, index, embed_model, chat_model, args.k)
    return 0


if __name__ == "__main__":
    sys.exit(run(build_args(sys.argv[1:])))
