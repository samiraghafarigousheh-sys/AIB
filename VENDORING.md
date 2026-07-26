# Upstream provenance

The `pybuildingenergy/` directory is a verbatim copy of the upstream
pyBuildingEnergy repository. **Nothing in it is modified on this branch.**

| Field           | Value                                                        |
| --------------- | ------------------------------------------------------------ |
| Upstream        | https://github.com/EURAC-EEBgroup/pyBuildingEnergy           |
| Commit          | `1236ace2fcc54f570cc4e7686b6fa3c1fa8b0573`                   |
| Commit date     | 2026-07-02                                                   |
| Commit subject  | Merge pull request #22 from EURAC-EEBgroup/da_engine_sandbox  |
| Files vendored  | 127 (all files tracked by upstream at that commit)            |
| License         | See `pybuildingenergy/LICENSE.md`                             |

## Verifying the copy is unmodified

All 127 files were verified byte-identical by comparing git blob hashes against
the upstream tree, not just file names. To re-verify:

```bash
git clone https://github.com/EURAC-EEBgroup/pyBuildingEnergy.git /tmp/pbe
git -C /tmp/pbe checkout 1236ace2fcc54f570cc4e7686b6fa3c1fa8b0573

git -C /tmp/pbe ls-files -s | awk '{print $2, $4}' | sort -k2 > /tmp/upstream.txt

git ls-tree -r HEAD --name-only pybuildingenergy \
  | while read f; do echo "$(git rev-parse HEAD:"$f") ${f#pybuildingenergy/}"; done \
  | sort -k2 > /tmp/vendored.txt

diff /tmp/upstream.txt /tmp/vendored.txt && echo "IDENTICAL"
```

## Note on force-added files

Three files are tracked by upstream but match patterns in upstream's own
`.gitignore`. They were force-added (`git add -f`) so the vendored copy is
complete:

- `src/pybuildingenergy/data/beat_building_1301600.json`
- `src/pybuildingenergy/data/building_archetype.py`
- `src/pybuildingenergy/data/readme.md`

## Relevant engine entry points

For orientation when reading the modification branches, the ISO 52016-1 core
lives in `pybuildingenergy/src/pybuildingenergy/source/utils.py`:

| Symbol                                              | Role                                                    |
| --------------------------------------------------- | ------------------------------------------------------- |
| `Calculation_ISO_52010`                             | Weather → per-orientation solar irradiance (ISO 52010-1) |
| `ISO52016.Solar_irradiance_calculation`             | Solar geometry and irradiance decomposition              |
| `ISO52016.Conductance_node_of_element`              | Rated U-value → RC-node conductances                     |
| `ISO52016._single_zone_52016_engine`                | Single-zone hourly balance (used by the legacy wrappers) |
| `ISO52016.simulate_envelope_multizone_free_floating`| Multizone free-floating hourly balance                   |
| `_dynamic_external_convection_h`                    | DOE-2 / MoWiTT / BLAST / simple-combined external h_ce   |

At this upstream commit `_dynamic_external_convection_h` is wired into the
**multizone** engine only; the single-zone engine still reads a constant `h_ce`.
