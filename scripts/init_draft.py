"""Create a blank line card (rosters.json) for a new fantasy draft season."""

import json
import re
from pathlib import Path

import click
import structlog

log = structlog.get_logger()

SEASON_PATTERN = re.compile(r"^(?P<y1>\d{2}|\d{4})(?:[-/](?P<y2>\d{2}|\d{4}))?$")


def parse_season_start_year(season: str) -> int:
    """Parse a season string like '2026', '26-27', or '2026-2027' into its start year."""
    match = SEASON_PATTERN.match(season.strip())
    if not match:
        raise click.BadParameter(
            f"'{season}' isn't a recognized season format "
            "(expected e.g. 2026, 26-27, or 2026-2027)."
        )
    y1_text, y2_text = match.group("y1"), match.group("y2")
    start_year = int(y1_text) + 2000 if len(y1_text) == 2 else int(y1_text)
    if y2_text is not None:
        end_year = int(y2_text) + 2000 if len(y2_text) == 2 else int(y2_text)
        if end_year != start_year + 1:
            raise click.BadParameter(f"'{season}' spans non-consecutive years.")
    return start_year


def slugify(drafter_name: str) -> str:
    """Turn a drafter's display name into a lowercase, alphanumeric team id."""
    return re.sub(r"[^a-z0-9]", "", drafter_name.lower())


def build_blank_line_card(drafter_names: tuple[str, ...]) -> dict:
    """Build an empty rosters.json structure, one team per drafter, in draft order."""
    teams = [
        {
            "id": slugify(name),
            "name": name,
            "roster": {"F": [], "D": [], "T": []},
            "replaced": [],
        }
        for name in drafter_names
    ]
    return {"teams": teams, "draftLog": []}


@click.command()
@click.argument("drafter_names", nargs=-1, required=True)
@click.option("--season", required=True, help="Season to cover: 2026, 26-27, or 2026-2027.")
@click.option(
    "--out-file",
    default="rosters.json",
    show_default=True,
    help="Filename to create inside the season's data directory.",
)
@click.option(
    "--data-dir",
    default="data",
    show_default=True,
    type=click.Path(file_okay=False),
    help="Root directory holding per-season data folders.",
)
@click.option(
    "--force",
    is_flag=True,
    help="Overwrite the output file if it already exists.",
)
def main(
    drafter_names: tuple[str, ...],
    season: str,
    out_file: str,
    data_dir: str,
    force: bool,
) -> None:
    """Write a blank line card for a new draft, one team per DRAFTER_NAMES, in draft order."""
    start_year = parse_season_start_year(season)
    season_dir = Path(data_dir) / f"{start_year}-{start_year + 1}"
    out_path = season_dir / out_file

    if out_path.exists() and not force:
        raise click.ClickException(f"{out_path} already exists — pass --force to overwrite.")

    season_dir.mkdir(parents=True, exist_ok=True)
    line_card = build_blank_line_card(drafter_names)
    out_path.write_text(json.dumps(line_card, indent=1) + "\n")
    log.info("wrote blank line card", path=str(out_path), teams=len(drafter_names))


if __name__ == "__main__":
    main()
