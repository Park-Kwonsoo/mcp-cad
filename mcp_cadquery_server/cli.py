import sys
from typing import Sequence

from .server import run_stdio


def main(argv: Sequence[str] | None = None) -> None:
    args = list(sys.argv[1:] if argv is None else argv)
    if args == ["--mode", "stdio"] or args == ["--mode=stdio"]:
        args = []

    if args:
        if args in (["-h"], ["--help"]):
            print("usage: mcp-cadquery")
            print()
            print("Start the CadQuery MCP server over stdio.")
            return
        raise SystemExit(f"unsupported arguments: {' '.join(args)}")

    run_stdio()
