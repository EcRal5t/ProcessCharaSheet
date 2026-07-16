# encoding: utf-8
"""Generate a safe, incremental i_area_list import from AreaList.md.

The old exporter truncated i_area_list and let AUTO_INCREMENT recreate every
ID. That is no longer safe because area IDs are referenced by common_entries,
common_releases and common_sync_queue.

Rules:
- Rows with an empty sheetname are notes/placeholders and are not imported.
- emit == "1" means is_visible = 0; every other emit value means visible.
- sort_order follows the Markdown row order in steps of 10.
- Existing rows are updated by sheetname; omitted rows are left untouched.
- A changed sheetname is never silently treated as a new location. The SQL
  reports RENAME_REQUIRED and gives the safe PHP command to run.
"""

from __future__ import annotations

import argparse
import csv
import io
import re
from dataclasses import dataclass
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Dict, List


IDENTIFIER_RE = re.compile(r"^[A-Za-z][A-Za-z0-9_]*$")
COLOR_RE = re.compile(r"^#[0-9A-Fa-f]{6}$")
REQUIRED_COLUMNS = [
    "longitude",
    "latitude",
    "first",
    "second",
    "third",
    "sheetname",
    "color",
    "emit",
]


@dataclass(frozen=True)
class AreaRow:
    longitude: str
    latitude: str
    first: str
    second: str
    third: str
    sheetname: str
    color: str
    is_visible: int
    sort_order: int


def sql_text(value: str) -> str:
    """Return readable UTF-8 SQL, using CHAR() only for unsafe characters."""
    parts: List[str] = []
    plain: List[str] = []

    def flush_plain() -> None:
        if plain:
            parts.append("_utf8mb4'{}'".format("".join(plain)))
            plain.clear()

    for char in str(value):
        codepoint = ord(char)
        if char in ("'", "\\") or codepoint < 32 or codepoint == 127:
            flush_plain()
            parts.append("CHAR({})".format(codepoint))
        else:
            plain.append(char)
    flush_plain()

    if not parts:
        return "_utf8mb4''"
    if len(parts) == 1:
        return parts[0]
    return "CONCAT({})".format(", ".join(parts))


def normalize_number(value: str, field: str, minimum: Decimal, maximum: Decimal) -> str:
    value = value.strip() or "0"
    try:
        number = Decimal(value)
    except InvalidOperation as error:
        raise ValueError("{} is not a number: {!r}".format(field, value)) from error
    if not minimum <= number <= maximum:
        raise ValueError("{} is outside {}..{}: {}".format(field, minimum, maximum, value))
    return format(number, "f")


def parse_markdown(markdown_table: str) -> List[AreaRow]:
    if not markdown_table.strip():
        raise ValueError("Markdown input is empty")

    raw_rows = list(csv.reader(io.StringIO(markdown_table.strip()), delimiter="|"))
    rows = []
    for raw in raw_rows:
        cells = [cell.strip() for cell in raw]
        if cells and cells[0] == "":
            cells = cells[1:]
        if cells and cells[-1] == "":
            cells = cells[:-1]
        if any(cells):
            rows.append(cells)
    if len(rows) < 2:
        raise ValueError("Markdown table has no data rows")

    headers = rows[0]
    missing = [column for column in REQUIRED_COLUMNS if column not in headers]
    if missing:
        raise ValueError("Missing Markdown columns: {}".format(", ".join(missing)))

    result: List[AreaRow] = []
    seen_sheets: Dict[str, int] = {}
    seen_places: Dict[tuple, int] = {}
    for line_number, cells in enumerate(rows[2:], start=3):
        if len(cells) != len(headers):
            raise ValueError(
                "Markdown line {} has {} cells; expected {}".format(
                    line_number, len(cells), len(headers)
                )
            )
        values = dict(zip(headers, cells))
        sheetname = values["sheetname"].strip()
        if not sheetname:
            continue
        if len(sheetname) > 64 or not IDENTIFIER_RE.fullmatch(sheetname):
            raise ValueError("Invalid sheetname on line {}: {!r}".format(line_number, sheetname))

        first = values["first"].strip()
        second = values["second"].strip()
        third = values["third"].strip()
        place = (first, second, third)
        if sheetname in seen_sheets:
            raise ValueError(
                "Duplicate sheetname {!r} on lines {} and {}".format(
                    sheetname, seen_sheets[sheetname], line_number
                )
            )
        if place in seen_places:
            raise ValueError(
                "Duplicate location {!r} on lines {} and {}".format(
                    place, seen_places[place], line_number
                )
            )

        color = values["color"].strip()
        if not COLOR_RE.fullmatch(color):
            raise ValueError("Invalid #RRGGBB color on line {}: {!r}".format(line_number, color))
        longitude = normalize_number(values["longitude"], "longitude", Decimal("-180"), Decimal("180"))
        latitude = normalize_number(values["latitude"], "latitude", Decimal("-90"), Decimal("90"))

        seen_sheets[sheetname] = line_number
        seen_places[place] = line_number
        result.append(
            AreaRow(
                longitude=longitude,
                latitude=latitude,
                first=first,
                second=second,
                third=third,
                sheetname=sheetname,
                color=color,
                is_visible=0 if values["emit"].strip() == "1" else 1,
                sort_order=(len(result) + 1) * 10,
            )
        )

    if not result:
        raise ValueError("No rows with a sheetname were found")
    return result


def markdown_to_sql(markdown_table: str, table_name: str = "i_area_list") -> str:
    if not IDENTIFIER_RE.fullmatch(table_name):
        raise ValueError("Invalid SQL table name: {!r}".format(table_name))
    areas = parse_markdown(markdown_table)
    values = []
    for area in areas:
        values.append(
            "({}, {}, {}, {}, {}, {}, {}, {}, {})".format(
                area.longitude,
                area.latitude,
                sql_text(area.first),
                sql_text(area.second),
                sql_text(area.third),
                sql_text(area.sheetname),
                sql_text(area.color),
                area.is_visible,
                area.sort_order,
            )
        )

    table = "`{}`".format(table_name)
    return """-- Incremental area catalogue import; existing area IDs are preserved.
-- Requires common_entries_schema.php v3 (is_visible, sort_order, unique sheetname).
DROP TEMPORARY TABLE IF EXISTS `_jyutdict_area_import`;
CREATE TEMPORARY TABLE `_jyutdict_area_import` (
  `longitude` DOUBLE NOT NULL,
  `latitude` DOUBLE NOT NULL,
  `first` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `second` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `third` VARCHAR(64) CHARACTER SET utf8mb4 COLLATE utf8mb4_bin NOT NULL,
  `sheetname` VARCHAR(64) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `color` CHAR(7) CHARACTER SET ascii COLLATE ascii_bin NOT NULL,
  `is_visible` TINYINT(1) NOT NULL,
  `sort_order` INT UNSIGNED NOT NULL,
  PRIMARY KEY (`sheetname`)
) ENGINE=InnoDB;

INSERT INTO `_jyutdict_area_import`
(`longitude`, `latitude`, `first`, `second`, `third`, `sheetname`, `color`, `is_visible`, `sort_order`) VALUES
{values};

START TRANSACTION;
UPDATE {table} AS `area`
JOIN `_jyutdict_area_import` AS `incoming` ON `incoming`.`sheetname` = `area`.`sheetname`
SET `area`.`longitude` = `incoming`.`longitude`,
    `area`.`latitude` = `incoming`.`latitude`,
    `area`.`first` = `incoming`.`first`,
    `area`.`second` = `incoming`.`second`,
    `area`.`third` = `incoming`.`third`,
    `area`.`color` = `incoming`.`color`,
    `area`.`is_visible` = `incoming`.`is_visible`,
    `area`.`sort_order` = `incoming`.`sort_order`;
SET @jyutdict_area_updated = ROW_COUNT();

INSERT INTO {table}
(`longitude`, `latitude`, `first`, `second`, `third`, `sheetname`, `color`, `is_visible`, `sort_order`)
SELECT `incoming`.`longitude`, `incoming`.`latitude`, `incoming`.`first`, `incoming`.`second`,
       `incoming`.`third`, `incoming`.`sheetname`, `incoming`.`color`,
       `incoming`.`is_visible`, `incoming`.`sort_order`
FROM `_jyutdict_area_import` AS `incoming`
WHERE NOT EXISTS (
  SELECT 1 FROM {table} AS `by_sheet` WHERE `by_sheet`.`sheetname` = `incoming`.`sheetname`
)
AND NOT EXISTS (
  SELECT 1 FROM {table} AS `by_place`
  WHERE `by_place`.`first` = `incoming`.`first`
    AND `by_place`.`second` = `incoming`.`second`
    AND `by_place`.`third` = `incoming`.`third`
)
ORDER BY `incoming`.`sort_order`;
SET @jyutdict_area_inserted = ROW_COUNT();
COMMIT;

SELECT
  IF(COUNT(*) = 0, 'AREA_LIST_OK', 'AREA_LIST_RENAME_REQUIRED') AS `jyutdict_area_list_status`,
  @jyutdict_area_updated AS `changed_existing_rows`,
  @jyutdict_area_inserted AS `inserted_rows`,
  COUNT(*) AS `rename_required_rows`
FROM `_jyutdict_area_import` AS `incoming`
JOIN {table} AS `actual`
  ON `actual`.`first` = `incoming`.`first`
 AND `actual`.`second` = `incoming`.`second`
 AND `actual`.`third` = `incoming`.`third`
WHERE `actual`.`sheetname` <> `incoming`.`sheetname`;

SELECT
  `actual`.`id` AS `area_id`,
  `actual`.`first`, `actual`.`second`, `actual`.`third`,
  `actual`.`sheetname` AS `current_sheetname`,
  `incoming`.`sheetname` AS `requested_sheetname`,
  CONCAT(
    'php api/scripts/rename_location_table.php --from=', `actual`.`sheetname`,
    ' --to=', `incoming`.`sheetname`, ' --apply'
  ) AS `required_command`
FROM `_jyutdict_area_import` AS `incoming`
JOIN {table} AS `actual`
  ON `actual`.`first` = `incoming`.`first`
 AND `actual`.`second` = `incoming`.`second`
 AND `actual`.`third` = `incoming`.`third`
WHERE `actual`.`sheetname` <> `incoming`.`sheetname`
ORDER BY `incoming`.`sort_order`;

DROP TEMPORARY TABLE `_jyutdict_area_import`;
""".format(table=table, values=",\n".join(values))


def main() -> None:
    base = Path(__file__).resolve().parent
    parser = argparse.ArgumentParser(description="Generate incremental i_area_list SQL")
    parser.add_argument("--input", type=Path, default=base / "AreaList.md")
    parser.add_argument("--output", type=Path, default=base / "IAreaList.sql")
    parser.add_argument("--table", default="i_area_list")
    args = parser.parse_args()

    markdown = args.input.read_text(encoding="utf-8")
    areas = parse_markdown(markdown)
    args.output.write_text(markdown_to_sql(markdown, args.table), encoding="utf-8")
    visible = sum(area.is_visible for area in areas)
    print(
        "Generated {}: {} locations ({} visible, {} hidden)".format(
            args.output, len(areas), visible, len(areas) - visible
        )
    )


if __name__ == "__main__":
    main()
