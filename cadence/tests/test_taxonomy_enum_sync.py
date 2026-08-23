"""CLAUDE.md: enums live in models/enums.py and are mirrored in
config/taxonomy.yaml. If they drift, the taxonomy file wins — but this test
must fail loudly so the drift gets noticed."""
from __future__ import annotations

from cadence.core.classify.taxonomy import load_taxonomy
from cadence.models.enums import CauseSubtype, Disposition, RootCause


def test_taxonomy_values_are_known_enum_members():
    tax = load_taxonomy()
    root_causes = {r.value for r in RootCause}
    subtypes = {s.value for s in CauseSubtype}
    dispositions = {d.value for d in Disposition}

    entries = list(tax.rules) + [tax.default]
    for entry in entries:
        assert entry.root_cause in root_causes, f"{entry.root_cause} missing from models/enums.py RootCause"
        assert entry.subtype in subtypes, f"{entry.subtype} missing from models/enums.py CauseSubtype"
        assert entry.disposition in dispositions, f"{entry.disposition} missing from models/enums.py Disposition"
