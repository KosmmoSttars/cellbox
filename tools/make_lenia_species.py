"""Picks the Lenia creatures for the pattern library out of Bert Chan's catalogue.

    python tools/make_lenia_species.py path/to/animals.json

animals.json comes from https://github.com/Chakazul/Lenia (Python/animals.json, MIT license,
© 2018 Bert Chan). Writes assets/patterns/lenia.json with the chosen species, their parameters and their
cells (Lenia's own RLE: '.' is 0, A..X and pA..yO are 1..255 out of 255).
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
OUT = ROOT / "assets" / "patterns" / "lenia.json"

# (section, code, catalogue name, short name for the menu)
SPECIES = (
    ("Orbium", "O2u", "Orbium unicaudatus", "Orbium"),
    ("Orbium", "O2b", "Orbium bicaudatus", "Orbium, two tails"),
    ("Orbium", "OG2g", "Gyrorbium gyrans", "Gyrorbium (circles)"),
    ("Orbium", "OV2u", "Vagorbium undulatus", "Vagorbium (wavy)"),
    ("Orbium", "O4s", "Synorbium solidus", "Synorbium (twin)"),
    ("Scutium", "S1s", "Scutium solidus", "Scutium"),
    ("Scutium", "S2s", "Discutium solidus", "Discutium"),
    ("Scutium", "S3s", "Triscutium solidus", "Triscutium"),
    ("Scutium", "2S1v", "Scutium serratus vagus", "Serrated scutium"),
    ("Pteron", "PG1a", "Gyropteron arcus", "Gyropteron"),
    ("Pteron", "P4al", "Paraptera arcus labens", "Paraptera"),
    ("Pteron", "P5cl", "Pentapteryx cavus labens", "Pentapteryx"),
    ("Pteron", "PV1", "Vagopteron vagus", "Vagopteron"),
    ("Helicium", "H3s", "Helicium solidus", "Helicium (spins)"),
    ("Helicium", "H5s", "Pentahelicium solidus", "Pentahelicium"),
    ("Helicium", "H7s", "Heptahelicium solidus", "Heptahelicium"),
    ("Kronium", "K4s", "Kronium solidus", "Kronium"),
    ("Kronium", "KG4", "Gyrokronium gyrans", "Gyrokronium"),
    ("Kronium", "K7a", "Aurokronium arcus", "Aurokronium"),
    ("Geminium", "3GH2s", "Hydrogeminium saliens", "Hydrogeminium"),
    ("Geminium", "2GG2g", "Gyrogeminium gyrans", "Gyrogeminium"),
    ("Geminium", "3G7n", "Heptageminium natans", "Heptageminium"),
    ("Still life", "2F5l", "Pentafolium lithos", "Pentafolium"),
    ("Still life", "3R5s", "Asterium solidus", "Asterium"),
    ("Still life", "2D6r", "Hexadentium rotans", "Hexadentium (turns)"),
)

CREDIT = ("Lenia creatures from Bert Chan's catalogue, https://github.com/Chakazul/Lenia "
          "(MIT license, (c) 2018 Bert Chan).")


def main() -> int:
    if len(sys.argv) != 2:
        print(__doc__)
        return 2
    catalogue = json.loads(Path(sys.argv[1]).read_text(encoding="utf-8"))
    by_key = {(a["code"], a["name"]): a for a in catalogue if "params" in a}
    out = []
    for section, code, name, short in SPECIES:
        animal = by_key.get((code, name))
        if animal is None:
            print(f"not in the catalogue: {code} {name}")
            return 1
        p = animal["params"]
        if p.get("kn") != 1 or p.get("gn") != 1:
            print(f"{code} uses another kernel or growth shape")
            return 1
        out.append({
            "section": section, "code": code, "name": short, "latin": name,
            "rule": f"Lenia R={p['R']} T={p['T']} m={p['m']} s={p['s']} b={p['b'].replace(',', ';')}",
            "cells": animal["cells"],
        })
    OUT.parent.mkdir(parents=True, exist_ok=True)
    OUT.write_text(json.dumps({"credit": CREDIT, "species": out}, indent=1, ensure_ascii=False) + "\n",
                   encoding="utf-8")
    print(f"{len(out)} species -> {OUT}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
