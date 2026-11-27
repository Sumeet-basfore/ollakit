"""ollakit CLI: review | ask | organize.

Each module owns its own argparse parser (build_args) so flags can't drift
between the CLI and direct module calls.
"""

import sys

from . import __version__


def main(argv: list[str] | None = None) -> int:
    argv = list(sys.argv[1:] if argv is None else argv)
    if argv and argv[0] in ("-V", "--version"):
        print(f"ollakit {__version__}")
        return 0
    if not argv or argv[0] in ("-h", "--help"):
        print(
            "usage: ollakit {review,ask,organize} ...\n"
            "\n"
            "  review    review a git diff with a local model\n"
            "  ask       ask questions over an indexed notes directory\n"
            "  organize  organize files in a directory (dry-run by default)\n"
        )
        return 0 if argv else 2

    command, rest = argv[0], argv[1:]
    if command == "review":
        from . import review

        return review.run(review.build_args(rest))
    if command == "ask":
        from . import ask

        return ask.run(ask.build_args(rest))
    if command == "organize":
        from . import organize

        return organize.run(organize.build_args(rest))
    print(f"unknown command: {command}", file=sys.stderr)
    return 2


if __name__ == "__main__":
    sys.exit(main())
