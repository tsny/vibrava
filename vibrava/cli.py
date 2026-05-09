import argparse
import os
import sys
from pathlib import Path

import PIL.Image
if not hasattr(PIL.Image, "ANTIALIAS"):
    PIL.Image.ANTIALIAS = PIL.Image.LANCZOS


def main() -> None:
    parser = argparse.ArgumentParser(prog="vibrava")
    sub = parser.add_subparsers(dest="command")

    gen = sub.add_parser("generate", help="Generate a video from a script")
    gen.add_argument("script", type=Path, help="Path to script JSON file")
    gen.add_argument(
        "--config", type=Path, default=Path("config.toml"), help="Path to config.toml"
    )
    gen.add_argument(
        "--output", type=Path, default=None,
        help="Output file path (overrides script filename + timestamp; also VIBRAVA_OUTPUT env var)",
    )

    res = sub.add_parser("resolve", help="Match images to a script and write a .resolved.json")
    res.add_argument("script", type=Path, help="Path to script JSON file")
    res.add_argument(
        "--config", type=Path, default=Path("config.toml"), help="Path to config.toml"
    )

    args = parser.parse_args()

    if args.command == "generate":
        from vibrava.config import load as load_config
        from vibrava.pipeline import run

        config = load_config(args.config)
        output = args.output or (Path(os.environ["VIBRAVA_OUTPUT"]) if "VIBRAVA_OUTPUT" in os.environ else None)
        run(args.script, config, output_path=output)
    elif args.command == "resolve":
        from vibrava.config import load as load_config
        from vibrava.pipeline import resolve

        config = load_config(args.config)
        resolve(args.script, config)
    else:
        parser.print_help()
        sys.exit(1)


if __name__ == "__main__":
    main()
