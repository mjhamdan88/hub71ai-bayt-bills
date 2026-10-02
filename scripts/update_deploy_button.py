"""Generate a Portacode button; use --public for the documented raw YAML URL."""

import argparse

from pathlib import Path
from urllib.parse import quote


ROOT = Path(__file__).resolve().parent.parent
README = ROOT / "README.md"
PORTAFILE = ROOT / "portafile.yaml"
PREFIX = "[![Deploy with Portacode]"


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--public", action="store_true", help="Use the public raw GitHub URL after making the repository public")
    args = parser.parse_args()
    yaml_data_url = "data:text/yaml;charset=utf-8," + quote(
        PORTAFILE.read_text(encoding="utf-8"),
        safe="",
    )
    if args.public:
        yaml_data_url = "https://raw.githubusercontent.com/portacode/UniStack/main/portafile.yaml"
    deploy_url = "https://portacode.com/dashboard/?portafile=" + quote(
        yaml_data_url,
        safe="",
    )
    button = (
        "[![Deploy with Portacode]"
        "(https://img.shields.io/badge/Deploy_with-Portacode-176b3a?style=for-the-badge)]"
        f"({deploy_url})"
    )
    lines = README.read_text(encoding="utf-8").splitlines()
    matches = [index for index, line in enumerate(lines) if line.startswith(PREFIX)]
    if len(matches) != 1:
        raise RuntimeError(f"Expected one deploy button in README.md, found {len(matches)}")
    lines[matches[0]] = button
    README.write_text("\n".join(lines) + "\n", encoding="utf-8")


if __name__ == "__main__":
    main()
