#!/usr/bin/env python3
"""
helm_lore_filter.py

Searches the Helm MCP server's lore index via search_lore,
then filters results by a regex pattern applied to the lore text.
Optionally restricts the search to units matching era/faction filters
via find_units, intersecting that set with search_lore results.

Usage:
    python helm_lore_filter.py --era 3050 --filter "wargame|legend" [--tech_base Inner Sphere] [--source TR:3050] [--weight_class Heavy] [--output json|table] [--search-limit 100]

Requires:
    pip install mcp
"""

import argparse
import asyncio
import json
import re
import sys
from typing import Any

from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client


async def list_facets(session: ClientSession) -> dict:
    """Return the available filter dimensions and their legal values."""
    result = await session.call_tool("list_facets", {})
    return _extract(result)


async def find_units(session: ClientSession, **filters: Any) -> list[dict]:
    """Return all units matching the given filters."""
    result = await session.call_tool("find_units", {"by": filters.get("by", "by"), **{k: v for k, v in filters.items() if k != "by"}})
    data = _extract(result)
    return data.get("units", [])


async def get_all_units_for_era(session: ClientSession, **filters: Any) -> list[dict]:
    """Fetch all units matching the given filters (handles pagination)."""
    all_units: list[dict] = []
    offset = 0
    page_size = 100

    while True:
        result = await session.call_tool(
            "find_units",
            {"by": filters.get("by", "by"), "limit": page_size, "offset": offset, **filters},
        )
        data = _extract(result)
        units = data.get("units", [])
        all_units.extend(units)
        total = data.get("total_matched", 0)
        if len(units) == 0 or len(all_units) >= total:
            break
        offset += len(units)

    return all_units


async def search_lore(session: ClientSession, query: str, limit: int = 100) -> list[dict]:
    """Full-text search over lore for units matching the query text.

    Returns hits with snippets. Each hit carries a snippet: a match means
    the text mentions it, not that the unit belongs to it, so read the
    snippet (or call get_lore for the full text) before treating a hit as
    confirmed.
    """
    result = await session.call_tool("search_lore", {"query": query, "limit": limit})
    data = _extract(result)
    return data.get("hits", [])


def _extract(result: Any) -> dict:
    """Extract the dictionary from an MCP tool result."""
    if isinstance(result, dict):
        return result
    # MCP returns CallToolResult with content list
    if hasattr(result, "content") and result.content:
        for item in result.content:
            if hasattr(item, "text") and item.text:
                return json.loads(item.text)
    # Fallback: direct text attribute
    if hasattr(result, "text"):
        text = result.text
        if isinstance(text, str):
            return json.loads(text)
    return {}


async def filter_by_lore_regex(
    session: ClientSession,
    pattern: str,
    ignore_case: bool = True,
    limit: int = 100,
    era_filters: dict[str, Any] | None = None,
) -> list[dict]:
    """Use search_lore to find units whose lore matches the regex pattern.

    This is a full-text search over lore (overview, capabilities,
    deployment, history) for units matching the query text.
    """
    compiled = re.compile(pattern, re.IGNORECASE if ignore_case else 0)
    hits = await search_lore(session, pattern, limit)

    # Build a lookup of era-filtered names if filters provided
    filtered_names: set[str] | None = None
    if era_filters:
        print(f"[info] Resolving era/faction filters: {era_filters}", file=sys.stderr)
        units = await get_all_units_for_era(session, **era_filters)
        # Normalize find_units names: "Chassis (Model)" -> "Chassis Model"
        filtered_names = {u["name"].replace(" (", " ").replace(")", "") for u in units}
        print(f"[info] {len(filtered_names)} units match era/faction filters.", file=sys.stderr)

    # Collect unique names to look up via get_unit (for BV)
    seen: set[str] = set()
    unique_units: list[dict[str, str]] = []
    for hit in hits:
        chassis = hit.get("chassis", "")
        model = hit.get("model", "")
        # Construct name without parentheses: "Chassis Model" (what get_unit expects)
        name = f"{chassis} {model}".strip() if model else chassis

        if name not in seen:
            seen.add(name)
            unique_units.append({"name": name, "chassis": chassis, "model": model})

    # Fetch BV for each unique unit via get_unit
    bv_lookup: dict[str, int] = {}
    for u in unique_units:
        result = await session.call_tool("get_unit", {"name": u["name"]})
        data = _extract(result)
        if data.get("error"):
            continue
        bv = data.get("battle_value")
        if bv is not None:
            bv_lookup[u["name"]] = bv

    # Build final matches with BV attached
    matches: list[dict[str, Any]] = []
    for u in unique_units:
        entry: dict[str, Any] = {
            "name": u["name"],
            "chassis": u["chassis"],
            "model": u["model"],
        }
        if u["name"] in bv_lookup:
            entry["bv"] = bv_lookup[u["name"]]
        matches.append(entry)

    return matches


def _load_mcp_config() -> tuple[str, str] | None:
    """Load MCP config from ~/.pi/agent/mcp.json if available."""
    import os
    config_path = os.path.expanduser("~/.pi/agent/mcp.json")
    try:
        with open(config_path) as f:
            config = json.load(f)
        if "mcpServers" in config and "helm" in config["mcpServers"]:
            helm = config["mcpServers"]["helm"]
            return helm["command"], helm.get("args", ["/Users/a.imparato/helm/helm.sqlite"])[0]
    except (FileNotFoundError, json.JSONDecodeError, KeyError):
        pass
    return None


async def main_async() -> None:
    args = parse_args()

    # Connect to the Helm MCP server via stdio
    # Auto-detect from ~/.pi/agent/mcp.json if available
    config = _load_mcp_config()
    helm_binary = args.helm_binary or (config[0] if config else "/Users/a.imparato/helm/target/release/helm-mcp")
    helm_db = args.helm_db or (config[1] if config else "/Users/a.imparato/helm/helm.sqlite")

    server_params = StdioServerParameters(
        command=helm_binary,
        args=[helm_db],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 1. List facets (optional diagnostic)
            facets = await list_facets(session)
            print(f"[info] Available facets: {json.dumps(facets, indent=2)[:500]}...", file=sys.stderr)

            # 2. Build era/faction filters
            era_filters: dict[str, Any] = {}
            if args.era:
                era_filters["year_max"] = args.era
            if args.tech_base:
                era_filters["tech_base"] = [args.tech_base]
            if args.source:
                era_filters["source"] = [args.source]
            if args.weight_class:
                era_filters["weight_class"] = [args.weight_class]

            # 3. Search lore (optionally intersected with era/faction filters)
            print(f"[info] Searching lore by regex: {args.filter!r}...", file=sys.stderr)
            matches = await filter_by_lore_regex(
                session,
                args.filter,
                args.ignore_case,
                args.search_limit,
                era_filters if era_filters else None,
            )
            print(f"[info] {len(matches)} units have matching lore.", file=sys.stderr)

            if not matches:
                print("[warn] No lore matches found. Exiting.", file=sys.stderr)
                return

            # 3. Output
            filter_header = f"pattern: {args.filter!r}"
            if era_filters:
                filter_header += f", filters: {era_filters}"

            if args.output == "json":
                print(json.dumps(matches, indent=2))
            else:
                print(f"\n{'='*80}")
                print(f"  Helm Lore Filter Results  ({filter_header})")
                print(f"{'='*80}\n")
                for m in matches:
                    bv = m.get("bv", "N/A")
                    print(f"  {m['name']}  (BV: {bv})")
                    print()


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Search Helm MCP lore by regex pattern via search_lore, "
                    "optionally restricted by era/faction filters via find_units.",
    )
    parser.add_argument("--helm-binary", default=None, help="Path to helm-mcp binary (default: ~/.pi/agent/mcp.json)")
    parser.add_argument("--helm-db", default=None, help="Path to helm.sqlite database (default: ~/.pi/agent/mcp.json)")
    parser.add_argument("--era", type=int, default=None, help="Year max (year_max) — e.g. 3050")
    parser.add_argument("--tech_base", default=None, help="Filter by tech base (array in JSON)")
    parser.add_argument("--source", default=None, help="Filter by source MUL (array in JSON)")
    parser.add_argument("--weight_class", default=None, help="Filter by weight class (array in JSON)")
    parser.add_argument("--filter", required=True, help="Regex/text pattern to search in lore descriptions")
    parser.add_argument("--ignore-case", action="store_true", default=True, help="Case-insensitive regex matching")
    parser.add_argument("--output", choices=["json", "table"], default="json", help="Output format (default: json)")
    parser.add_argument("--search-limit", type=int, default=100, help="Max search_lore results (default: 100)")
    return parser.parse_args()


def main() -> None:
    try:
        asyncio.run(main_async())
    except Exception as e:
        print(f"[error] {e}", file=sys.stderr)
        sys.exit(1)


if __name__ == "__main__":
    main()
