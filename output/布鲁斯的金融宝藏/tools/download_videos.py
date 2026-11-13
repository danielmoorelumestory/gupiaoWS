#!/usr/bin/env python3
"""Download the public Douyin videos used in the Bruce_Gold research.

Use the patched yt-dlp environment described in README.md.
"""
import argparse
from pathlib import Path

DEFAULT_URLS = [
    "https://www.douyin.com/video/7689639585425056591",
    "https://www.douyin.com/video/7700469388663999720",
    "https://www.douyin.com/video/7692341302306897984",
    "https://www.douyin.com/video/7690782528969594728",
]


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("urls", nargs="*", help="Public video URLs; defaults to four research videos")
    parser.add_argument(
        "--output", type=Path,
        default=Path(__file__).resolve().parent.parent / "videos",
        help="Directory for videos and metadata",
    )
    args = parser.parse_args()
    try:
        import yt_dlp
    except ImportError:
        parser.exit(2, "Install yt-dlp and apply the bundled fix as described in README.md.\n")
    args.output.mkdir(parents=True, exist_ok=True)
    options = {
        "noplaylist": True,
        "socket_timeout": 20,
        "retries": 1,
        "writeinfojson": True,
        "writesubtitles": True,
        "writeautomaticsub": True,
        "subtitleslangs": ["all"],
        "outtmpl": str(args.output / "%(id)s.%(ext)s"),
        "overwrites": False,
        "ignoreerrors": True,
        "noprogress": True,
    }
    with yt_dlp.YoutubeDL(options) as downloader:
        return downloader.download(args.urls or DEFAULT_URLS)


if __name__ == "__main__":
    raise SystemExit(main())
