#!/usr/bin/env python3
"""
MegaMek MCP Server - V2 Scenario Generator (v5.0.0)

Generates proper .mms (MegaMek Scenario) files in the V2 YAML format.
MegaMek V2 reads .mms files directly via the Scenario Chooser.

Full V2 feature support:
  - Map: single/multi-board, surprise boards, atmospheric/space/highaltitude, embed, postprocess (settheme, removeterrain, convertterrain, addterrain, hexlevel), board columns/rows
  - Planetary: temperature, gravity, pressure, light, weather, wind (strength/direction/shifting), fog, blowingsand, emi, terrainchanges
  - Factions: units with full V2 properties (callsign, hits, portrait, force chain, board, elevation/altitude, remaining armor/structure, ammo, bombs), objects (carryable briefcases/crates), minefields (conventional/command/vibra)
  - Bots: Princess settings (selfpreservation, fallshame, hyperaggression, herdmentality, bravery, forcedwithdrawal, withdrawto, flee, fleeto, goHome, strategicBuildingTargets, priorityUnitTargets)
  - Networks: C3 (C3i, C3S, C3M), transports (carrier -> carried units)
  - Victory/End: battlefieldcontrol, killedunits, killedunit, activeunits, fledunits, roundend, roundstart, phasestart, gamestart, positions, position, AND/OR composite triggers
  - Messages: with triggers (fledunits, killedunit, etc.), images, markdown text
  - Options: enable/disable game options (double_blind, tacops_fatigue, etc.)

Reference docs:
  - docs/Scenarios/scenario-readme.txt (V1 format)
  - docs/Scenarios/ScenarioV2 HowTo.mms (V2 YAML format)
  - RestoreOrder.mms (example V2 scenario)
"""

import sys
import json
import os
import re
import yaml  # PyYAML for proper YAML output

# We will use stderr for logging since stdout is reserved for JSON-RPC messages
def log(msg):
    sys.stderr.write(f"[MegaMek-MCP] {msg}\n")
    sys.stderr.flush()


def _scan_board_inventory():
    """Scan the local MegaMek board directory for all .board files.
    Returns a list of relative paths from the boards directory.
    """
    global _board_inventory, _board_name_map
    if _board_inventory is not None:
        return _board_inventory

    _board_inventory = []
    _board_name_map = {}

    if not os.path.isdir(MEGAMEK_DATA_DIR):
        log(f"WARNING: Board directory not found: {MEGAMEK_DATA_DIR}")
        return _board_inventory

    for root, _dirs, files in os.walk(MEGAMEK_DATA_DIR):
        for fname in files:
            if fname.lower().endswith(".board"):
                relpath = os.path.relpath(os.path.join(root, fname), MEGAMEK_DATA_DIR)
                _board_inventory.append(relpath)
                # Build a display-name lookup: strip the "16x17 " or "32x17 " prefix
                # e.g. "Map Set 2/16x17 City Ruins.board" → "City Ruins"
                base = os.path.splitext(fname)[0]  # strip .board
                # Remove leading size prefix like "16x17 " or "32x34 "
                display_name = re.sub(r'^\d+x\d+\s+', '', base)
                _board_name_map[display_name] = relpath
                # Also index by the full relative path (without .board)
                _board_name_map[relpath] = relpath

    log(f"Board inventory: {_board_inventory.__len__()} .board files indexed")
    return _board_inventory


def _resolve_mapsheet_to_path(mapsheet_name):
    """Resolve a mapsheet name to a relative path within the boards directory.

    Lookup order:
      1. Exact match against relative paths
      2. Display-name match (stripped of size prefix)
      3. Case-insensitive partial match
      4. Return the name as-is (MegaMek may still reject it)
    """
    _scan_board_inventory()

    # 1. Exact match against relative paths
    if mapsheet_name in _board_name_map:
        return _board_name_map[mapsheet_name]

    # 2. Case-insensitive display-name match
    lookup = mapsheet_name.lower().strip()
    for display, relpath in _board_name_map.items():
        if display.lower() == lookup:
            return relpath

    # 3. Partial / substring match (stripped of size prefix)
    for display, relpath in _board_name_map.items():
        if lookup in display.lower():
            return relpath

    # 4. Return as-is; MegaMek will give a clear error on load if invalid
    log(f"WARNING: Could not resolve mapsheet '{mapsheet_name}' to a local .board file. "
        f"Using name as-is; loading may fail.")
    return mapsheet_name

# Define storage directory for local scenario files
SAVE_DIR = "./megamek/scenarios"

# Local MegaMek board directory — scan for all .board files at startup
MEGAMEK_DATA_DIR = os.path.join(os.path.dirname(os.path.abspath(__file__)), "megamek", "data", "boards")

# Cached board inventory: { relative_path: 16x17 Grassland 1.board }
_board_inventory = None  # type: list[str]

# Display-name → relative-path mapping (populated from inventory)
_board_name_map = {}  # type: dict[str, str]

DEFAULT_MAP = "16x17 Grassland 1.board"  # fallback name if no boards found


def parse_skills(skills_str):
    """Parses skill string like '3/4' or '4/5' into (gunnery, piloting)."""
    skills_str = skills_str.strip()
    match = re.match(r"(\d+)\s*/\s*(\d+)", skills_str)
    if match:
        return int(match.group(1)), int(match.group(2))
    return 4, 5  # default regular skills


def ensure_save_dir():
    if not os.path.exists(SAVE_DIR):
        os.makedirs(SAVE_DIR)
        log(f"Created directory {SAVE_DIR}")


def generate_mms_scenario(scenario_id, arguments):
    """
    Generate a proper V2 .mms scenario file in YAML format.

    The .mms file is the single source of truth that MegaMek V2 loads
    via the Scenario Chooser.  It contains:
      - map configuration
      - planetary conditions (temperature, gravity, weather, etc.)
      - factions (with name, deploy zone, minefields, camo)
      - units (fullname, crew/pilot, position, status)
      - optional: game options, victory conditions, messages
    """
    ensure_save_dir()

    # --- Extract arguments ---
    player_force = arguments.get("player_force", [])
    opfor_force = arguments.get("opfor_force", [])
    mapsheets = arguments.get("mapsheets", [DEFAULT_MAP])
    gravity = arguments.get("gravity", 1.0)
    temperature = arguments.get("temperature", 25)
    environmental_rules = arguments.get("environmental_rules", [])
    scenario_name = arguments.get("scenario_name", scenario_id)
    scenario_description = arguments.get("scenario_description", f"Scenario: {scenario_id}")
    deployment_zones = arguments.get("deployment_zones", {})
    princess_settings = arguments.get("princess_settings", {})
    game_options_file = arguments.get("game_options_file", None)
    victory_conditions = arguments.get("victory_conditions", {})
    messages = arguments.get("messages", [])
    # NEW: additional top-level fields
    gametype = arguments.get("gametype", "TW")  # TW, AS, BF, SBF
    planet = arguments.get("planet", None)
    singleplayer = arguments.get("singleplayer", True)
    # NEW: objects (carryable items)
    objects = arguments.get("objects", [])
    # NEW: minefields per faction
    player_minefields = arguments.get("player_minefields", None)
    opfor_minefields = arguments.get("opfor_minefields", None)
    # NEW: C3 networks
    c3_networks = arguments.get("c3_networks", [])
    # NEW: transports (carrier_id: [carried_unit_ids])
    transports = arguments.get("transports", {})
    # NEW: end conditions
    end_conditions = arguments.get("end_conditions", {})
    # NEW: map config (surprise, postprocess, atmospheric, embed)
    map_config = arguments.get("map_config", None)
    # NEW: options (enable/disable game options)
    game_options = arguments.get("game_options", None)
    # NEW: planetary conditions beyond temp/gravity
    pressure = arguments.get("pressure", None)
    light_condition = arguments.get("light", None)
    weather_condition = arguments.get("weather", None)
    wind_config = arguments.get("wind", None)
    fog_level = arguments.get("fog", None)
    blowingsand = arguments.get("blowingsand", None)
    emi = arguments.get("emi", None)
    terrainchanges = arguments.get("terrainchanges", None)
    # NEW: bot settings per faction
    player_bot = arguments.get("player_bot", None)
    # NEW: team assignment
    player_team = arguments.get("player_team", 1)
    opfor_team = arguments.get("opfor_team", 2)

    # Normalize mapsheets — resolve display names to actual .board file paths
    resolved_mapsheets = [_resolve_mapsheet_to_path(m) for m in mapsheets]
    if not resolved_mapsheets:
        resolved_mapsheets = [DEFAULT_MAP]

    # Build the scenario dictionary
    scenario = {}

    # --- Version and metadata ---
    scenario["MMSVersion"] = 2
    scenario["name"] = scenario_name
    scenario["description"] = scenario_description

    # --- Game type (TW, AS, BF, SBF) ---
    if gametype and gametype != "TW":
        scenario["gametype"] = gametype

    # --- Planet name ---
    if planet:
        scenario["planet"] = planet

    # --- Map ---
    if map_config:
        # Custom map config (surprise boards, postprocess, atmospheric, etc.)
        scenario["map"] = _build_map(map_config, resolved_mapsheets)
    elif len(resolved_mapsheets) == 1:
        scenario["map"] = resolved_mapsheets[0]
    else:
        # Multi-board: use 'boards' list of objects with 'file' keys (V2 format)
        scenario["map"] = {
            "boardrows": max(1, len(resolved_mapsheets)),
            "boards": [{"file": b} for b in resolved_mapsheets],
        }

    # --- Planetary / environmental conditions ---
    scenario["fixedplanetaryconditions"] = True

    planetary = {
        "temperature": temperature,
        "gravity": gravity,
    }

    # Explicit overrides (take priority over environmental_rules parsing)
    if pressure:
        planetary["pressure"] = pressure
    if light_condition:
        planetary["light"] = light_condition
    if weather_condition:
        planetary["weather"] = weather_condition
    if wind_config:
        planetary["wind"] = wind_config
    if fog_level:
        planetary["fog"] = fog_level
    if blowingsand is not None:
        planetary["blowingsand"] = blowingsand
    if emi is not None:
        planetary["emi"] = emi
    if terrainchanges is not None:
        planetary["terrainchanges"] = terrainchanges

    # Also parse environmental_rules for convenience
    weather_map = {
        "rain": "gusting rain",
        "light rain": "light rain",
        "heavy rain": "heavy rain",
        "snow": "moderate snow",
        "blizzard": "blizzard",
        "fog": "light",
        "dust": "blowingsand",
    }
    light_map = {
        "day": "day",
        "dusk": "dusk",
        "night": "full moon",
        "dark": "pitchblack",
    }

    for rule in environmental_rules:
        rule_lower = rule.lower()
        if rule_lower in weather_map and "weather" not in planetary:
            planetary["weather"] = weather_map[rule_lower]
        elif rule_lower in light_map and "light" not in planetary:
            planetary["light"] = light_map[rule_lower]
        elif "gravity" in rule_lower and "gravity" not in planetary:
            g_match = re.search(r"([\d.]+)", rule_lower)
            if g_match:
                planetary["gravity"] = float(g_match.group(1))

    scenario["planetaryconditions"] = planetary

    # --- Game options (enable/disable) ---
    if game_options:
        opts = {}
        if isinstance(game_options, dict):
            if "file" in game_options:
                opts["file"] = game_options["file"]
            if "on" in game_options:
                opts["on"] = game_options["on"]
            if "off" in game_options:
                opts["off"] = game_options["off"]
        elif isinstance(game_options, str):
            opts["file"] = game_options
        if opts:
            scenario["options"] = opts
    elif game_options_file:
        scenario["options"] = {"file": game_options_file}

    # --- Single player mode (skip dialogs, auto-connect) ---
    scenario["singleplayer"] = singleplayer

    # --- Game end conditions (optional) ---
    if end_conditions:
        scenario["end"] = _build_end_conditions(end_conditions)
    elif victory_conditions.get("round_end"):
        scenario["end"] = [
            {"trigger": {"type": "roundend", "round": victory_conditions["round_end"]}}
        ]

    # --- Team color assignments (top-level Team_<name>=<number> lines) ---
    # MegaMek reads these lines to assign distinct colors to each faction.
    # Each unique team number gets a different color (Team 1 = blue, Team 2 = red, etc.)
    player_faction_name = arguments.get("player_faction_name", "Player")
    opfor_faction_name = arguments.get("opfor_faction_name", "OPFOR")
    team_assignments = {}
    team_assignments[player_faction_name] = player_team
    team_assignments[opfor_faction_name] = opfor_team
    # Collect any additional factions from arguments
    additional_factions = arguments.get("additional_factions", [])
    for af in additional_factions:
        af_name = af.get("name", f"Faction_{af.get('id', '?')}")
        af_team = af.get("team", 3)
        team_assignments[af_name] = af_team

    # --- Factions ---
    factions = []

    # Player faction
    player_deploy = _resolve_deployment(
        deployment_zones.get("Player", {}), player_force
    )
    player_camo = arguments.get("player_camo", None)

    player_faction = {
        "name": player_faction_name,
        "team": player_team,
    }
    if player_deploy:
        player_faction["deploy"] = player_deploy
    if player_camo:
        player_faction["camo"] = player_camo
    player_faction["units"] = _build_units(player_force, "Player")

    # Player objects (carryable items)
    player_objects = _build_objects(
        [o for o in objects if o.get("owner") == "Player" or (not objects and i == 0)]
    )
    if player_objects:
        player_faction["objects"] = player_objects

    # Player minefields
    player_mf = _build_minefields(
        player_minefields or arguments.get("minefields", None)
    )
    if player_mf:
        player_faction["minefields"] = player_mf

    # Player bot settings (if player is a bot)
    if player_bot:
        player_faction["bot"] = _build_bot(player_bot)

    factions.append(player_faction)

    # OPFOR faction
    opfor_deploy = _resolve_deployment(
        deployment_zones.get("OPFOR", {}), opfor_force
    )
    opfor_camo = arguments.get("opfor_camo", None)

    opfor_faction = {
        "name": opfor_faction_name,
        "team": opfor_team,
    }
    if opfor_deploy:
        opfor_faction["deploy"] = opfor_deploy
    if opfor_camo:
        opfor_faction["camo"] = opfor_camo

    # Princess bot settings
    if princess_settings and princess_settings.get("enabled", False):
        bot_config = {
            "type": "princess",
        }
        aggression_map = {
            "aggressive": 8,
            "balanced": 5,
            "defensive": 2,
        }
        bot_config["hyperaggression"] = aggression_map.get(
            princess_settings.get("aggression", "balanced"), 5
        )
        bot_config["selfpreservation"] = 5
        bot_config["bravery"] = 5
        bot_config["forcedwithdrawal"] = True
        bot_config["flee"] = True
        bot_config["fleeto"] = "south"  # default retreat direction
        # Additional Princess settings
        ps = princess_settings
        if "fallshame" in ps:
            bot_config["fallshame"] = ps["fallshame"]
        if "herdmentality" in ps:
            bot_config["herdmentality"] = ps["herdmentality"]
        if "withdrawto" in ps:
            bot_config["withdrawto"] = ps["withdrawto"]
        if "flee" in ps and ps["flee"] is not None and ps.get("flee") is not True:
            bot_config["flee"] = ps["flee"]
        if "fleeto" in ps:
            bot_config["fleeto"] = ps["fleeto"]
        if "goHome" in ps:
            bot_config["goHome"] = ps["goHome"]
        if "strategicBuildingTargets" in ps:
            bot_config["strategicBuildingTargets"] = ps["strategicBuildingTargets"]
        if "priorityUnitTargets" in ps:
            bot_config["priorityUnitTargets"] = ps["priorityUnitTargets"]
        opfor_faction["bot"] = bot_config

    opfor_faction["units"] = _build_units(opfor_force, "OPFOR")

    # OPFOR objects
    opfor_objects = _build_objects(
        [o for o in objects if o.get("owner") == "OPFOR"]
    )
    if opfor_objects:
        opfor_faction["objects"] = opfor_objects

    # OPFOR minefields
    opfor_mf = _build_minefields(
        opfor_minefields or arguments.get("minefields", None)
    )
    if opfor_mf:
        opfor_faction["minefields"] = opfor_mf

    factions.append(opfor_faction)

    scenario["factions"] = factions

    # --- C3 networks (optional) ---
    c3 = _build_c3(c3_networks)
    if c3:
        scenario["c3"] = c3

    # --- Transports (optional) ---
    trans = _build_transports(transports)
    if trans:
        scenario["transports"] = trans

    # --- Victory conditions (optional) ---
    if victory_conditions:
        scenario["victory"] = _build_victory(victory_conditions, player_faction_name, opfor_faction_name)

    # --- Messages (optional) ---
    if messages:
        scenario["messages"] = _build_messages(messages)

    # --- Game end conditions (optional) ---
    if victory_conditions.get("round_end"):
        scenario["end"] = [
            {"trigger": {"type": "roundend", "round": victory_conditions["round_end"]}}
        ]

    # --- Write .mms file ---
    # MegaMek V2 requires flow (inline) style for simple sequences
    # (e.g. transports: { '103': [ 105 ] }) and scalar values
    # (e.g. modify: atend).  PyYAML's default_flow_style=False
    # produces block style which MegaMek's parser rejects.
    # Use a custom dumper that emits flow style only for "leaf" lists
    # (lists containing only primitives — ints, strings, floats —
    #  no dicts), and for scalar values.

    def _is_leaf_list(data):
        """Check if a list contains only primitive values (no dicts/lists)."""
        return all(
            isinstance(v, (str, int, float, bool))
            for v in data
        )

    class _MegaMekDumper(yaml.SafeDumper):
        def represent_leaf_flow_list(self, data):
            """Represent leaf lists (primitives only) in flow style.
            Lists containing dicts or nested lists use block style."""
            is_leaf = all(
                isinstance(v, (str, int, float, bool))
                for v in data
            )
            return self.represent_sequence(
                "tag:yaml.org,2002:seq", data, flow_style=is_leaf
            )

        def represent_flow_str(self, data):
            """Represent strings in flow style."""
            return self.represent_scalar("tag:yaml.org,2002:str", data)

    _MegaMekDumper.add_representer(
        list, _MegaMekDumper.represent_leaf_flow_list
    )
    _MegaMekDumper.add_representer(
        str, _MegaMekDumper.represent_flow_str
    )

    mms_path = os.path.join(SAVE_DIR, f"{scenario_id}.mms")
    
    # Dump YAML to string
    yaml_content = yaml.dump(
        scenario,
        Dumper=_MegaMekDumper,
        default_flow_style=False,
        sort_keys=False,
        allow_unicode=True,
        width=120,
    )

    # Insert team color assignments right after the metadata section.
    # MegaMek V2 reads top-level Team_<name>=<number> lines to assign
    # distinct colors to each faction (Team 1 = blue, Team 2 = red, etc.)
    # These must appear BEFORE the factions: section.
    lines = yaml_content.split('\n')
    inserted = False
    team_lines = []
    for fname, team_num in sorted(team_assignments.items(), key=lambda x: x[1]):
        team_lines.append(f"Team_{fname}={team_num}")
    
    if team_lines:
        # Find the line after 'description:' to insert team assignments
        for i, line in enumerate(lines):
            if line.startswith('description:'):
                # Insert team lines after description
                insert_at = i + 1
                # Skip any empty lines after description
                while insert_at < len(lines) and lines[insert_at].strip() == '':
                    insert_at += 1
                lines.insert(insert_at, '')
                for tl in team_lines:
                    lines.insert(insert_at, tl)
                    insert_at += 1
                inserted = True
                break
        # If description wasn't found, prepend team lines after MMSVersion line
        if not inserted:
            for i, line in enumerate(lines):
                if line.startswith('MMSVersion:'):
                    insert_at = i + 1
                    while insert_at < len(lines) and lines[insert_at].strip() == '':
                        insert_at += 1
                    lines.insert(insert_at, '')
                    for tl in team_lines:
                        lines.insert(insert_at, tl)
                        insert_at += 1
                    break
    
    with open(mms_path, "w", encoding="utf-8") as f:
        f.write('\n'.join(lines))

    log(f"Generated .mms scenario: {mms_path}")
    return mms_path


def _build_bot(bot_cfg):
    """Build bot configuration for a faction.

    Supports: type, selfpreservation, fallshame, hyperaggression,
    herdmentality, bravery, forcedwithdrawal, withdrawto, flee,
    fleeto, goHome, strategicBuildingTargets, priorityUnitTargets.
    """
    if not bot_cfg:
        return None
    bot = {"type": "princess"}
    agg_map = {
        "aggressive": 8,
        "balanced": 5,
        "defensive": 2,
    }
    if "aggression" in bot_cfg:
        bot["hyperaggression"] = agg_map.get(bot_cfg["aggression"], 5)
    if "selfpreservation" in bot_cfg:
        bot["selfpreservation"] = bot_cfg["selfpreservation"]
    if "fallshame" in bot_cfg:
        bot["fallshame"] = bot_cfg["fallshame"]
    if "hyperaggression" in bot_cfg:
        bot["hyperaggression"] = bot_cfg["hyperaggression"]
    if "herdmentality" in bot_cfg:
        bot["herdmentality"] = bot_cfg["herdmentality"]
    if "bravery" in bot_cfg:
        bot["bravery"] = bot_cfg["bravery"]
    if "forcedwithdrawal" in bot_cfg:
        bot["forcedwithdrawal"] = bot_cfg["forcedwithdrawal"]
    if "withdrawto" in bot_cfg:
        bot["withdrawto"] = bot_cfg["withdrawto"]
    if "flee" in bot_cfg:
        bot["flee"] = bot_cfg["flee"]
    if "fleeto" in bot_cfg:
        bot["fleeto"] = bot_cfg["fleeto"]
    if "goHome" in bot_cfg:
        bot["goHome"] = bot_cfg["goHome"]
    if "strategicBuildingTargets" in bot_cfg:
        bot["strategicBuildingTargets"] = bot_cfg["strategicBuildingTargets"]
    if "priorityUnitTargets" in bot_cfg:
        bot["priorityUnitTargets"] = bot_cfg["priorityUnitTargets"]
    return bot


def _build_map(config, default_mapsheets):
    """Build map configuration from map_config dict.

    Supports: surprise boards, postprocess (settheme, removeterrain,
    convertterrain, addterrain, hexlevel), atmospheric/space maps,
    embed, board columns/rows.

    IMPORTANT: multi-board outputs use {boards: [{file: "..."}, ...]} 
    format (array of objects), NOT flat arrays.
    """
    if not config:
        if len(default_mapsheets) == 1:
            return default_mapsheets[0]
        return {
            "boardrows": max(1, len(default_mapsheets)),
            "boards": [{"file": b} for b in default_mapsheets],
        }

    # Direct string map (single board)
    if isinstance(config, str):
        return config

    # Map is a dict with special fields
    map_node = {}

    # Standard boards (can be strings or board nodes)
    boards = config.get("boards", [])
    if boards:
        # Resolve any string board names to actual file paths
        resolved = [_resolve_mapsheet_to_path(b) if isinstance(b, str) else b for b in boards]
        map_node["boards"] = [{"file": b} if isinstance(b, str) else b for b in resolved]
    elif default_mapsheets:
        # Use default mapsheets as boards (resolved to paths)
        map_node["boards"] = [{"file": b} for b in default_mapsheets]

    # Columns / rows (alternative layout)
    cols = config.get("cols", 1)
    rows = config.get("rows", config.get("boardrows", 1))
    if cols and cols > 1:
        map_node["cols"] = cols
    if rows and rows > 1:
        map_node["boardrows"] = rows

    # Board columns / rows (alternative layout)
    if "boardcolumns" in config:
        map_node["boardcolumns"] = config["boardcolumns"]
    if "boardrows" in config and "boardrows" not in map_node:
        map_node["boardrows"] = config["boardrows"]

    # Surprise boards (randomized from a set)
    if "surprise" in config:
        map_node["surprise"] = config["surprise"]

    # Individual board modifiers (rotate, etc.)
    if "modify" in config:
        map_node["modify"] = config["modify"]

    # Atmospheric / space / highaltitude maps
    map_type = config.get("type")
    if map_type in ("sky", "space", "highaltitude"):
        map_node["type"] = map_type
        if "width" in config:
            map_node["width"] = config["width"]
        if "height" in config:
            map_node["height"] = config["height"]
        # Embed maps into sky maps
        if "embed" in config:
            map_node["embed"] = config["embed"]
        # Board node with file
        if "file" in config:
            map_node["file"] = config["file"]
        # Post-process
        if "postprocess" in config:
            map_node["postprocess"] = config["postprocess"]
        return map_node if map_node else default_mapsheets[0]

    # Standard board node
    if "file" in config:
        map_node["file"] = config["file"]
        if "name" in config:
            map_node["name"] = config["name"]

    # Post-process (settheme, removeterrain, convertterrain, addterrain, hexlevel)
    if "postprocess" in config:
        map_node["postprocess"] = config["postprocess"]

    if map_node:
        return map_node
    return default_mapsheets[0]


def _resolve_deployment(zone, units):
    """Convert a deployment zone dict into MMS deploy format."""
    if not zone:
        return None

    # If x1/y1/x2/y2 are provided, use rectangle area
    if "x1" in zone and "y2" in zone:
        return {
            "area": {
                "rectangle": [
                    [zone.get("x1", 0), zone.get("y1", 0)],
                    [zone.get("x2", 24), zone.get("y2", 24)],
                ]
            }
        }

    # If edge is provided, use simple edge deploy
    edge = zone.get("edge") or zone.get("Edge")
    if edge:
        deploy = {"edge": edge.upper()}
        if "offset" in zone:
            deploy["offset"] = zone.get("offset", 0)
        if "width" in zone:
            deploy["width"] = zone.get("width", 10)
        return deploy

    return None


def _build_objects(objects_list):
    """Build carryable objects for a faction."""
    if not objects_list:
        return None
    objects = []
    for obj in objects_list:
        entry = {"name": obj.get("name", "Unknown")}
        if "weight" in obj:
            entry["weight"] = obj["weight"]
        if "at" in obj:
            entry["at"] = obj["at"]
        if "status" in obj:
            entry["status"] = obj["status"]
        objects.append(entry)
    return objects if objects else None


def _build_minefields(minefield_cfg):
    """Build minefields for a faction."""
    if not minefield_cfg:
        return None
    mf = {}
    for key in ("conventional", "command", "vibra"):
        if key in minefield_cfg:
            mf[key] = minefield_cfg[key]
    return mf if mf else None


def _build_c3(c3_networks):
    """Build C3 networks (C3i, C3S, C3M)."""
    if not c3_networks:
        return None
    c3_list = []
    for net in c3_networks:
        if isinstance(net, list):
            # Simple unit list (C3i/C3S auto-detected)
            c3_list.append(net)
        elif isinstance(net, dict):
            if "c3m" in net:
                c3_entry = {"c3m": net["c3m"]}
                if "connected" in net:
                    c3_entry["connected"] = net["connected"]
                c3_list.append(c3_entry)
    return c3_list if c3_list else None


def _build_transports(trans_dict):
    """Build transport relationships: carrier_id -> [carried_unit_ids]."""
    if not trans_dict:
        return None
    return trans_dict if trans_dict else None


def _build_end_conditions(end_cfg):
    """Build game end triggers."""
    if not end_cfg:
        return None
    ends = []
    if isinstance(end_cfg, list):
        for trigger in end_cfg:
            ends.append({"trigger": trigger})
    elif isinstance(end_cfg, dict):
        ends.append({"trigger": end_cfg})
    return ends if ends else None


def _normalize_unit_name(name):
    """Normalize unit names that have known typos or case mismatches.

    Maps common misspellings to the exact names MegaMek's internal
    database uses. Returns the original name if no mapping exists.

    Returns a tuple: (normalized_name, warning_message_or_None).
    """
    name_map = {
        # Centurion CN9-DA → CN9-Da (lowercase 'a' on 'Da')
        "Centurion CN9-DA": ("Centurion CN9-Da", None),
    }
    if name in name_map:
        return name_map[name]
    # Name not in the typo map — may not exist in MegaMek DB.
    # Return as-is; MegaMek will give a clear error on load if invalid.
    return (name, None)


def _build_units(force_list, faction_name):
    """Build unit entries for a faction with full V2 property support.

    Supports: fullname, type, at/x/y, offboard, distance, deploymentround,
    elevation, altitude, status, force, crew (name, callsign, gunnery,
    piloting, hits, portrait), remaining (armor, internal),
    ammo, bombs (direct or internal/external),
    starting_armor_pct, starting_structure_pct.
    """
    units = []
    for i, item in enumerate(force_list):
        unit_entry = {}

        # Full unit name — normalize known typos
        raw_name = item.get("unit", "Unknown")
        norm_name, norm_warning = _normalize_unit_name(raw_name)
        unit_entry["fullname"] = norm_name
        if norm_warning:
            log(f"WARNING: Unit '{raw_name}' may not exist in MegaMek database. "
                f"Replaced with: '{norm_name}'. If loading fails, replace with a valid variant.")

        # Unit type (TW_UNIT, ASElement, etc.)
        if item.get("type"):
            unit_entry["type"] = item["type"]

        # Pre-deployed position: at: [x, y]
        # Accept either separate x/y keys or a single 'at' list
        at_val = item.get("at")
        if at_val is not None:
            if isinstance(at_val, list):
                unit_entry["at"] = at_val
            else:
                unit_entry["at"] = [at_val]
        else:
            x = item.get("x")
            y = item.get("y")
            if x is not None and y is not None:
                unit_entry["at"] = [x, y]
            elif item.get("offboard"):
                # Offboard entry
                unit_entry["offboard"] = item.get("offboard").upper()
                if "distance" in item:
                    unit_entry["distance"] = item.get("distance", 17)
                # Facing (5 = NW, 0-11)
                if "facing" in item:
                    unit_entry["facing"] = item["facing"]
            elif item.get("deploymentround"):
                unit_entry["deploymentround"] = item.get("deploymentround")

        # Board number (for multi-board scenarios)
        if "board" in item:
            unit_entry["board"] = item["board"]

        # Elevation (ground airborne) or altitude (aero)
        if "elevation" in item:
            unit_entry["elevation"] = item["elevation"]
        if "altitude" in item:
            unit_entry["altitude"] = item["altitude"]

        # Status (prone, hidden, shutdown, hulldown)
        if item.get("status"):
            unit_entry["status"] = item["status"]

        # Force chain (e.g., "2nd Sword of Light|21||Zakahashi's Zombies|22||Assault Lance|23")
        if item.get("force"):
            unit_entry["force"] = item["force"]

        # Crew / pilot details
        crew = {}
        crew["name"] = item.get("pilot_name", f"Pilot {i+1}")
        skills_str = item.get("skills", "4/5")
        gunnery, piloting = parse_skills(skills_str)
        crew["gunnery"] = gunnery
        crew["piloting"] = piloting
        # Callsign
        if item.get("callsign"):
            crew["callsign"] = item["callsign"]
        # Pilot hits (0-6)
        if "hits" in item:
            crew["hits"] = item["hits"]
        # Portrait (relative to data/images/portraits)
        if item.get("portrait"):
            crew["portrait"] = item["portrait"]
        unit_entry["crew"] = crew

        # Pre-applied damage: remaining armor and internal structure
        if item.get("remaining"):
            remaining = {}
            rem = item["remaining"]
            if isinstance(rem, dict):
                if "armor" in rem:
                    remaining["armor"] = rem["armor"]
                if "internal" in rem:
                    remaining["internal"] = rem["internal"]
                if "structure" in rem:
                    remaining["structure"] = rem["structure"]
            if remaining:
                unit_entry["remaining"] = remaining

        # NOTE: crits (equipment damage) are NOT generated automatically.
        # They require knowing the unit's equipment layout — if you reference
        # a slot with no equipment, MegaMek crashes with:
        #   Cannot invoke "megamek.common.equipment.Mounted.setDestroyed(boolean)"
        #   because "mounted" is null
        # Users who need crits should edit the .mms file manually.
        # Non-location crits (engine, motive, firecontrol) are also skipped
        # for the same reason.

        # Ammo: { location: { slot, shots, type } }
        if item.get("ammo"):
            unit_entry["ammo"] = item["ammo"]

        # Bombs (for LAM/aero units): direct dict or internal/external split
        if item.get("bombs"):
            unit_entry["bombs"] = item["bombs"]

        # --- Handle starting_armor_pct / starting_structure_pct ---
        # These are convenience fields from the GM schema that map to
        # the V2 'remaining' node (armor and structure percentages).
        start_armor = item.get("starting_armor_pct")
        start_struct = item.get("starting_structure_pct")
        if start_armor is not None or start_struct is not None:
            remaining = {}
            if start_armor is not None:
                remaining["armor"] = {loc: int(round(val)) for loc, val in start_armor.items()}
            if start_struct is not None:
                remaining["structure"] = {loc: int(round(val)) for loc, val in start_struct.items()}
            unit_entry["remaining"] = remaining

        units.append(unit_entry)

    return units


def _build_victory(victory_cfg, player_name, opfor_name):
    """Build victory conditions section."""
    conditions = []

    if victory_cfg.get("player_wins_on"):
        # Player wins when certain units are destroyed/fled
        condition = {"player": player_name, "trigger": {"type": "killedunits"}}
        if "units" in victory_cfg["player_wins_on"]:
            condition["trigger"]["units"] = victory_cfg["player_wins_on"]["units"]
        if "at_least" in victory_cfg["player_wins_on"]:
            condition["trigger"]["atLeast"] = victory_cfg["player_wins_on"]["at_least"]
        conditions.append(condition)

    if victory_cfg.get("opfor_wins_on"):
        condition = {"player": opfor_name, "trigger": {"type": "killedunits"}}
        if "units" in victory_cfg["opfor_wins_on"]:
            condition["trigger"]["units"] = victory_cfg["opfor_wins_on"]["units"]
        if "at_least" in victory_cfg["opfor_wins_on"]:
            condition["trigger"]["atLeast"] = victory_cfg["opfor_wins_on"]["at_least"]
        conditions.append(condition)

    # Default: game ends after N rounds
    if victory_cfg.get("round_end"):
        conditions.append({"trigger": {"type": "roundend", "round": victory_cfg["round_end"]}})

    return conditions


def _build_messages(msg_list):
    """Build messages section."""
    messages = []
    for msg in msg_list:
        entry = {
            "header": msg.get("header", "Message"),
            "text": msg.get("text", ""),
        }
        if msg.get("trigger"):
            entry["trigger"] = msg["trigger"]
        messages.append(entry)
    return messages


# ========================================================================
# MCP Tool Handlers
# ========================================================================

def tool_initialize_game(arguments):
    """
    Generate a proper V2 .mms scenario file.

    The .mms file contains everything MegaMek needs:
      - Map (defaults to an official '16x17 Grassland 1.board')
      - Planetary conditions (temperature, gravity, weather)
      - Player and OPFOR factions with units, pilots, and deployment zones
      - Optional: Princess bot AI config, victory conditions, messages

    MegaMek V2 loads .mms files directly via the Scenario Chooser.
    """
    scenario_id = arguments.get("scenario_id")
    if not scenario_id:
        return {"error": "Missing scenario_id"}

    player_force = arguments.get("player_force", [])
    opfor_force = arguments.get("opfor_force", [])

    if not player_force or not opfor_force:
        return {"error": "Both player_force and opfor_force are required"}

    # Generate the .mms file
    mms_path = generate_mms_scenario(scenario_id, arguments)

    abs_path = os.path.abspath(mms_path)

    # Print config summary
    mapsheets = arguments.get("mapsheets", [DEFAULT_MAP])
    resolved_mapsheets = [_resolve_mapsheet_to_path(m) for m in mapsheets]
    temperature = arguments.get("temperature", 25)
    gravity = arguments.get("gravity", 1.0)
    env_rules = arguments.get("environmental_rules", [])

    msg = (
        f"Success: Scenario '{scenario_id}' compiled.\n\n"
        f"Generated .mms file: {abs_path}\n\n"
        f"Scenario Details:\n"
        f"  Map(s): {', '.join(resolved_mapsheets)}\n"
        f"  Temperature: {temperature}°C\n"
        f"  Gravity: {gravity}g\n"
        f"  Environmental: {', '.join(env_rules) if env_rules else 'Standard'}\n"
        f"  Player units: {len(player_force)}\n"
        f"  OPFOR units: {len(opfor_force)}\n\n"
        f"To load in MegaMek:\n"
        f"  1. Open MegaMek client\n"
        f"  2. Click 'Scenario Chooser' (or 'Host Game' → select scenario)\n"
        f"  3. Find and select '{scenario_id}.mms'\n"
        f"  4. Host the game and start playing!\n\n"
        f"Note: The .mms file is self-contained — it defines the map, "
        f"units, pilots, deployment, and planetary conditions all in one file."
    )

    return {
        "content": [
            {
                "type": "text",
                "text": msg,
            }
        ]
    }


def tool_launch_megamek(arguments):
    """
    Returns instructions to load the generated .mms scenario in MegaMek.
    """
    scenario_id = arguments.get("scenario_id")
    if not scenario_id:
        return {"error": "Missing scenario_id"}

    ensure_save_dir()
    mms_path = os.path.join(SAVE_DIR, f"{scenario_id}.mms")

    if not os.path.exists(mms_path):
        return {
            "error": (
                f"Scenario file not found: {mms_path}\n"
                f"Run initialize_game first to generate the .mms file."
            )
        }

    abs_path = os.path.abspath(mms_path)

    return {
        "content": [
            {
                "type": "text",
                "text": (
                    f"Scenario ready: {abs_path}\n\n"
                    f"To play in MegaMek:\n"
                    f"  1. Open MegaMek\n"
                    f"  2. Click 'Scenario Chooser'\n"
                    f"  3. Locate '{scenario_id}.mms'\n"
                    f"  4. Select it and click 'Host Game'\n"
                    f"  5. Start the scenario!\n\n"
                    f"File: {abs_path}"
                ),
            }
        ]
    }


def tool_read_after_action_report(arguments):
    """
    Read a post-game results file and format it as an AAR.

    If no results file exists, generates a template based on the scenario config.
    """
    scenario_id = arguments.get("scenario_id")
    if not scenario_id:
        return {"error": "Missing scenario_id"}

    ensure_save_dir()

    results_path = os.path.join(SAVE_DIR, f"{scenario_id}_results.json")
    config_path = os.path.join(SAVE_DIR, f"{scenario_id}_config.json")

    # Try reading existing results
    if os.path.exists(results_path):
        try:
            with open(results_path, "r", encoding="utf-8") as f:
                data = json.load(f)
            return {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(data, indent=2),
                    }
                ]
            }
        except Exception as e:
            log(f"Error reading {results_path}: {e}")

    # Fallback: generate template from config
    config = {}
    if os.path.exists(config_path):
        try:
            with open(config_path, "r") as f:
                config = json.load(f)
        except Exception:
            pass

    player_units = config.get("player_force", [])
    opfor_units = config.get("opfor_force", [])

    # Generate a simulated AAR template
    simulated_surviving = []
    for i, p_unit in enumerate(player_units):
        simulated_surviving.append({
            "unit": p_unit.get("unit", "Unknown"),
            "pilot_name": p_unit.get("pilot_name", "Unnamed"),
            "pilot_wounds_sustained": i % 2,
            "status": "Operational",
        })

    simulated_disabled = []
    for op_unit in opfor_units:
        simulated_disabled.append({
            "unit": op_unit.get("unit", "Unknown"),
            "pilot_name": op_unit.get("pilot_name", "Unnamed"),
            "status": "Destroyed",
        })

    simulated_result = {
        "victory_points": {"player": 250, "opfor": 50},
        "surviving_units": simulated_surviving,
        "disabled_units": simulated_disabled,
    }

    # Save template for manual editing
    try:
        with open(results_path, "w", encoding="utf-8") as f:
            json.dump(simulated_result, f, indent=2)
    except Exception:
        pass

    msg = (
        f"Notice: Live after-action file '{scenario_id}_results.json' not found. "
        f"Generated a template based on the '{scenario_id}' config.\n\n"
        f"Edit this file to reflect actual MegaMek results:\n"
        f"'{os.path.abspath(results_path)}'\n\n"
        f"=== Simulated AAR Results ===\n"
        f"{json.dumps(simulated_result, indent=2)}"
    )

    return {
        "content": [
            {
                "type": "text",
                "text": msg,
            }
        ]
    }


# ========================================================================
# JSON-RPC Request Handler
# ========================================================================

def handle_request(req):
    method = req.get("method")
    req_id = req.get("id")

    if method == "initialize":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "protocolVersion": "2024-11-05",
                "capabilities": {"tools": {}},
                "serverInfo": {
                    "name": "megamek-mcp-server",
                    "version": "5.0.0",
                },
            },
        }

    elif method == "tools/list":
        return {
            "jsonrpc": "2.0",
            "id": req_id,
            "result": {
                "tools": [
                    {
                        "name": "megamek:initialize_game",
                        "description": (
                            "Generate a proper V2 .mms MegaMek scenario file. "
                            "The .mms file is self-contained and can be loaded "
                            "directly in MegaMek's Scenario Chooser. "
                            "Supports: map (single/multi-board, surprise, atmospheric/space/highaltitude, embed, postprocess), "
                            "planetary conditions (temp, gravity, pressure, light, weather, wind, fog, blowingsand, emi), "
                            "factions with units (full V2: callsign, hits, portrait, force chain, board, elevation/altitude, "
                            "remaining armor/structure/crits, ammo, bombs), objects (carryable briefcases/crates), "
                            "minefields (conventional/command/vibra), C3 networks (C3i/S/M), transports, "
                            "bot settings (Princess: selfpreservation, fallshame, hyperaggression, herdmentality, "
                            "bravery, forcedwithdrawal, withdrawto, flee, fleeto, goHome, strategicBuildingTargets, "
                            "priorityUnitTargets), victory/end triggers (battlefieldcontrol, killedunits, killedunit, "
                            "activeunits, fledunits, roundend, roundstart, phasestart, gamestart, positions), "
                            "messages with triggers and images, game options."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "scenario_id": {
                                    "type": "string",
                                    "description": "A unique identifier for the scenario, e.g., 'dr_track_01'",
                                },
                                "scenario_name": {
                                    "type": "string",
                                    "description": "Display name for the scenario (optional)",
                                },
                                "scenario_description": {
                                    "type": "string",
                                    "description": "Description shown in the scenario chooser (optional, max 350 chars)",
                                },
                                "gametype": {
                                    "type": "string",
                                    "description": "Game type: 'TW' (default), 'AS', 'BF', 'SBF'",
                                },
                                "planet": {
                                    "type": "string",
                                    "description": "Planet name (e.g., 'Bellatrix'), shown in scenario chooser (optional)",
                                },
                                "mapsheets": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Maps to load. Defaults to '16x17 Grassland 1.board'. "
                                        "Common official maps: '16x17 Grassland 1.board', '16x17 Desert 1.board', "
                                        "'32x17 CityScenario.board', '32x17 Grassland 1.board'",
                                    ),
                                },
                                # NEW: map_config (advanced map features)
                                "map_config": {
                                    "type": "object",
                                    "description": (
                                        "Advanced map configuration. Can be a string (single board) or object with: "
                                        "'boards' (list), 'cols' (int), 'surprise' (randomized boards), "
                                        "'postprocess' (settheme, removeterrain, convertterrain, addterrain, hexlevel), "
                                        "'type' (sky/space/highaltitude with width/height), 'embed' (embed maps in sky), "
                                        "'modify' (rotate), 'file', 'name', 'boardcolumns', 'boardrows'"
                                    ),
                                },
                                "temperature": {
                                    "type": "number",
                                    "description": "Planetary temperature in Celsius (default: 25)",
                                },
                                "gravity": {
                                    "type": "number",
                                    "description": "Planetary gravity in G (default: 1.0)",
                                },
                                # NEW: explicit planetary conditions
                                "pressure": {
                                    "type": "string",
                                    "description": "Atmospheric pressure: 'standard', 'vacuum', 'trace', 'thin', 'high', 'very high' (optional)",
                                },
                                "light": {
                                    "type": "string",
                                    "description": "Lighting: 'day', 'dusk', 'full moon', 'moonless', 'pitchblack' (optional)",
                                },
                                "weather": {
                                    "type": "string",
                                    "description": ("Weather: 'none', 'light rain', 'moderate rain', 'heavy rain', "
                                        "'gusting rain', 'downpour', 'light snow', 'moderate snow', 'heavy snow', "
                                        "'snow flurries', 'sleet', 'blizzard', 'ice storm' (optional)"),
                                },
                                "wind": {
                                    "type": "object",
                                    "description": ("Wind config: 'strength' (none/light gale/moderate gale/strong gale/storm/tornado/tornado f4), "
                                        "'direction' (N/NE/SE/S/SW/NW/random), 'shifting' (yes/no) (optional)"),
                                },
                                "fog": {
                                    "type": "string",
                                    "description": "Fog level: 'none', 'light', 'heavy' (optional)",
                                },
                                "blowingsand": {
                                    "type": "boolean",
                                    "description": "Enable blowing sand (optional)",
                                },
                                "emi": {
                                    "type": "boolean",
                                    "description": "Enable EMI effects (optional)",
                                },
                                "terrainchanges": {
                                    "type": "boolean",
                                    "description": "Enable terrain changes over time (optional, default: true)",
                                },
                                "environmental_rules": {
                                    "type": "array",
                                    "items": {"type": "string"},
                                    "description": (
                                        "Convenience environmental conditions: 'rain', 'light rain', 'heavy rain', "
                                        "'snow', 'blizzard', 'fog', 'dust', 'day', 'dusk', 'night'. "
                                        "These are parsed into proper MegaMek values. Explicit planetary conditions override."
                                    ),
                                },
                                # NEW: game options
                                "game_options": {
                                    "type": ["string", "object"],
                                    "description": (
                                        "Game options. String: path to mmconf/gameoptions.xml. "
                                        "Object: { 'file': 'path', 'on': ['double_blind', 'single_blind_bots'], 'off': ['tacops_fatigue'] }"
                                    ),
                                },
                                "singleplayer": {
                                    "type": "boolean",
                                    "description": "Skip dialogs and auto-connect to localhost server (default: true)",
                                },
                                # --- Force definitions ---
                                "player_force": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "unit": {
                                                "type": "string",
                                                "description": "Full unit name, e.g., 'Caesar CES-3R'",
                                            },
                                            "pilot_name": {
                                                "type": "string",
                                                "description": "Pilot name (default: 'Pilot N')",
                                            },
                                            "callsign": {
                                                "type": "string",
                                                "description": "Pilot callsign (optional)",
                                            },
                                            "skills": {
                                                "type": "string",
                                                "description": "Gunnery/Piloting skills, e.g., '3/4' (default: '4/5')",
                                            },
                                            "hits": {
                                                "type": "number",
                                                "description": "Pilot hits: 0-6 (optional)",
                                            },
                                            "portrait": {
                                                "type": "string",
                                                "description": "Portrait path relative to data/images/portraits (optional)",
                                            },
                                            "x": {"type": "number"},
                                            "y": {"type": "number"},
                                            "offboard": {
                                                "type": "string",
                                                "description": "Offboard entry direction: N, E, S, W (optional)",
                                            },
                                            "distance": {
                                                "type": "number",
                                                "description": "Offboard distance in hexes (default: 17)",
                                            },
                                            "facing": {
                                                "type": "number",
                                                "description": "Pre-deployed facing (0-11, 5=NW) (optional)",
                                            },
                                            "deploymentround": {
                                                "type": "number",
                                                "description": "Turn number when unit reinforces (optional)",
                                            },
                                            "status": {
                                                "type": "string",
                                                "description": "Initial status: prone, hidden, shutdown, hulldown (optional)",
                                            },
                                            "board": {
                                                "type": "number",
                                                "description": "Board number for multi-board scenarios (optional)",
                                            },
                                            "elevation": {
                                                "type": "number",
                                                "description": "Elevation for airborne ground units (optional)",
                                            },
                                            "altitude": {
                                                "type": "number",
                                                "description": "Altitude for aero units (optional)",
                                            },
                                            "force": {
                                                "type": "string",
                                                "description": ("Force chain: e.g., '2nd Sword of Light|21||Zakahashi's Zombies|22||Assault Lance|23' (optional)"),
                                            },
                                            "type": {
                                                "type": "string",
                                                "description": "Unit type: 'TW_UNIT' (default), 'ASElement' (optional)",
                                            },
                                            # NEW: pre-applied damage
                                            "remaining": {
                                                "type": "object",
                                                "description": (
                                                    "Pre-applied damage: { 'armor': { 'LT': 2, 'CTR': 0 }, "
                                                    "'internal': { 'LA': 2 }, 'structure': {...} }"
                                                ),
                                            },
                                            # NOTE: crits (equipment damage) are NOT supported in the schema.
                                            # They require knowing the unit's equipment layout.
                                            # If you reference a slot with no equipment, MegaMek crashes:
                                            #   Cannot invoke "megamek.common.equipment.Mounted.setDestroyed(boolean)"
                                            #   because "mounted" is null
                                            # Users who need crits should edit the .mms file manually.
                                            # "crits": { "type": "object", ... },  # NOT supported
                                            "ammo": {
                                                "type": "object",
                                                "description": (
                                                    "Ammo: { 'LA': { 'slot': 5, 'shots': 2, 'type': 'xyz'} } (optional)"
                                                ),
                                            },
                                            "bombs": {
                                                "type": ["object", "object"],
                                                "description": (
                                                    "Bombs for LAM/aero: direct { 'HE': 1 } or split { 'internal': {...}, 'external': {...} }. "
                                                    "Types: HE, CLUSTER, LG, RL, TAG, AAA, AS, ASEW, ARROW, HOMING, INFERNO, LAA, THUNDER, TORPEDO, ALAMO, FAE_SMALL, FAE_LARGE, RLP"
                                                ),
                                            },
                                        },
                                        "required": ["unit", "pilot_name", "skills"],
                                    },
                                },
                                "opfor_force": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "unit": {"type": "string"},
                                            "pilot_name": {"type": "string"},
                                            "callsign": {"type": "string"},
                                            "skills": {"type": "string"},
                                            "hits": {"type": "number"},
                                            "portrait": {"type": "string"},
                                            "x": {"type": "number"},
                                            "y": {"type": "number"},
                                            "offboard": {"type": "string"},
                                            "distance": {"type": "number"},
                                            "facing": {"type": "number"},
                                            "deploymentround": {"type": "number"},
                                            "status": {"type": "string"},
                                            "board": {"type": "number"},
                                            "elevation": {"type": "number"},
                                            "altitude": {"type": "number"},
                                            "force": {"type": "string"},
                                            "type": {"type": "string"},
                                            "remaining": {"type": "object"},
                                            # "crits": {"type": "object"},  # NOT supported — see NOTE above
                                            "ammo": {"type": "object"},
                                            "bombs": {"type": "object"},
                                        },
                                        "required": ["unit", "pilot_name", "skills"],
                                    },
                                },
                                # NEW: objects (carryable items)
                                "objects": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "name": {"type": "string"},
                                            "weight": {"type": "number"},
                                            "at": {"type": "array", "items": {"type": "number"}},
                                            "status": {"type": "string"},
                                            "owner": {"type": "string"},
                                        },
                                    },
                                    "description": (
                                        "Carryable objects (briefcases, crates). "
                                        "Each needs 'name' and 'weight'. Optional: 'at' (pre-deployed position), "
                                        "'status' (e.g., 'invulnerable'), 'owner' ('Player'/'OPFOR')"
                                    ),
                                },
                                # NEW: minefields per faction
                                "player_minefields": {
                                    "type": "object",
                                    "description": "Player minefields: { 'conventional': 2, 'command': 0, 'vibra': 2 } (optional)",
                                },
                                "opfor_minefields": {
                                    "type": "object",
                                    "description": "OPFOR minefields: { 'conventional': 2, 'command': 0, 'vibra': 2 } (optional)",
                                },
                                # NEW: team assignment (also controls faction colors in-game)
                                # Each unique team number gets a different color:
                                # Team 1 = blue, Team 2 = red, Team 3 = green, etc.
                                # Player and OPFOR default to teams 1 and 2 respectively.
                                "player_team": {
                                    "type": "number",
                                    "description": "Player team number (default: 1, blue). Units on this team share the same color.",
                                },
                                "opfor_team": {
                                    "type": "number",
                                    "description": "OPFOR team number (default: 2, red). Must differ from player_team for distinct colors.",
                                },
                                # NEW: bot settings
                                "player_bot": {
                                    "type": "object",
                                    "description": (
                                        "Player bot settings (Princess): { 'type': 'princess', 'selfpreservation': 5, "
                                        "'fallshame': 5, 'hyperaggression': 5, 'herdmentality': 5, 'bravery': 5, "
                                        "'forcedwithdrawal': true, 'withdrawto': 'south', 'flee': true, 'fleeto': 'south', "
                                        "'goHome': false, 'strategicBuildingTargets': [...], 'priorityUnitTargets': [...] }"
                                    ),
                                },
                                # Existing (kept for backward compat)
                                "battlefield_support_points": {
                                    "type": "object",
                                    "properties": {
                                        "player_bsp": {"type": "number"},
                                        "opfor_bsp": {"type": "number"},
                                    },
                                },
                                "princess_settings": {
                                    "type": "object",
                                    "description": (
                                        "Princess bot AI config for OPFOR. "
                                        "Keys: 'enabled' (bool), 'aggression' (aggressive/balanced/defensive), "
                                        "'selfpreservation' (0-10), 'fallshame' (0-10), 'hyperaggression' (0-10), "
                                        "'herdmentality' (0-10), 'bravery' (0-10), 'forcedwithdrawal' (bool), "
                                        "'withdrawto' (south/north/west/east/nearest), 'flee' (bool), "
                                        "'fleeto' (south/north/west/east/none), 'goHome' (bool), "
                                        "'strategicBuildingTargets' (list), 'priorityUnitTargets' (list)"
                                    ),
                                },
                                "deployment_zones": {
                                    "type": "object",
                                    "description": (
                                        "Deployment zones for each faction. "
                                        "Can specify 'edge' (N, E, S, W) or rectangular area with x1, y1, x2, y2."
                                    ),
                                    "properties": {
                                        "Player": {
                                            "type": "object",
                                            "properties": {
                                                "edge": {"type": "string"},
                                                "offset": {"type": "number"},
                                                "width": {"type": "number"},
                                                "x1": {"type": "number"},
                                                "y1": {"type": "number"},
                                                "x2": {"type": "number"},
                                                "y2": {"type": "number"},
                                            },
                                        },
                                        "OPFOR": {
                                            "type": "object",
                                            "properties": {
                                                "edge": {"type": "string"},
                                                "offset": {"type": "number"},
                                                "width": {"type": "number"},
                                                "x1": {"type": "number"},
                                                "y1": {"type": "number"},
                                                "x2": {"type": "number"},
                                                "y2": {"type": "number"},
                                            },
                                        },
                                    },
                                },
                                "player_camo": {
                                    "type": "string",
                                    "description": "Player faction camo image path (optional)",
                                },
                                "opfor_camo": {
                                    "type": "string",
                                    "description": "OPFOR faction camo image path (optional)",
                                },
                                # NEW: C3 networks
                                "c3_networks": {
                                    "type": "array",
                                    "description": (
                                        "C3 networks. List of unit ID arrays for C3i/C3S: [101, 102]. "
                                        "Or C3M objects: { 'c3m': 208, 'connected': [202, 203] }"
                                    ),
                                },
                                # NEW: transports
                                "transports": {
                                    "type": "object",
                                    "description": (
                                        "Transport relationships: { 'carrier_id': [carried_unit_ids] }. "
                                        "e.g., { '102': [104, 105] }"
                                    ),
                                },
                                # NEW: end conditions
                                "end_conditions": {
                                    "type": ["object", "array"],
                                    "description": (
                                        "Game end triggers (checked at end of round). "
                                        "Types: 'battlefieldcontrol', 'killedunits' (units, atLeast/atmost/count), "
                                        "'killedunit' (unit), 'activeunits' (units, count), 'fledunits' (units, count), "
                                        "'roundend' (round), 'roundstart' (round), 'phasestart' (phase), 'gamestart', "
                                        "'positions' (area, units, atLeast/atmost/count), 'position' (area, unit). "
                                        "Also supports 'and' and 'or' composite triggers with sub-triggers."
                                    ),
                                },
                                "game_options_file": {
                                    "type": "string",
                                    "description": "Path to mmconf/gameoptions.xml for custom game rules (optional, deprecated: use 'game_options')",
                                },
                                "victory_conditions": {
                                    "type": "object",
                                    "description": "Victory and game-end conditions (optional)",
                                    "properties": {
                                        "player_wins_on": {
                                            "type": "object",
                                            "properties": {
                                                "units": {"type": "array", "items": {"type": "number"}},
                                                "at_least": {"type": "number"},
                                            },
                                        },
                                        "opfor_wins_on": {
                                            "type": "object",
                                            "properties": {
                                                "units": {"type": "array", "items": {"type": "number"}},
                                                "at_least": {"type": "number"},
                                            },
                                        },
                                        "round_end": {
                                            "type": "number",
                                            "description": "Game ends after N rounds",
                                        },
                                    },
                                },
                                "messages": {
                                    "type": "array",
                                    "items": {
                                        "type": "object",
                                        "properties": {
                                            "header": {"type": "string"},
                                            "text": {"type": "string"},
                                            "image": {"type": "string"},
                                            "trigger": {"type": "object"},
                                        },
                                    },
                                },
                            },
                            "required": ["scenario_id", "player_force", "opfor_force"],
                        },
                    },
                    {
                        "name": "megamek:launch_megamek",
                        "description": (
                            "Returns instructions to load the generated .mms scenario "
                            "in MegaMek via the Scenario Chooser."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "scenario_id": {
                                    "type": "string",
                                    "description": "The unique identifier of the scenario to launch.",
                                }
                            },
                            "required": ["scenario_id"],
                        },
                    },
                    {
                        "name": "megamek:read_after_action_report",
                        "description": (
                            "Read a post-game results file and format it as an AAR. "
                            "If no results file exists, generates a template based on "
                            "the scenario config."
                        ),
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "scenario_id": {
                                    "type": "string",
                                    "description": "The unique identifier of the scenario.",
                                }
                            },
                            "required": ["scenario_id"],
                        },
                    },
                ],
            },
        }

    elif method == "tools/call":
        params = req.get("params", {})
        tool_name = params.get("name", "")
        arguments = params.get("arguments", {})

        if tool_name in ("megamek_initialize_game", "megamek:initialize_game"):
            result = tool_initialize_game(arguments)
        elif tool_name in ("megamek_launch_megamek", "megamek:launch_megamek"):
            result = tool_launch_megamek(arguments)
        elif tool_name in ("megamek_read_after_action_report", "megamek:read_after_action_report"):
            result = tool_read_after_action_report(arguments)
        else:
            return {
                "jsonrpc": "2.0",
                "id": req_id,
                "error": {"code": -32601, "message": f"Tool not found: {tool_name}"},
            }

        return {"jsonrpc": "2.0", "id": req_id, "result": result}

    return None


def main():
    log("MegaMek MCP Server v5.0.0 launched and waiting for standard I/O messages...")
    try:
        while True:
            line = sys.stdin.readline()
            if not line:
                break

            line = line.strip()
            if not line:
                continue

            try:
                req = json.loads(line)
            except json.JSONDecodeError as e:
                log(f"Invalid JSON received: {e}")
                continue

            res = handle_request(req)
            if res:
                sys.stdout.write(json.dumps(res) + "\n")
                sys.stdout.flush()

    except KeyboardInterrupt:
        log("Server shutting down via interrupt.")
    except Exception as e:
        log(f"Fatal error in main loop: {e}")


if __name__ == "__main__":
    main()
