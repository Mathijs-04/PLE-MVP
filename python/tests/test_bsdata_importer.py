from __future__ import annotations

import sys
import tempfile
import unittest
from pathlib import Path


sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bsdata_importer import import_from_local_cat_files, validate_generated_markdown


NS = "http://www.battlescribe.net/schema/catalogueSchema"


class BSDataImporterTest(unittest.TestCase):
    def test_converts_40k_unit_profiles_to_current_markdown_contract(self) -> None:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalogue xmlns="{NS}" name="Imperium - Space Marines">
  <selectionEntries>
    <selectionEntry id="captain" name="Captain" type="model">
      <categoryLinks>
        <categoryLink name="Character"/>
        <categoryLink name="Infantry"/>
        <categoryLink name="Faction: Adeptus Astartes"/>
      </categoryLinks>
      <costs>
        <cost name="pts" value="80"/>
      </costs>
      <profiles>
        <profile id="unit" name="Captain" typeName="Unit">
          <characteristics>
            <characteristic name="M">6"</characteristic>
            <characteristic name="T">4</characteristic>
            <characteristic name="SV">3+</characteristic>
            <characteristic name="W">5</characteristic>
            <characteristic name="LD">6+</characteristic>
            <characteristic name="OC">1</characteristic>
          </characteristics>
        </profile>
        <profile id="bolt" name="Bolt pistol" typeName="Ranged Weapons">
          <characteristics>
            <characteristic name="Range">12"</characteristic>
            <characteristic name="A">1</characteristic>
            <characteristic name="BS">2+</characteristic>
            <characteristic name="S">4</characteristic>
            <characteristic name="AP">0</characteristic>
            <characteristic name="D">1</characteristic>
            <characteristic name="Keywords">Pistol</characteristic>
          </characteristics>
        </profile>
        <profile id="ability" name="Leader" typeName="Abilities">
          <characteristics>
            <characteristic name="Description">This model can be attached to Intercessors.</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
  </selectionEntries>
</catalogue>
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cat = root / "Imperium - Space Marines.cat"
            cat.write_text(xml, encoding="utf-8")
            result = import_from_local_cat_files("wh40k", [cat], data_dir=root / "data")

        self.assertEqual(len(result.generated), 1)
        markdown = result.generated[0].markdown
        self.assertTrue(validate_generated_markdown(markdown))
        self.assertIn("# Space Marines", markdown)
        self.assertIn("### Captain", markdown)
        self.assertIn("**Points:** 80 | **M:** 6\"", markdown)
        self.assertIn("**Keywords:** Character, Infantry, Adeptus Astartes", markdown)
        self.assertIn("| Bolt pistol | Ranged | 12\" | 1 | 2+ | 4 | 0 | 1 | Pistol |", markdown)
        self.assertIn("| Captain | 80 |", markdown)

    def test_resolves_linked_aos_shared_unit_profiles(self) -> None:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalogue xmlns="{NS}" name="Stormcast Eternals">
  <entryLinks>
    <entryLink id="link-lord" name="Lord-Aquilor" targetId="lord" type="selectionEntry"/>
  </entryLinks>
  <sharedSelectionEntries>
    <sharedSelectionEntry id="lord" name="Lord-Aquilor" type="unit">
      <categoryLinks>
        <categoryLink name="HERO"/>
        <categoryLink name="ORDER"/>
        <categoryLink name="STORMCAST ETERNALS"/>
      </categoryLinks>
      <costs>
        <cost name="pts" value="140"/>
      </costs>
      <profiles>
        <profile id="unit" name="Lord-Aquilor" typeName="Unit">
          <characteristics>
            <characteristic name="Move">14"</characteristic>
            <characteristic name="Health">8</characteristic>
            <characteristic name="Save">3+</characteristic>
            <characteristic name="Control">3</characteristic>
          </characteristics>
        </profile>
        <profile id="weapon" name="Heavy Boltstorm Pistol" typeName="Ranged Weapon">
          <characteristics>
            <characteristic name="Rng">12"</characteristic>
            <characteristic name="Atk">4</characteristic>
            <characteristic name="Hit">3+</characteristic>
            <characteristic name="Wnd">3+</characteristic>
            <characteristic name="Rnd">1</characteristic>
            <characteristic name="Dmg">1</characteristic>
            <characteristic name="Ability">Shoot in Combat</characteristic>
          </characteristics>
        </profile>
        <profile id="ability" name="Ride the Winds Aetheric" typeName="Ability (Activated)">
          <characteristics>
            <characteristic name="Timing">Your Movement Phase</characteristic>
            <characteristic name="Effect">Remove this unit from the battlefield.</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </sharedSelectionEntry>
  </sharedSelectionEntries>
</catalogue>
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cat = root / "Stormcast Eternals - Library.cat"
            cat.write_text(xml, encoding="utf-8")
            result = import_from_local_cat_files("aos", [cat], data_dir=root / "data")

        self.assertEqual(len(result.generated), 1)
        markdown = result.generated[0].markdown
        self.assertTrue(validate_generated_markdown(markdown))
        self.assertIn("# Stormcast Eternals", markdown)
        self.assertIn("**Points:** 140 | **Move:** 14\"", markdown)
        self.assertIn("#### Ride the Winds Aetheric (Activated)", markdown)
        self.assertIn("| Lord-Aquilor | 140 |", markdown)

    def test_preserves_existing_markdown_when_points_are_missing(self) -> None:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalogue xmlns="{NS}" name="Stormcast Eternals">
  <selectionEntries>
    <selectionEntry id="lord" name="Lord-Aquilor" type="unit">
      <profiles>
        <profile id="unit" name="Lord-Aquilor" typeName="Unit">
          <characteristics>
            <characteristic name="Move">14"</characteristic>
            <characteristic name="Health">8</characteristic>
            <characteristic name="Save">3+</characteristic>
            <characteristic name="Control">3</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
  </selectionEntries>
</catalogue>
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            data_dir = root / "data"
            data_dir.mkdir()
            (data_dir / "Stormcast Eternals.md").write_text("# Existing\n", encoding="utf-8")
            cat = root / "Stormcast Eternals.cat"
            cat.write_text(xml, encoding="utf-8")
            result = import_from_local_cat_files("aos", [cat], data_dir=data_dir)

        self.assertEqual(result.generated, [])
        self.assertIn("Stormcast Eternals.md", result.preserved)

    def test_imports_aos_faction_rules_from_shared_entries_and_groups(self) -> None:
        xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalogue xmlns="{NS}" name="Stormcast Eternals">
  <sharedSelectionEntries>
    <selectionEntry id="traits" name="Battle Traits: Stormcast Eternals" type="upgrade">
      <profiles>
        <profile id="heavens-sent" name="Heavens-sent" typeName="Ability (Command)">
          <characteristics>
            <characteristic name="Timing">Your Movement Phase</characteristic>
            <characteristic name="Effect">Set up a replacement unit.</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
  </sharedSelectionEntries>
  <sharedSelectionEntryGroups>
    <selectionEntryGroup id="artefacts" name="Artefacts of Power">
      <selectionEntries>
        <selectionEntry id="null-pendant" name="Null Pendant" type="upgrade">
          <profiles>
            <profile id="null-profile" name="Null Pendant" typeName="Ability (Activated)">
              <characteristics>
                <characteristic name="Timing">Once Per Battle</characteristic>
                <characteristic name="Effect">Subtract 5 from the target's control score.</characteristic>
              </characteristics>
            </profile>
          </profiles>
        </selectionEntry>
      </selectionEntries>
    </selectionEntryGroup>
  </sharedSelectionEntryGroups>
  <selectionEntries>
    <selectionEntry id="lord" name="Lord-Aquilor" type="unit">
      <categoryLinks>
        <categoryLink name="HERO"/>
        <categoryLink name="STORMCAST ETERNALS"/>
      </categoryLinks>
      <costs>
        <cost name="pts" value="140"/>
      </costs>
      <profiles>
        <profile id="unit" name="Lord-Aquilor" typeName="Unit">
          <characteristics>
            <characteristic name="Move">14"</characteristic>
            <characteristic name="Health">8</characteristic>
            <characteristic name="Save">3+</characteristic>
            <characteristic name="Control">3</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
  </selectionEntries>
</catalogue>
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            cat = root / "Stormcast Eternals.cat"
            cat.write_text(xml, encoding="utf-8")
            result = import_from_local_cat_files("aos", [cat], data_dir=root / "data")

        self.assertEqual(len(result.generated), 1)
        markdown = result.generated[0].markdown
        self.assertTrue(validate_generated_markdown(markdown))
        self.assertLess(markdown.index("## Army Rules"), markdown.index("## Units"))
        self.assertIn("### Battle Traits", markdown)
        self.assertIn("#### Heavens-sent (Command)", markdown)
        self.assertIn("### Artefacts of Power", markdown)
        self.assertIn("#### Null Pendant (Activated)", markdown)

    def test_merges_subfaction_catalogs_into_parent_faction_file(self) -> None:
        base_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalogue xmlns="{NS}" name="Stormcast Eternals">
  <selectionEntries>
    <selectionEntry id="lord" name="Lord-Aquilor" type="unit">
      <categoryLinks>
        <categoryLink name="HERO"/>
        <categoryLink name="STORMCAST ETERNALS"/>
      </categoryLinks>
      <costs>
        <cost name="pts" value="140"/>
      </costs>
      <profiles>
        <profile id="unit" name="Lord-Aquilor" typeName="Unit">
          <characteristics>
            <characteristic name="Move">14"</characteristic>
            <characteristic name="Health">8</characteristic>
            <characteristic name="Save">3+</characteristic>
            <characteristic name="Control">3</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
  </selectionEntries>
</catalogue>
"""
        subfaction_xml = f"""<?xml version="1.0" encoding="UTF-8"?>
<catalogue xmlns="{NS}" name="Stormcast Eternals - Ruination Brotherhood">
  <selectionEntries>
    <selectionEntry id="formation" name="Ruination Brotherhood" type="upgrade">
      <profiles>
        <profile id="ability" name="Ancient Aura" typeName="Ability (Passive)">
          <characteristics>
            <characteristic name="Effect">Friendly Ruination Chamber units have Ward (5+).</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
    <selectionEntry id="reclusian" name="Reclusians" type="unit">
      <categoryLinks>
        <categoryLink name="INFANTRY"/>
        <categoryLink name="STORMCAST ETERNALS"/>
      </categoryLinks>
      <costs>
        <cost name="pts" value="120"/>
      </costs>
      <profiles>
        <profile id="unit" name="Reclusians" typeName="Unit">
          <characteristics>
            <characteristic name="Move">5"</characteristic>
            <characteristic name="Health">3</characteristic>
            <characteristic name="Save">3+</characteristic>
            <characteristic name="Control">1</characteristic>
          </characteristics>
        </profile>
      </profiles>
    </selectionEntry>
  </selectionEntries>
</catalogue>
"""
        with tempfile.TemporaryDirectory() as temp:
            root = Path(temp)
            base_cat = root / "Stormcast Eternals.cat"
            subfaction_cat = root / "Stormcast Eternals - Ruination Brotherhood.cat"
            base_cat.write_text(base_xml, encoding="utf-8")
            subfaction_cat.write_text(subfaction_xml, encoding="utf-8")
            result = import_from_local_cat_files("aos", [base_cat, subfaction_cat], data_dir=root / "data")

        self.assertEqual(len(result.generated), 1)
        generated = result.generated[0]
        self.assertEqual(generated.filename, "Stormcast Eternals.md")
        self.assertTrue(validate_generated_markdown(generated.markdown))
        self.assertIn("## Subfactions", generated.markdown)
        self.assertIn("### Ruination Brotherhood", generated.markdown)
        self.assertIn("#### Ancient Aura (Passive)", generated.markdown)
        self.assertIn("### Lord-Aquilor", generated.markdown)
        self.assertIn("### Reclusians", generated.markdown)


if __name__ == "__main__":
    unittest.main()
