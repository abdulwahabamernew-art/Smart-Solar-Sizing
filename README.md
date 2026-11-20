# Smart Solar Sizing

**Development snapshot:** v3.2 — PV compatibility workspace
**Status:** In development; not an installation approval or certified engineering design.

## Project Overview

Smart Solar Sizing is a Python prototype for preliminary solar-system sizing and equipment-data review, with a focus on Yemen-oriented load and location examples. The v3.2 snapshot combines the earlier sizing and inventory work with a source-aware photovoltaic (PV) panel/inverter compatibility screening layer.

The project intentionally keeps assumptions and missing manufacturer data visible. Its calculations and compatibility results are decision-support examples only and must be checked by a qualified solar/electrical professional against the actual equipment, site conditions, and applicable standards before procurement or installation.

## Main Features

- Preliminary daily-energy, PV-array, battery-energy, continuous-inverter, and motor-starting calculations based on explicitly supplied loads and assumptions.
- Arabic appliance names, aliases, and Arabic-Indic digit handling in the sizing engine.
- Import and audit of three legacy inventory snapshots while preserving source/raw fields and avoiding unsupported stock aggregation.
- Preliminary inventory-based quantities and cost drafts with explicit exchange-rate inputs; prices and stock are not live or verified.
- PV compatibility screening using versioned manufacturer profiles, including string/MPPT voltage and current checks and selected site conditions. Results can be rejected, conditional, pending, or based on an explicit assumption; a conditional result is not an approval.
- JSON examples and outputs that make assumptions and limitations inspectable.

## Project Architecture

- `solar/engine.py` — load parsing and preliminary energy, PV, battery, inverter, and pump-related sizing calculations.
- `solar/inventory.py` — legacy inventory import, normalization, conflict/audit reporting, and preliminary commercial-draft calculations.
- `solar/compatibility.py` — PV array and inverter compatibility screening against the selected source profiles and operating constraints.
- `data/` — preliminary configuration, inventory schema and snapshots, manufacturer profiles, and source manifest.
- `tests/` — unit tests for the sizing engine, inventory processing, and compatibility screening.
- `outputs/` — inspectable sample JSON results used by the demos and documentation; these are not live customer quotations or verified installations.
- `demo.py`, `run_inventory_demo.py`, and `run_compatibility_demo.py` — standalone demonstration entry points.

## Repository Structure

```text
Smart-Solar-Sizing/
├── solar/
│   ├── __init__.py
│   ├── engine.py
│   ├── inventory.py
│   └── compatibility.py
├── data/
│   ├── config.json
│   ├── inventory.schema.json
│   ├── manufacturer_profiles.json
│   ├── source_manifest.json
│   ├── legacy_inventory_0.json
│   ├── legacy_inventory_1.json
│   └── legacy_inventory_2.json
├── tests/
│   ├── test_engine.py
│   ├── test_inventory.py
│   └── test_compatibility.py
├── outputs/
│   ├── compatibility_cases.json
│   ├── commercial_draft_example.json
│   ├── inventory_audit.json
│   └── inventory_normalized.json
├── demo.py
├── run_inventory_demo.py
├── run_compatibility_demo.py
├── README.md
├── README_AR.md
├── README_v3_1_history.md
├── TEST_RESULTS.txt
└── .gitignore
```

## Requirements

- Python 3.9 or later (as stated in the project documentation).
- Python standard library only; no third-party runtime packages are required.

## Installation Instructions

Clone the repository and enter its directory:

```bash
git clone https://github.com/abdulwahabamernew-art/Smart-Solar-Sizing.git
cd Smart-Solar-Sizing
```

No dependency installation step is currently required.

## How to Run

Run the basic sizing example:

```bash
python demo.py
```

Run the inventory and preliminary commercial-draft example:

```bash
python run_inventory_demo.py
```

Run the PV compatibility scenarios:

```bash
python run_compatibility_demo.py
```

The demo scripts may regenerate JSON files under `outputs/`.

## Testing Instructions

From the repository root, run:

```bash
python -m unittest discover -s tests -v
```

The v3.2 suite contains **41 unit tests**. It was run successfully during preparation of this repository snapshot; rerun it in your own environment before relying on changes.

## Development Status

This is an active development snapshot, not a production-ready engineering tool. The source documentation reports 41 tests; the compatibility cases and manufacturer profiles are deliberately version-specific and retain gaps instead of filling them with guessed values.

## Current Limitations

- Load, climate, and solar-resource defaults are preliminary and unverified; location examples do not represent validated coverage of Yemen or certified design extremes.
- Legacy inventory records are not automatically qualified engineering components. Manufacturer ratings, stock, and prices may be incomplete, stale, or unverified.
- The commercial draft is illustrative, not a final customer quotation; it may include electrically incompatible items and omits important balance-of-system, installation, transport, and tax costs.
- PV compatibility checks do not establish full-system compatibility or installation safety. Battery/BMS behavior, AC loads and starting, wiring, protection, earthing, mounting, ventilation, and site-specific design still require professional verification.
- Missing datasheet values remain pending or are shown as explicit assumptions. A compatibility pass or conditional result does **not** certify a system for real installation.

## Future Roadmap

1. Verify exact target component models and datasheet revisions, including missing temperature coefficients and electrical limits.
2. Add validated battery/BMS, AC-load, starting, wiring, protection, and environmental checks before presenting a complete system design.
3. Improve traceability and validation of inventory and location inputs, keeping source and uncertainty information intact.
4. After the calculation path is validated, evaluate integration into the planned Dart/Flutter application described in the project history.

## Author

**Abdulwahab Yahya Mohammed Amer**<br>
Artificial Intelligence & Data Science<br>
GitHub: [abdulwahabamernew-art](https://github.com/abdulwahabamernew-art)

## Language

The Arabic project notes are available in [README_AR.md](README_AR.md). Historical v3.1 context is preserved in [README_v3_1_history.md](README_v3_1_history.md).
