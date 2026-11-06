# Modified work (2026): Python adaptation of TNO-MST/siso-entity-type.
# Original copyright 2025 TNO; Apache-2.0. See LICENSE and NOTICE.
"""SISO-REF-010 entity-type XML extraction, ported from TNO's Apache-2.0 parser.

This is the entity-type subset selected by the upstream parser, not a general
SISO-REF-010 schema validator. Other enumeration and bitfield tables are ignored.
"""

from __future__ import annotations

import json
import re
import xml.etree.ElementTree as ET
from pathlib import Path

from .catalog import SisoEnumsData
from .model import create_key

DEFAULT_QUALIFIED = False
DEFAULT_DELIMITER = " / "
# Kept as provenance: upstream declares this but never filters deprecated rows.
DEFAULT_DEPRECATED = False


class ParseError(ValueError):
    """Malformed XML or an invalid entity-type record."""


def _tag(element: ET.Element) -> str:
    return element.tag.rsplit("}", 1)[-1]


def _children(element: ET.Element, tag: str) -> list[ET.Element]:
    return [child for child in element if _tag(child) == tag]


def _integer(element: ET.Element, name: str) -> int:
    value = element.get(name)
    if value is None or re.fullmatch(r"[0-9]+", value.strip()) is None:
        raise ParseError(f"<{_tag(element)}> requires an unsigned decimal {name!r}, got {value!r}")
    return int(value)


def _description(element: ET.Element) -> str:
    value = element.get("description")
    if value is None:
        raise ParseError(f"<{_tag(element)}> is missing a description")
    return value


def _applicability(value: str | None, part_index: int) -> list[int]:
    """Follow upstream's comma-separated range behavior (not a full grammar)."""
    result: list[int] = []
    if not value:
        return result
    for part in value.split(","):
        field = part.split(".")[part_index] if "." in part else part
        bounds: list[int] = []
        for bound in field.split("-"):
            try:
                bounds.append(int(bound))
            except ValueError:
                bounds.append(0)  # Upstream '+value || 0', including X wildcards.
        if len(bounds) == 1:
            result.append(bounds[0])
        else:
            result.extend(range(bounds[0], bounds[1]))
            result.append(bounds[1])
    return result


class SisoEnumsParser:
    def __init__(
        self, root: ET.Element, *, qualified: bool = DEFAULT_QUALIFIED, delimiter: str = DEFAULT_DELIMITER
    ) -> None:
        if _tag(root) != "ebv":
            raise ParseError("Expected an SISO-REF-010 <ebv> root element")
        self._root = root
        self.qualified = qualified
        self.delimiter = delimiter
        self._countries: dict[int, str] = {}
        self._kinds: dict[int, str] = {}
        self._domains: dict[int, str] = {}
        self._categories: dict[int, str] = {}
        self._subcategories: dict[int, str] = {}
        self._parse()

    @classmethod
    def from_string(
        cls, xml_string: str, *, qualified: bool = False, delimiter: str = " / "
    ) -> SisoEnumsParser:
        if re.search(r"<!\s*(?:DOCTYPE|ENTITY)\b", xml_string, re.IGNORECASE):
            raise ParseError("DTD and entity declarations are not supported")
        try:
            root = ET.fromstring(xml_string)
        except ET.ParseError as exc:
            raise ParseError(f"Invalid SISO XML: {exc}") from exc
        return cls(root, qualified=qualified, delimiter=delimiter)

    @classmethod
    def from_file(
        cls, path: str | Path, *, qualified: bool = False, delimiter: str = " / "
    ) -> SisoEnumsParser:
        return cls.from_string(
            Path(path).read_text(encoding="utf-8-sig"), qualified=qualified, delimiter=delimiter
        )

    @property
    def title(self) -> str:
        return self._root.get("title", "")

    @property
    def date(self) -> str:
        return self._root.get("date", "")

    @property
    def copyright_notice(self) -> str:
        return "\n".join("".join(child.itertext()).strip() for child in _children(self._root, "copyright"))

    @property
    def country_count(self) -> int:
        return len(self._countries)

    @property
    def kind_count(self) -> int:
        return len(self._kinds)

    @property
    def domain_count(self) -> int:
        return len(self._domains)

    @property
    def category_count(self) -> int:
        return len(self._categories)

    @property
    def subcategory_count(self) -> int:
        return len(self._subcategories)

    def _parse(self) -> None:
        for enum in _children(self._root, "enum"):
            uid = enum.get("uid")
            if uid not in {"7", "8", "14", "29", "472", "478", "479", "600"}:
                continue
            rows = _children(enum, "enumrow")
            # Python handles singleton enum rows too. Upstream's XML conversion
            # produces a scalar for one row, which its array-only guards ignore.
            for row in rows:
                value, description = _integer(row, "value"), _description(row)
                if uid == "29":
                    self._countries[create_key(0, 0, value, 0, 0, 0, 0)] = description
                elif uid == "7":
                    self._kinds[create_key(value, 0, 0, 0, 0, 0, 0)] = description
                else:
                    for kind in _applicability(enum.get("applicability"), 0):
                        if uid in {"8", "14", "600"}:
                            self._domains[create_key(kind, value, 0, 0, 0, 0, 0)] = description
                        else:
                            for domain in _applicability(enum.get("applicability"), 1):
                                self._categories[create_key(kind, domain, 0, value, 0, 0, 0)] = description
        for cet in _children(self._root, "cet"):
            for entity in _children(cet, "entity"):
                prefix = tuple(_integer(entity, name) for name in ("kind", "domain", "country"))
                for category in _children(entity, "category"):
                    self._walk(category, prefix, 3, "")

    def _walk(self, element: ET.Element, prefix: tuple[int, ...], level: int, parent_text: str) -> None:
        fields = (*prefix, _integer(element, "value"))
        description = _description(element)
        if self.qualified and level > 3:
            description = parent_text + self.delimiter + description
        full = (*fields, *((0,) * (7 - len(fields))))
        key = create_key(*full)
        target = self._categories if level == 3 else self._subcategories
        target[key] = description
        if level < 6:
            next_tag = ("subcategory", "specific", "extra")[level - 3]
            for child in _children(element, next_tag):
                self._walk(child, fields, level + 1, description)

    def get_country(self, key: int) -> str | None:
        return self._countries.get(key)

    def get_kind(self, key: int) -> str | None:
        return self._kinds.get(key)

    def get_domain(self, key: int) -> str | None:
        return self._domains.get(key)

    def get_category(self, key: int) -> str | None:
        return self._categories.get(key)

    def get_subcategory(self, key: int) -> str | None:
        return self._subcategories.get(key)

    def to_data(self) -> SisoEnumsData:
        return SisoEnumsData(
            subcategories={str(key): value for key, value in self._subcategories.items()},
            categories={str(key): value for key, value in self._categories.items()},
            countries={str(key): value for key, value in self._countries.items()},
            domains={str(key): value for key, value in self._domains.items()},
        )

    def to_string(self) -> str:
        """Serialize valid XML. Formatting/prefixes are not byte-preserving."""
        return ET.tostring(self._root, encoding="unicode")

    def write_output_files(self, folder: str | Path) -> Path:
        destination = Path(folder)
        destination.mkdir(parents=True, exist_ok=True)
        path = destination / "siso-enums.json"
        path.write_text(
            json.dumps(self.to_data(), ensure_ascii=False, separators=(",", ":")), encoding="utf-8"
        )
        return path

    countryCount = country_count
    kindCount = kind_count
    domainCount = domain_count
    categoryCount = category_count
    subcategoryCount = subcategory_count
    getCountry = get_country
    getKind = get_kind
    getDomain = get_domain
    getCategory = get_category
    getSubcategory = get_subcategory
    toString = to_string
    writeOutputFiles = write_output_files


class SisoEnumsFactory:
    """Explicit typed entry points for XML parsing and output."""

    @staticmethod
    def create_from_string(
        xml_string: str, *, qualified: bool = False, delimiter: str = " / "
    ) -> SisoEnumsParser:
        """Parse an in-memory XML string without printing or writing files."""
        return SisoEnumsParser.from_string(xml_string, qualified=qualified, delimiter=delimiter)

    @staticmethod
    def create_from_file(
        path: str | Path, *, qualified: bool = False, delimiter: str = " / "
    ) -> SisoEnumsParser:
        """Read and parse a UTF-8 XML file."""
        return SisoEnumsParser.from_file(path, qualified=qualified, delimiter=delimiter)

    @staticmethod
    def write_output(parser: SisoEnumsParser, output_folder: str | Path = "output") -> Path:
        return parser.write_output_files(output_folder)

    createFromString = create_from_string
    createFromFile = create_from_file
    writeOutput = write_output
