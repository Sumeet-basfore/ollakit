"""ollakit CLI: review | ask | organize."""

import argparse
import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(prog="ollakit", description="Local Ollama toolkit")
    parser.add_argument("--version", action="version", version=f"ollakit {__version__}")
    sub = parser.add_subparsers(dest="command", required=True)

    p_review = sub.add_parser("review", help="review a git diff with a local model")
    p_review.add_argument("--staged", action="store_true", help="review staged changes (default)")
    p_review.add_argument("--branch", metavar="REF", help="review diff from REF to HEAD")
    p_review.add_argument("--model", help="chat model override")
    p_review.add_argument("--json", action="store_true", dest="as_json", help="emit raw JSON findings")
    p_review.add_argument("--install-hook", action="store_true", help="write a pre-push git hook")

    p_ask = sub.add_parser("ask", help="ask questions over an indexed notes directory")
    p_ask.add_argument("question", nargs="?", help="question to answer")
    p_ask.add_argument("--index", metavar="DIR", help="directory to index (default from config)")
    p_ask.add_argument("--reindex", action="store_true", help="rebuild the index")
    p_ask.add_argument("--chat", action="store_true", help="interactive session")
    p_ask.add_argument("--model", help="chat model override")
    p_ask.add_argument("--embed-model", help="embedding model override")

    p_org = sub.add_parser("organize", help="organize files in a directory (dry-run by default)")
    p_org.add_argument("directory", help="directory to organize")
    p_org.add_argument("--recursive", action="store_true", help="recurse into subdirectories")
    p_org.add_argument("--apply", action="store_true", help="execute the plan (default is dry-run)")
    p_org.add_argument("--undo", action="store_true", help="revert the last organize apply")
    p_org.add_argument("--model", help="chat model override")

    args = parser.parse_args(argv)

    if args.command == "review":
        from . import review

        return review.run(args)
    if args.command == "ask":
        from . import ask

        return ask.run(args)
    if args.command == "organize":
        from . import organize

        return organize.run(args)
    return 2


if __name__ == "__main__":
    sys.exit(main())
