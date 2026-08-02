"""Command-line interface for swatch color extraction."""

from __future__ import annotations

import argparse

from .pipeline import run_color_extraction

## Build CLI and a resumable pipeline to manage data w/out mutating the original input files
def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Extract RGB, HEX, and CIE Lab colors from Ulta swatch images."
    )
    parser.add_argument("--input", required=True, help="Prepared variant CSV.")
    parser.add_argument("--output", required=True, help="Output swatch_colors.csv.")
    parser.add_argument("--failures", default=None, help="Optional failure-log path.")
    parser.add_argument("--manifest", default=None, help="Optional manifest path.")
    parser.add_argument("--limit", type=int, default=None, help="Process only the first N rows.")
    parser.add_argument(
        "--request-delay",
        type=float,
        default=0.05,
        help="Seconds between image requests.",
    )
    parser.add_argument(
        "--checkpoint-interval",
        type=int,
        default=25,
        help="Write resumable output every N attempted images.",
    )
    parser.add_argument(
        "--no-resume",
        action="store_true",
        help="Refuse to use an existing output file.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    try:
        result = run_color_extraction(
            args.input, # load input rows
            args.output,
            failures_path=args.failures,
            manifest_path=args.manifest,
            limit=args.limit,
            request_delay_seconds=args.request_delay,
            checkpoint_interval=args.checkpoint_interval,
            resume=not args.no_resume,
        )
    except (OSError, TypeError, ValueError) as error:
        raise SystemExit(str(error)) from error

    print(
        f"Color extraction {result['status']}: "
        f"{result['completed_row_count']}/{result['input_row_count']} rows"
    )
    print(f"Output: {result['output_path']}")
    return 0 if result["status"] == "complete" else 1


if __name__ == "__main__":
    raise SystemExit(main())
