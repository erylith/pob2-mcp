"""MCP server for Path of Building PoE2.

Provides tools for Claude Desktop (or any MCP client) to interact with
the PoB calculation engine via a persistent LuaJIT subprocess.
"""

import argparse
import atexit
import json
import logging
import sys

from mcp.server.fastmcp import FastMCP

from .bridge_pool import LuaBridgePool
from .config import BRIDGE_POOL_MAX_BUILDS, DEFAULT_HOST, DEFAULT_PORT
from .lua_bridge import LuaBridgeError

logger = logging.getLogger(__name__)

mcp = FastMCP(
    "Path of Building PoE2",
    instructions="Tools for creating, modifying, and analyzing Path of Exile 2 builds using Path of Building",
    host="0.0.0.0",
)

# Global bridge pool, initialized on first use
_pool: LuaBridgePool | None = None

class ChatGPTAuthMiddleware:
    def __init__(self, inner_app, token: str):
        self.inner_app = inner_app
        self.expected_auth = f"Bearer {token}"

    async def __call__(self, scope, receive, send):
        # Only intercept standard HTTP requests (skip lifespan or websocket scopes)
        if scope["type"] == "http":
            headers = dict(scope.get("headers", []))
            # ASGI headers are stored as raw bytes, so look up b"authorization"
            auth_header = headers.get(b"authorization", b"").decode("utf-8")
            
            if auth_header != self.expected_auth:
                # Instantly slam the door with a 401 Unauthorized
                await send({
                    "type": "http.response.start",
                    "status": 401,
                    "headers": [(b"content-type", b"application/json")],
                })
                await send({
                    "type": "http.response.body",
                    "body": b'{"detail": "Unauthorized: Missing or invalid token."}',
                })
                return
                
        # Valid token (or non-HTTP payload). Hand execution off to FastMCP.
        await self.inner_app(scope, receive, send)

def get_pool() -> LuaBridgePool:
    """Get or create the global LuaBridgePool instance."""
    global _pool
    if _pool is None:
        _pool = LuaBridgePool(max_builds=BRIDGE_POOL_MAX_BUILDS)
        atexit.register(_pool.shutdown_all)
    return _pool


def call(command: str, params: dict | None = None) -> dict:
    """Call a bridge command on the active build, returning the result dict."""
    return get_pool().call(command, params)


def format_result(result: dict) -> str:
    """Format a result dict as readable JSON."""
    return json.dumps(result, indent=2, default=str)


# ============================================================================
# Build tools
# ============================================================================

@mcp.tool()
def new_build(name: str = "New Build") -> str:
    """Create a new empty build and make it the active build in the pool.

    Args:
        name: A name for this build in the pool (default: 'New Build')
    """
    get_pool().load_build(name, new=True)
    return f"New build '{name}' created and set as active."


@mcp.tool()
def load_build_xml(xml: str, name: str = "Imported Build") -> str:
    """Load a build from its XML representation and make it the active build in the pool.

    Args:
        xml: The full build XML content (as exported from Path of Building)
        name: A name for this build in the pool
    """
    get_pool().load_build(name, xml=xml)
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
def dump_item_fields(item_id: int) -> str:
    """Debug: dump all scalar fields on a raw Lua item object.

    Use this to discover the actual field names available on an item —
    tables are shown as '<table>', functions as '<function>'.

    Args:
        item_id: The ID of the item (from list_items)
    """
    result = call("dump_item_fields", {"item_id": item_id})
    return format_result(result.get("fields", {}))


@mcp.tool()
def get_all_equipped_items() -> str:
    """Return full details for every equipped item in a single call.

    Equivalent to calling get_item_details on each result from list_items
    that has an equippedSlot, but in one round-trip. Each item includes
    base stats, mods (implicits, explicits, enchants), socketed rune/idol
    names, rune effects, socket counts, and the slot it occupies.
    """
    result = call("get_all_equipped_items")
    items = result.get("items", [])
    if not items:
        return "No equipped items found."
    return format_result(items)


@mcp.tool()
def get_item_impact(item_id: int, stats: list[str] | None = None) -> str:
    """Show the stat impact of an equipped item by temporarily unequipping it and diffing.

    Unequips the item, captures the stat delta, then re-equips it — all in one
    call. Only returns stats that actually changed. Each changed stat shows the
    value with the item, without it, and the difference.

    Args:
        item_id: ID of an equipped item (from list_items or get_all_equipped_items)
        stats:   Optional list of specific stat keys to evaluate. Defaults to the
                 standard curated stat set (DPS, life, resists, EHP, etc.)
    """
    params: dict = {"item_id": item_id}
    if stats:
        params["stats"] = stats
    result = call("get_item_impact", params)
    return format_result(result)


@mcp.tool()
def get_all_equipped_items_impact(stats: list[str] | None = None) -> str:
    """Show the stat impact of every equipped item, evaluated one at a time.

    For each equipped item, temporarily unequips it (with all others still on),
    diffs the stats, then re-equips before moving to the next. Only changed
    stats are returned per item.

    Args:
        stats: Optional list of specific stat keys to evaluate. Defaults to the
               standard curated stat set (DPS, life, resists, EHP, etc.)
    """
    params: dict = {}
    if stats:
        params["stats"] = stats
    result = call("get_all_equipped_items_impact", params if params else None)
    items = result.get("items", [])
    if not items:
        return "No equipped items found."
    return format_result(items)


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


@mcp.tool()
def get_minion_stats(keys: list[str] | None = None) -> str:
    """Get calculated stats for the minion of the current main skill.

    Returns damage, survivability, and defensive stats for the minion associated
    with the active skill (e.g. Raise Skeleton, Summon Wolf). Returns a message
    if the current main skill has no minion.

    Args:
        keys: Optional list of specific stat keys to retrieve. If omitted, returns
            curated minion stats. Common keys: CombinedDPS, TotalDPS, TotalDot,
            WithDotDPS, BleedDPS, IgniteDPS, PoisonDPS, DecayDPS, TotalDotDPS,
            Life, EnergyShield, LifeRegenRecovery, FireResist, ColdResist,
            LightningResist, ChaosResist, Armour, Evasion, CritChance, CritMultiplier
    """
    params = {}
    if keys:
        params["keys"] = keys
    result = call("get_minion_stats", params if params else None)
    if not result.get("has_minion"):
        return "No minion associated with the current main skill."
    result.pop("has_minion", None)
    return format_result(result)


@mcp.tool()
def search_modifiers(query: str, mod_type: str = "Item", max_results: int = 30) -> str:
    """Search for modifier groups by name, affix, or effect text.
    
    Args:
        query: Search text to find modifiers (e.g., "life", "resist", "damage")
        mod_type: Type of modifiers to search ("Item", "Flask", "Charm", "Jewel", "Corruption")
        max_results: Maximum number of modifier groups to return
    
    Returns modifier groups with tier count and basic info. Use get_modifier_tiers
    to see all tiers for a specific group.
    """
    result = call("search_modifiers", {"query": query, "mod_type": mod_type, "max_results": max_results})
    groups = result.get("groups", [])
    if not groups:
        return f"No modifiers found matching '{query}' in {mod_type}."
    return format_result(groups)


@mcp.tool()
def get_modifier_tiers(group: str, mod_type: str = "Item") -> str:
    """Get all tiers for a specific modifier group with their ranges and requirements.
    
    Args:
        group: The modifier group name (e.g., "LifeRegeneration", "Strength", "FireResistance")
        mod_type: Type of modifiers ("Item", "Flask", "Charm", "Jewel", "Corruption")
    
    Returns all tiers sorted from lowest (tier 1) to highest, showing:
    - Tier number and affix name
    - Stat ranges (e.g., "+(5-8) to Strength")
    - Required item level
    - Which item types can roll it
    """
    result = call("get_modifier_tiers", {"group": group, "mod_type": mod_type})
    tiers = result.get("tiers", [])
    if not tiers:
        return f"No tiers found for group '{group}' in {mod_type}."
    
    output = [f"Modifier Group: {group} ({len(tiers)} tiers)\n"]
    for tier in tiers:
        output.append(f"T{tier['tier']}: {tier['affix']} (Level {tier['level']})")
        output.append(f"  {tier['mod_text']}")
        if tier.get('mod_tags'):
            output.append(f"  Tags: {', '.join(tier['mod_tags'])}")
        output.append("")
    
    return "\n".join(output)


@mcp.tool()
def get_modifiers_for_item_type(item_type: str, mod_type: str = "Item", 
                                affix_type: str | None = None, max_results: int = 50) -> str:
    """Get all modifiers that can roll on a specific item type.
    
    Args:
        item_type: The item type tag (e.g., "helmet", "ring", "body_armour", "bow", "sword")
                Supports partial matching: "sword" matches "sword", "two_hand_sword", etc.
        mod_type: Type of modifiers ("Item", "Flask", "Charm", "Jewel", "Corruption")
        affix_type: Filter by "Prefix" or "Suffix" (default: both)
        max_results: Maximum number of modifiers to return
    
    Returns all modifier groups available on that item type, sorted by level.
    Use get_modifier_tiers to see the full tier breakdown for any group.
    
    Tip: Use get_item_modifier_tags() to see all available item type tags,
    or search_item_types() to find which tag to use for your item.
    """
    params = {
        "item_type": item_type,
        "mod_type": mod_type,
        "max_results": max_results
    }
    if affix_type:
        params["affix_type"] = affix_type
    
    result = call("get_modifiers_for_item_type", params)
    modifiers = result.get("modifiers", [])
    if not modifiers:
        filter_text = f" {affix_type.lower()}" if affix_type else ""
        return f"No{filter_text} modifiers found for item type '{item_type}' in {mod_type}. Try using search_item_types() to find the correct tag."
    return format_result(modifiers)


@mcp.tool()
def get_modifier_types() -> str:
    """List all available modifier type categories.
    
    Returns the different modifier databases available for querying:
    - Item: Regular item modifiers (prefixes/suffixes)
    - Flask: Flask modifiers
    - Charm: Charm modifiers
    - Jewel: Jewel-specific modifiers
    - Corruption: Corrupted modifiers
    - Runes: Rune modifiers
    - IncursionLimb: Incursion limb modifiers
    - Exclusive: Exclusive/special modifiers
    
    Use these type names with search_modifiers, get_modifier_tiers, and
    get_modifiers_for_item_type functions.
    """
    result = call("get_modifier_types")
    types = result.get("types", [])
    if not types:
        return "No modifier types found."
    return format_result(types)


@mcp.tool()
def get_item_modifier_tags(mod_type: str = "Item") -> str:
    """List all item type tags that can have modifiers.
    
    Args:
        mod_type: Type of modifiers to check ("Item", "Flask", "Charm", "Jewel", "Corruption")
    
    Returns all unique item type tags found in the modifier database.
    These tags are used with get_modifiers_for_item_type() to query which
    modifiers can roll on specific item types.
    
    Common tags include:
    - Armour: helmet, body_armour, gloves, boots, shield
    - Weapons: sword, mace, axe, bow, staff, wand, dagger, claw
    - Accessories: ring, amulet, belt, quiver
    - Special: str_armour, dex_armour, int_armour (attribute-based armour)
    """
    result = call("get_item_modifier_tags", {"mod_type": mod_type})
    tags = result.get("tags", [])
    if not tags:
        return f"No modifier tags found for {mod_type}."
    return format_result(tags)


@mcp.tool()
def search_item_types(query: str, max_results: int = 50) -> str:
    """Search for item types by name or category.
    
    Args:
        query: Search term to find item types (e.g., "sword", "armour", "ring")
        max_results: Maximum number of item types to return
    
    Returns matching item types with example base items and their tags.
    This helps you find the correct item_type tag to use with 
    get_modifiers_for_item_type().
    
    Example: search_item_types("sword") returns:
    - "One Handed Sword" with tags
    - "Two Handed Sword" with tags
    etc.
    """
    result = call("search_item_types", {"query": query, "max_results": max_results})
    types = result.get("types", [])
    if not types:
        return f"No item types found matching '{query}'."
    
    output = [f"Found {len(types)} item type(s) matching '{query}':\n"]
    for item_type in types:
        output.append(f"Type: {item_type['type']}")
        output.append(f"  Example base: {item_type['example_base']}")
        if item_type.get('tags'):
            tags_str = ", ".join(item_type['tags'][:10])  # Limit tags shown
            if len(item_type['tags']) > 10:
                tags_str += f" (+{len(item_type['tags']) - 10} more)"
            output.append(f"  Tags: {tags_str}")
        output.append("")
    
    return "\n".join(output)


# ============================================================================
# Build flag / condition tools
# ============================================================================

@mcp.tool()
def check_flag(flag: str) -> str:
    """Check whether a build flag or condition is active for the current character.

    Uses the fully-resolved post-calculation modDB, so it reflects passives,
    items, and all other sources — the same way PoB evaluates conditions internally.

    Args:
        flag: The flag name to check. Examples:
            "Condition:CanUseBondedModifiers"  — character can use Bonded idol/rune effects
            "Condition:CanUseBondedModifiers" requires the passive
            "Condition:CanSprint", "Condition:Fortified", etc.

    Returns whether the flag is true or false for the loaded build.
    """
    result = call("check_flag", {"flag": flag})
    value = result.get("value", False)
    return f"{flag}: {value}"


# ============================================================================
# Config tools
# ============================================================================

@mcp.tool()
def list_config_options() -> str:
    """List all configuration options that are applicable to the current build.

    Only returns options whose conditions are met (same visibility logic as the
    PoB UI — e.g. buff toggles only appear if the build can actually use them).

    Each option includes:
    - var:   the key to pass to set_config
    - type:  "check" (bool toggle), "count" (integer), or "list" (enum)
    - label: human-readable description
    - value: current setting (None means using default)
    """
    result = call("list_config_options")
    options = result.get("options", [])
    if not options:
        return "No applicable config options for this build."
    return format_result(options)


@mcp.tool()
def set_config(key: str, value: str | int | float | bool) -> str:
    """Set a configuration option for the build (e.g., enemy type, conditions).

    Use list_config_options to see what's available and the var names to use.

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
    """Load a build from its file path and make it the active build in the pool.

    The filename (without .xml) is used as the build's pool name.

    Args:
        path: Full path to the build .xml file
    """
    from pathlib import Path as _Path
    name = _Path(path).stem
    get_pool().load_build(name, path=path)
    info = call("get_build_info")
    build_name = info.get("buildName", "Unknown")
    class_name = info.get("className", "Unknown")
    level = info.get("level", "Unknown")
    return f"Build loaded: {build_name} (pool name: '{name}')\nClass: {class_name} (Level {level})"


# ============================================================================
# Pool management tools
# ============================================================================

@mcp.tool()
def list_loaded_builds() -> str:
    """List all builds currently loaded in the pool, showing which is active.

    Returns each build's pool name, whether it is the active build, and
    whether its LuaJIT process is still running.
    """
    builds = get_pool().list_builds()
    if not builds:
        return "No builds loaded. Use load_build_file or load_build_xml to load one."
    lines = []
    for b in builds:
        marker = " [active]" if b["active"] else ""
        status = "" if b["is_running"] else " (not running)"
        lines.append(f"  {b['name']}{marker}{status}")
    return "Loaded builds:\n" + "\n".join(lines)


@mcp.tool()
def switch_active_build(name: str) -> str:
    """Switch the active build. All subsequent tool calls will target this build.

    Args:
        name: Pool name of the build to activate (see list_loaded_builds)
    """
    get_pool().switch_build(name)
    info = call("get_build_info")
    build_name = info.get("buildName", name)
    class_name = info.get("className", "Unknown")
    level = info.get("level", "?")
    return f"Switched to '{name}': {build_name} ({class_name}, Level {level})"


@mcp.tool()
def unload_build(name: str) -> str:
    """Remove a build from the pool, freeing its LuaJIT process.

    Args:
        name: Pool name of the build to unload (see list_loaded_builds)
    """
    get_pool().unload_build(name)
    active = get_pool().active_build
    msg = f"Build '{name}' unloaded."
    if active:
        msg += f" Active build is now '{active}'."
    else:
        msg += " No active build remaining."
    return msg


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
        choices=["stdio", "sse", "streamable-http"],
        default="stdio",
        help="Transport mode: 'stdio' for standard input/output, 'sse' for SSE, 'streamable-http' for http streaming     streaming (default: stdio)",
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
    parser.add_argument(
        "--api-secret",
        default=None,
        #choices=["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"],
        help="Bearer token used for Chat GPT auth",
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
        if args.api_secret:
            secured_app = ChatGPTAuthMiddleware(app, token=args.api_secret)
            uvicorn.run(secured_app, host=args.host, port=args.port)
        else:
            #mcp.run(transport="sse", host=args.host, port=args.port)
            uvicorn.run(app, host=args.host, port=args.port)
    elif args.transport == "streamable-http":
        import uvicorn
        app = mcp.streamable_http_app()
        logger.info(
            "Starting MCP Streamable HTTP server on http://%s:%s/mcp",
            args.host,
            args.port,
        )
        if args.api_secret:
            secured_app = ChatGPTAuthMiddleware(app, token=args.api_secret)
            uvicorn.run(secured_app, host=args.host, port=args.port)
        else:
            uvicorn.run(app, host=args.host, port=args.port)
    #else:
    #    parser.error(f"Unknown transport: {args.transport}")