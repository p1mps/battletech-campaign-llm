# BattleTech: Draconis Reach Campaign System

> A **MechCommander Review Circuit (MRC)** campaign management system for BattleTech tabletop play, integrated with **MegaMek** for tactical scenarios and **Helm Memory Core** for unit data.

---

## Table of Contents

- [What This Is](#what-this-is)
- [Architecture](#architecture)
- [Prerequisites](#prerequisites)
- [Installation](#installation)
  - [1. MegaMek](#1-megamek)
  - [2. Helm Memory Core](#2-helm-memory-core)
  - [3. Python Virtual Environment](#3-python-virtual-environment)
  - [4. Pi Agent MCP Configuration](#4-pi-agent-mcp-configuration)
- [Running the Campaign](#running-the-campaign)
  - [Force Creation](#force-creation)
  - [Battle Preparation](#battle-preparation)
  - [Post-Battle Accounting](#post-battle-accounting)
- [Project Structure](#project-structure)
- [Configuration Reference](#configuration-reference)
- [Troubleshooting](#troubleshooting)

---

## What This Is

This project is a **campaign management framework** for running **BattleTech: Hot Spots — Draconis Reach** scenarios using the **MechCommander Review Circuit (MRC)** ruleset. It provides:

- **Force creation** from the complete MegaMek unit database (9,700+ units)
- **Scenario generation** for MegaMek V2 tactical battles
- **Post-battle accounting** — damage tracking, salvage, repairs, pilot progression
- **Campaign state management** — warchest, reputation, contracts, roster tracking

The system is designed to work with **Pi** (a coding agent harness) as the Game Master, using MCP (Model Context Protocol) servers to interface with:

| Component | Purpose |
|-----------|---------|
| **Helm Memory Core** | Unit database — BV, PV, loadouts, quirks, lore |
| **MegaMek MCP Server** | Scenario file generation (`.mms`) and AAR parsing |
| **helm_lore_filter.py** | CLI tool for faction-specific force discovery |

---

## Architecture

```
┌──────────────────────────────────────────────────────────────────┐
│                         Pi Agent (GM)                            │
│  MercNet-Lestrade — Campaign Administrator Persona               │
└──────────┬──────────────────────┬───────────────────────────────┘
           │                      │
           │  MCP Protocol        │  CLI Script
           ▼                      ▼
┌─────────────────────┐  ┌──────────────────────────────────────┐
│  Helm Memory Core   │  │  helm_lore_filter.py                 │
│  (helm-mcp binary)  │  │  — Lore-filtered unit discovery       │
│                     │  │  — Era/faction filtering              │
│  • 9,700+ units     │  │  — BV lookup                          │
│  • BV/PV values     │  │  — Faction-specific roster building   │
│  • Loadouts         │  │                                      │
│  • Quirks           │  └──────────────────────────────────────┘
│  • Lore             │                  │
└─────────────────────┘                  │
                                         │  MCP Protocol
                                         ▼
                              ┌──────────────────────────────────┐
                              │  MegaMek MCP Server              │
                              │  (megamek_mcp.py)                │
                              │                                  │
                              │  • Scenario generation (.mms)    │
                              │  • V2 feature support            │
                              │  • AAR parsing                   │
                              └──────────────────────────────────┘
                                         │
                                         ▼
                              ┌──────────────────────────────────┐
                              │  MegaMek Game Client             │
                              │  (MegaMek.jar)                   │
                              │                                  │
                              │  • Loads .mms scenarios          │
                              │  • Tabletop tactical play        │
                              │  • Generates game logs           │
                              └──────────────────────────────────┘
```

---

## Prerequisites

| Requirement | Minimum | Notes |
|-------------|---------|-------|
| **Python** | 3.12+ | For MCP servers and CLI tools |
| **Java** | 17+ | Required by MegaMek |
| **Node.js** | 18+ | For Pi agent harness (if using) |
| **Pi Agent** | Latest | `npm install -g @earendil-works/pi-coding-agent` |
| **Git** | Latest | For cloning (optional) |

---

## Installation

### 1. MegaMek

MegaMek is the tabletop simulator. Download from [megamek.org](https://megamek.org).

```bash
# Clone or download the latest release
cd /path/to/campaign
# Place the MegaMek directory here (contains MegaMek.jar, MegaMek.sh, etc.)

# Verify the JAR exists
ls MegaMek.jar
```

**Verify Java:**
```bash
java -version
# Should show Java 17 or later
```

**Verify MegaMek launches:**
```bash
cd megamek
./MegaMek.sh
# Should open the MegaMek GUI
```

### 2. Helm Memory Core

Helm provides the unit database and lookup tools.

```bash
# Clone the Helm repository
git clone https://github.com/longgongs/helm.git /Users/a.imparato/helm
cd /Users/a.imparato/helm

# Build the MCP binary (requires Rust/Cargo)
cargo build --release

# The SQLite database is included:
#   /Users/a.imparato/helm/helm.sqlite
```

**Verify:**
```bash
/Users/a.imparato/helm/target/release/helm-mcp /Users/a.imparato/helm/helm.sqlite list_facets
```

### 3. Python Virtual Environment

```bash
cd /path/to/campaign

# Create and activate the virtual environment
python3 -m venv venv
source venv/bin/activate

# Install Python dependencies
pip install mcp pyyaml

# Verify the MCP servers work:
python helm_lore_filter.py --source "TR:3050" --filter "Raven Alliance" --output json
```

### 4. Pi Agent MCP Configuration

The Pi agent uses `~/.pi/agent/mcp.json` to connect to MCP servers. Create or edit this file:

```json
{
  "mcpServers": {
    "helm": {
      "command": "/path/to/helm/target/release/helm-mcp",
      "args": ["/path/to/helm/helm.sqlite"],
      "directTools": true
    },
    "megamek-generator": {
      "command": "/path/to/campaign/venv/bin/python",
      "args": ["/path/to/campaign/megamek_mcp.py"],
      "directTools": true
    }
  }
}
```

**Replace paths** with your actual installation paths.

---

## Running the Campaign

### Force Creation

**Step 1:** Choose your force (faction) and era.

| Era | MUL Code | Years | Notes |
|-----|----------|-------|-------|
| **ilClan** (pre-Schism) | `TR:3050` | 3039–3050 | Raven Alliance did not yet exist |
| **Clan Invasion** (post-Schism) | `TR:CI` | 3049–3059 | Raven Alliance operates here |

**Step 2:** Discover force-specific units:

```bash
# Example: Raven Alliance units in ilClan era
python3 helm_lore_filter.py --source "TR:3050" --filter "Raven Alliance" --output json

# Example: Entire MUL (all units)
python3 helm_lore_filter.py --source "TR:3050" --filter ".*" --output json

# Example: Faction-specific search
python3 helm_lore_filter.py --source "TR:3050" --filter "Draconis Combine" --output json
```

**Step 3:** Select your starting force (3,000 BV max, at least one BattleMech).

### Battle Preparation

**Step 1:** Generate a MegaMek scenario:

```python
# Via Pi Agent MCP call:
megamek:initialize_game({
  "scenario_id": "dr_achernar_track_1",
  "mapsheets": ["16x17 Grassland 1.board"],
  "gravity": 1.0,
  "temperature": 25,
  "player_force": [
    {"unit": "Mad Cat (Timber Wolf) Prime", "pilot_name": "Commander", "skills": "3/4"}
  ],
  "opfor_force": [
    {"unit": "Daishi (Dire Wolf) Prime", "pilot_name": "Enemy", "skills": "4/5"}
  ]
})
```

**Step 2:** Load the generated `.mms` file in MegaMek via the Scenario Chooser.

### Post-Battle Accounting

After gameplay, parse the results:

```python
# Via Pi Agent MCP call:
megamek:read_after_action_report({
  "scenario_id": "dr_achernar_track_1"
})
```

This provides:
- Casualties and ejected pilots
- Damage reports (armor, structure, critical hits)
- Victory conditions met
- Salvage values

---

## Troubleshooting

### "No lore matches found"

This means the regex pattern didn't match any unit lore. Try:
- Using a different faction tag (e.g., `"Raven Alliance"` vs `"Jade Falcon"`)
- Using `".*"` to list all units in the MUL
- Checking the correct MUL code (see MUL Reference Table above)

### "helm-mcp: command not found"

Verify the binary was built:
```bash
ls /path/to/helm/target/release/helm-mcp
# If missing, run: cd /path/to/helm && cargo build --release
```

### "MegaMek doesn't launch"

Verify Java is installed:
```bash
java -version
```

### "No module named 'mcp'"

Install the Python package:
```bash
source venv/bin/activate
pip install mcp pyyaml
```

### Scenario files won't load in MegaMek

- Ensure the `.mms` file is in the `megamek_saved_games/` directory
- Open MegaMek → Scenario Chooser → Select the `.mms` file
- Verify the map file referenced in the scenario exists in `megamek/boards/`


---

*Designed for the MechCommander Review Circuit (MRC) digital league. Compatible with MegaMek 0.51.0+.*
