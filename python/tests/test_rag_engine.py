from __future__ import annotations

import sys
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from rag_engine import _build_army_list_from_table, _parse_units_with_roles


class RagEngineArmyListTest(unittest.TestCase):
    def test_army_list_excludes_legends_units_from_headings_by_default(self) -> None:
        faction_text = """# Space Marines

## Units

### Captain
**Points:** 80 | **M:** 6" | **T:** 4 | **SV:** 3+ | **W:** 5 | **LD:** 6+ | **OC:** 1
**Keywords:** Character, Infantry, Imperium, Adeptus Astartes, Captain

---

### Intercessor Squad
**Points:** 80 | **M:** 6" | **T:** 4 | **SV:** 3+ | **W:** 2 | **LD:** 6+ | **OC:** 2
**Keywords:** Infantry, Battleline, Imperium, Adeptus Astartes, Intercessor Squad

---

### Gladiator Lancer
**Points:** 160 | **M:** 10" | **T:** 10 | **SV:** 3+ | **W:** 12 | **LD:** 6+ | **OC:** 3
**Keywords:** Vehicle, Smoke, Imperium, Adeptus Astartes, Gladiator Lancer

---

### Mastodon [Legends]
**Points:** 300 | **M:** 9" | **T:** 14 | **SV:** 2+ | **W:** 30 | **LD:** 6+ | **OC:** 12
**Keywords:** Vehicle, Titanic, Transport, Smoke, Imperium, Adeptus Astartes, Mastodon
"""

        parsed = _parse_units_with_roles(faction_text, "wh40k")
        legends_unit = next(unit for unit in parsed if unit["name"] == "Mastodon [Legends]")
        self.assertIn("LEGENDS", legends_unit["keywords"])

        army_list = _build_army_list_from_table(
            faction_text,
            budget=500,
            game="wh40k",
            question="Build me a 500 point Space Marine army",
        )

        self.assertIsNotNone(army_list)
        self.assertNotIn("Mastodon", army_list)


if __name__ == "__main__":
    unittest.main()
