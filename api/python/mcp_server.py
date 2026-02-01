"""MCP server for Path of Building PoE2.

Provides tools for Claude Desktop (or any MCP client) to interact with
the PoB calculation engine via a persistent LuaJIT subprocess.
"""

import argparse
import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from .config import DEFAULT_HOST, DEFAULT_PORT
from .lua_bridge import LuaBridge, LuaBridgeError

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Path of Building PoE2",
    instructions="Tools for creating, modifying, and analyzing Path of Exile 2 builds using Path of Building",
    host="0.0.0.0",
)

# Global bridge instance, initialized on first use
_bridge: LuaBridge | None = None


def get_bridge() -> LuaBridge:
    """Get or create the global LuaBridge instance."""
    global _bridge
    if _bridge is None:
        _bridge = LuaBridge()
    if not _bridge.is_running:
        _bridge.start()
    return _bridge


def call(command: str, params: dict | None = None) -> dict:
    """Call a bridge command, returning the result dict."""
    return get_bridge().send_command(command, params)


def format_result(result: dict) -> str:
    """Format a result dict as readable JSON."""
    return json.dumps(result, indent=2, default=str)


# ============================================================================
# Build tools
# ============================================================================

@mcp.tool()
def new_build() -> str:
    """Create a new empty build. This resets all skills, items, and tree allocations."""
    result = call("new_build")
    return "New build created successfully."


@mcp.tool()
def load_build_xml(xml: str, name: str = "Imported Build") -> str:
    """Load a build from its XML representation.

    Args:
        xml: The full build XML content (as exported from Path of Building)
        name: A name for the build
    """
    call("load_build_xml", {"xml": xml, "name": name})
    info = call("get_build_info")
    return f"Build loaded: {info.get('buildName', name)}\n" + format_result(info)


@mcp.tool()
def get_build_info() -> str:
    """Get current build information including class, level, and ascendancy."""
    result = call("get_build_info")
    return format_result(result)


@mcp.tool()
def export_build_xml() -> str:
    """Export the current build as XML that can be shared or imported into Path of Building."""
    result = call("get_build_xml")
    return result.get("xml", "")


# ============================================================================
# Tree tools
# ============================================================================

@mcp.tool()
def alloc_node(node_id: int) -> str:
    """Allocate a passive tree node by its ID. This also allocates any nodes along the path to it.

    Args:
        node_id: The numeric ID of the passive tree node to allocate
    """
    result = call("alloc_node", {"node_id": node_id})
    if result.get("already_allocated"):
        return f"Node {node_id} was already allocated."
    return f"Node {node_id} allocated successfully."


@mcp.tool()
def dealloc_node(node_id: int) -> str:
    """Deallocate a passive tree node. Dependent nodes are also deallocated.

    Args:
        node_id: The numeric ID of the passive tree node to deallocate
    """
    result = call("dealloc_node", {"node_id": node_id})
    if result.get("already_deallocated"):
        return f"Node {node_id} was already deallocated."
    return f"Node {node_id} deallocated successfully."


@mcp.tool()
def get_allocated_nodes() -> str:
    """List all currently allocated passive tree nodes."""
    result = call("list_alloc_nodes")
    nodes = result.get("nodes", [])
    if not nodes:
        return "No nodes are currently allocated."
    return format_result(nodes)


@mcp.tool()
def search_nodes(query: str, max_results: int = 30) -> str:
    """Search for passive tree nodes by name.

    Args:
        query: Text to search for in node names (case-insensitive)
        max_results: Maximum number of results to return (default 30)
    """
    result = call("search_nodes", {"query": query, "max_results": max_results})
    nodes = result.get("nodes", [])
    if not nodes:
        return f"No nodes found matching '{query}'."
    return format_result(nodes)


@mcp.tool()
def get_node_info(node_id: int) -> str:
    """Get detailed information about a specific passive tree node.

    Args:
        node_id: The numeric ID of the passive tree node
    """
    result = call("get_node_info", {"node_id": node_id})
    return format_result(result)


# ============================================================================
# Item tools
# ============================================================================

@mcp.tool()
def list_items() -> str:
    """List all items currently in the build."""
    result = call("list_items")
    items = result.get("items", [])
    if not items:
        return "No items in the build."
    return format_result(items)


@mcp.tool()
def get_item_details(item_id: int) -> str:
    """Get detailed information about a specific item in the build.
    
    Args:
        item_id: The ID of the item (from list_items)
    
    Returns full item data including:
    - Base stats (armour, weapon damage, etc.)
    - Quality, item level, corruption status
    - All mods: implicits, explicits, enchants, runes
    - Equipment slot if equipped
    """
    result = call("get_item_details", {"item_id": item_id})
    return format_result(result)


@mcp.tool()
def search_base_items(query: str, item_type: str | None = None, max_results: int = 50) -> str:
    """Search for item base types (e.g., "Greathelm", "Staff").
    
    Args:
        query: Text to search for in base item names (case-insensitive)
        item_type: Optional filter by item type/category (e.g., "Helmet", "Staff")
        max_results: Maximum number of results to return (default 50)
    """
    params = {"query": query, "max_results": max_results}
    if item_type:
        params["type"] = item_type
    result = call("search_base_items", params)
    items = result.get("items", [])
    if not items:
        return f"No base items found matching '{query}'."
    return format_result(items)


@mcp.tool()
def get_base_item_types() -> str:
    """List all available item base type categories (e.g., Helmet, Staff, Amulet)."""
    result = call("get_base_item_types")
    types = result.get("types", [])
    if not types:
        return "No item types found."
    return format_result(types)


@mcp.tool()
def get_base_item_details(name: str) -> str:
    """Get detailed information about a specific base item.
    
    Args:
        name: The exact name of the base item (e.g., "Rusted Greathelm")
    """
    result = call("get_base_item_details", {"name": name})
    return format_result(result)


@mcp.tool()
def search_unique_items(query: str, item_type: str | None = None, max_results: int = 50) -> str:
    """Search for unique items by name or base type.
    
    Args:
        query: Text to search for in unique item names (case-insensitive)
        item_type: Optional filter by item type (e.g., "helmet", "sword")
        max_results: Maximum number of results to return (default 50)
    """
    params = {"query": query, "max_results": max_results}
    if item_type:
        params["type"] = item_type
    result = call("search_unique_items", params)
    uniques = result.get("uniques", [])
    if not uniques:
        return f"No unique items found matching '{query}'."
    return format_result(uniques)


@mcp.tool()
def get_unique_item_details(name: str) -> str:
    """Get detailed information about a specific unique item.
    
    Args:
        name: The exact name of the unique item (e.g., "Black Sun Crest")
    """
    result = call("get_unique_item_details", {"name": name})
    return format_result(result)


@mcp.tool()
def add_item(item_raw: str, slot: str | None = None) -> str:
    """Add an item to the build from its text representation.

    Args:
        item_raw: Item text in the game's copy-paste format (e.g., from Ctrl+C on an item in-game)
        slot: Optional equipment slot to equip it to (e.g., "Helmet", "Weapon 1", "Ring 1")
    """
    params: dict = {"item_raw": item_raw}
    if slot:
        params["slot"] = slot
    result = call("add_item", params)
    msg = f"Item added (ID: {result.get('item_id', '?')})."
    if slot:
        msg += f" Equipped to {slot}."
    return msg


@mcp.tool()
def equip_item(item_id: int, slot: str) -> str:
    """Equip an existing item to a specific equipment slot.

    Args:
        item_id: The ID of the item (from list_items)
        slot: The equipment slot name (e.g., "Helmet", "Weapon 1", "Ring 1", "Body Armour")
    """
    call("equip_item", {"item_id": item_id, "slot": slot})
    return f"Item {item_id} equipped to {slot}."


@mcp.tool()
def list_slots() -> str:
    """List all equipment slots and what items are currently equipped in them."""
    result = call("list_slots")
    return format_result(result.get("slots", []))


# ============================================================================
# Skill tools
# ============================================================================

@mcp.tool()
def list_skills() -> str:
    """List all skill gem groups in the build."""
    result = call("list_skills")
    skills = result.get("skills", [])
    if not skills:
        return "No skills in the build."
    return format_result(skills)


@mcp.tool()
def add_skill(skill_text: str) -> str:
    """Add a skill gem group to the build.

    Args:
        skill_text: Skill group in paste format. Example:
            Label: My Attack Setup
            Fireball 20/0 1
            Combustion Support 20/0 1

            Format per gem line: "GemName level/quality [count]"
    """
    result = call("add_skill", {"skill_text": skill_text})
    return (
        f"Skill group added at index {result.get('index', '?')} "
        f"with {result.get('gem_count', '?')} gems."
    )


@mcp.tool()
def set_main_skill(index: int) -> str:
    """Set which skill gem group is the main (active) skill for DPS calculations.

    Args:
        index: 1-based index of the skill group (from list_skills)
    """
    call("set_main_skill", {"index": index})
    return f"Main skill set to group {index}."


# ============================================================================
# Calculation tools
# ============================================================================

@mcp.tool()
def get_stats(keys: list[str] | None = None) -> str:
    """Get calculated build statistics (DPS, life, resistances, etc.).

    Args:
        keys: Optional list of specific stat keys to retrieve. If omitted, returns
              curated important stats. Common keys include: TotalDPS, CombinedDPS,
              FullDPS, Life, EnergyShield, Mana, FireResist, ColdResist,
              LightningResist, ChaosResist, Armour, Evasion, TotalEHP, Speed, etc.
    """
    params = {}
    if keys:
        params["stats"] = keys
    result = call("get_output", params if params else None)
    return format_result(result)


@mcp.tool()
def get_full_stats() -> str:
    """Get the complete calculation output with all available stats. This can be very large."""
    result = call("get_full_output")
    return format_result(result)


@mcp.tool()
def get_stat(key: str) -> str:
    """Retrieve a specific stat value from the full calculation output.
    
    Args:
        key: The stat key name (e.g., "TotalDPS", "Life", "CritChance", "Speed")
    
    Returns the value of that specific stat. Use this instead of get_full_stats
    when you only need one or a few specific values to avoid flooding the context.
    """
    result = call("get_stat", {"key": key})
    if not result.get("found"):
        return f"Stat '{key}' not found."
    value = result.get("value")
    if result.get("type") == "table":
        table_data = value if isinstance(value, dict) else {}
        return f"{key} (table with {result.get('table_size', '?')} entries): {format_result(table_data)}"
    return f"{key}: {value}"


@mcp.tool()
def get_stats_list(keys: list[str]) -> str:
    """Retrieve multiple specific stats at once from the calculation output.
    
    Args:
        keys: List of stat key names to retrieve (e.g., ["TotalDPS", "Life", "Speed"])
    
    Returns multiple stat values in a single call. More efficient than calling
    get_stat multiple times when you need several stats.
    """
    result = call("get_stats_list", {"keys": keys})
    found = result.get("found", {})
    not_found = result.get("not_found", [])
    
    output = []
    output.append(f"Retrieved {result.get('found_count', 0)}/{result.get('count', 0)} stats:\n")
    
    for key, data in found.items():
        value = data.get("value")
        if data.get("type") == "table":
            table_data = value if isinstance(value, dict) else {}
            output.append(f"{key} (table): {format_result(table_data)}")
        else:
            output.append(f"{key}: {value}")
    
    if not_found:
        output.append(f"\nNot found: {', '.join(not_found)}")
    
    return "\n".join(output)


# ============================================================================
# Config tools
# ============================================================================

@mcp.tool()
def set_config(key: str, value: str | int | float | bool) -> str:
    """Set a configuration option for the build (e.g., enemy type, conditions).

    Args:
        key: Configuration key name (e.g., "enemyIsBoss", "conditionStationary")
        value: Value to set (string, number, or boolean depending on the option)
    """
    call("set_config", {"key": key, "value": value})
    return f"Config '{key}' set to {value!r}."


@mcp.tool()
def set_custom_mods(mods: str) -> str:
    """Set custom modifiers on build. These are applied as additional modifiers.

    Args:
        mods: Custom modifier text, one modifier per line. Example:
              "10% increased Attack Speed\\n20% increased Physical Damage"
    """
    call("set_custom_mods", {"mods": mods})
    return "Custom mods applied."


# ============================================================================
# File management tools
# ============================================================================

@mcp.tool()
def list_builds(sub_path: str = "") -> str:
    """List saved builds with their metadata.

    Args:
        sub_path: Optional subdirectory within builds folder to list
    """
    result = call("list_builds", {"sub_path": sub_path})
    builds = result.get("builds", [])
    folders = result.get("folders", [])
    
    output = []
    if folders:
        output.append("Folders:")
        for folder in folders:
            output.append(f"  📁 {folder['name']}")
        output.append("")
    
    if builds:
        output.append("Builds:")
        for build in builds:
            class_info = ""
            if build.get("className"):
                class_info = f" ({build['className']}"
                if build.get("ascendClassName"):
                    class_info += f" / {build['ascendClassName']}"
                class_info += f", Level {build['level']})"
            output.append(f"  📄 {build['name']}{class_info}")
    else:
        output.append("No builds found.")
    
    return "\n".join(output)


@mcp.tool()
def load_build_file(path: str) -> str:
    """Load a build from its file path.

    Args:
        path: Full path to the build .xml file
    """
    call("load_build_file", {"path": path})
    info = call("get_build_info")
    build_name = info.get("buildName", "Unknown")
    class_name = info.get("className", "Unknown")
    level = info.get("level", "Unknown")
    
    return f"Build loaded: {build_name}\nClass: {class_name} (Level {level})"


@mcp.tool()
def save_build() -> str:
    """Save the current build to its existing file."""
    call("save_build")
    return "Build saved successfully."


@mcp.tool()
def save_build_as(name: str, sub_path: str = "") -> str:
    """Save the current build to a new file.

    Args:
        name: Name for the new build file (without .xml extension)
        sub_path: Optional subdirectory within builds folder
    """
    result = call("save_build_as", {"name": name, "sub_path": sub_path})
    return f"Build saved as: {result.get('path', 'Unknown')}"


@mcp.tool()
def delete_build_file(path: str) -> str:
    """Delete a build file.

    Args:
        path: Full path to the build .xml file to delete
    """
    call("delete_build_file", {"path": path})
    return f"Build file deleted: {path}"


@mcp.tool()
def create_builds_folder(name: str, sub_path: str = "") -> str:
    """Create a subfolder in the builds directory.

    Args:
        name: Name for the new folder
        sub_path: Optional parent subdirectory within builds folder
    """
    result = call("create_folder", {"name": name, "sub_path": sub_path})
    return f"Folder created: {result.get('path', 'Unknown')}"


@mcp.tool()
def rename_build_file(old_path: str, new_name: str) -> str:
    """Rename a build file.

    Args:
        old_path: Full path to the current build file
        new_name: New name for the file (without .xml extension)
    """
    result = call("rename_build_file", {"old_path": old_path, "new_name": new_name})
    return f"Build renamed to: {result.get('new_path', 'Unknown')}"


def run_server():
    """Run the MCP server with configurable transport (stdio or HTTP streaming)."""
    parser = argparse.ArgumentParser(
        description="Path of Building PoE2 MCP Server",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Transport modes:
  stdio          - Standard input/output mode (default, for Claude Desktop)
  sse            - HTTP streaming with Server-Sent Events

Examples:
  %(prog)s                          # Run in stdio mode (default)
  %(prog)s --transport sse          # Run HTTP streaming on default port
  %(prog)s --transport sse --port 8080 --host 0.0.0.0
        """,
    )
    parser.add_argument(
        "--transport",
        choices=["stdio", "sse"],
        default="stdio",
        help="Transport mode: 'stdio' for standard input/output, 'sse' for HTTP streaming (default: stdio)",
    )
    parser.add_argument(
        "--host",
        default=DEFAULT_HOST,
        help=f"Host to bind HTTP server to when using sse transport (default: {DEFAULT_HOST})",
    )
    parser.add_argument(
        "--port",
        type=int,
        default=DEFAULT_PORT,
        help=f"Port to bind HTTP server to when using sse transport (default: {DEFAULT_PORT})",
    )
    parser.add_argument(
        "--log-level",
        default="INFO",
        choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Logging level (default: INFO)",
    )

    args = parser.parse_args()

    # Configure logging
    logging.basicConfig(
        level=getattr(logging, args.log_level),
        format="%(asctime)s [%(name)s] %(levelname)s: %(message)s",
        stream=sys.stderr,
    )

    if args.transport == "stdio":
        logger.info("Starting MCP server in stdio mode")
        mcp.run(transport="stdio")
    elif args.transport == "sse":
        import uvicorn
        app = mcp.sse_app()
        logger.info(f"Starting MCP server in HTTP streaming mode on {args.host}:{args.port}")
        #mcp.run(transport="sse", host=args.host, port=args.port)
        uvicorn.run(app, host=args.host, port=args.port)
    else:
        parser.error(f"Unknown transport: {args.transport}")
