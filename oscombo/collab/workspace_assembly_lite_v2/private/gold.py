"""Scoring patterns; the tag is derived from the host-held public source."""
EXPECTED_NAME = "inspection_note.txt"
TAG_PATTERN = r"(?m)^Inspection tag: ([A-Z][A-Z0-9]{2,9}-[0-9]{2})\.$"
