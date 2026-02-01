# Path of Building PoE2 — API & MCP Server

A REST API and MCP (Model Context Protocol) server for the Path of Building PoE2 calculation engine. Lets you programmatically create builds, allocate passive nodes, equip items, add skills, and read calculated stats.

## Prerequisites

- **LuaJIT**: Required as a standalone interpreter (see platform-specific instructions below)
- **Python 3.10+**: Required for the `mcp` SDK
- **Python dependencies**: `pip install -r api/requirements.txt`

### Installing LuaJIT

The PoB Windows app bundles LuaJIT inside its GUI executable (`runtime/Path of Building-PoE2.exe`), but the API needs a standalone `luajit` interpreter.

**macOS:**
```bash
brew install luajit
```

**Windows:**
```
scoop install luajit
```
or
```
choco install luajit
```
or download binaries from https://luajit.org/download.html. Make sure `luajit.exe` is on your PATH, or set the `LUAJIT_PATH` environment variable.

**Linux:**
```bash
sudo apt install luajit    # Debian/Ubuntu
sudo pacman -S luajit      # Arch
```

## Quick Start

### REST API

```bash
python api/run_api.py
```

The server starts at `http://127.0.0.1:8000`. Test it:

```bash
# Health check
curl http://localhost:8000/health

# Create a new build
curl -X POST http://localhost:8000/build/new

# Get build info
curl http://localhost:8000/build/info

# Search for passive nodes
curl 'http://localhost:8000/tree/search?q=life&max_results=5'

# Add a skill
curl -X POST http://localhost:8000/skills/add \
  -H 'Content-Type: application/json' \
  -d '{"skill_text": "Lightning Arrow 20/0 1"}'

# Get calculated stats
curl http://localhost:8000/calc

# Get specific stats
curl 'http://localhost:8000/calc/stats?keys=Life,Mana,TotalDPS,FireResist'
```

Options:

```
python api/run_api.py --host 0.0.0.0 --port 9000 --log-level debug
```

### MCP Server (Claude Desktop)

Add this to your Claude Desktop config file:

**macOS**: `~/Library/Application Support/Claude/claude_desktop_config.json`
**Windows**: `%APPDATA%\Claude\claude_desktop_config.json`

```json
{
  "mcpServers": {
    "pob-poe2": {
      "command": "python",
      "args": ["/path/to/PathOfBuilding-PoE2/api/run_mcp.py"],
      "env": {
        "POB_PATH": "/path/to/PathOfBuilding-PoE2"
      }
    }
  }
}
```

Replace `/path/to/PathOfBuilding-PoE2` with the actual path to your clone.

**Windows example:**

```json
{
  "mcpServers": {
    "pob-poe2": {
      "command": "python",
      "args": ["C:\\Users\\you\\PathOfBuilding-PoE2\\api\\run_mcp.py"],
      "env": {
        "POB_PATH": "C:\\Users\\you\\PathOfBuilding-PoE2",
        "LUAJIT_PATH": "C:\\tools\\luajit\\luajit.exe"
      }
    }
  }
}
```

Set `LUAJIT_PATH` if `luajit` isn't on your system PATH.

**With a conda environment or specific Python path:**

```json
{
  "mcpServers": {
    "pob-poe2": {
      "command": "/path/to/conda/envs/py313env/bin/python",
      "args": ["/path/to/PathOfBuilding-PoE2/api/run_mcp.py"],
      "env": {
        "POB_PATH": "/path/to/PathOfBuilding-PoE2"
      }
    }
  }
}
```

Restart Claude Desktop after editing the config. You can then ask Claude to:

- "Create a new Ranger build and allocate some life nodes"
- "Add Lightning Arrow and show me the DPS"
- "What are my current resistances?"
- "Search for nodes that give attack speed"

### Lua Bridge (standalone)

For direct testing without Python.

**macOS / Linux:**

```bash
cd src
echo '{"command":"ping"}' | \
  LUA_PATH="../runtime/lua/?.lua;../runtime/lua/?/init.lua;;" \
  luajit ../api/lua/bridge.lua
```

Multi-command session (one JSON object per line):

```bash
cd src
LUA_PATH="../runtime/lua/?.lua;../runtime/lua/?/init.lua;;" \
  luajit ../api/lua/bridge.lua <<'EOF'
{"command":"new_build"}
{"command":"add_skill","params":{"skill_text":"Lightning Arrow 20/0 1"}}
{"command":"get_output","params":{"stats":["TotalDPS","Life","Mana"]}}
{"command":"shutdown"}
EOF
```

**Windows (cmd):**

```cmd
cd src
set LUA_PATH=../runtime/lua/?.lua;../runtime/lua/?/init.lua;;
set LUA_CPATH=../runtime/?.dll;;
echo {"command":"ping"} | luajit ..\api\lua\bridge.lua
```

**Windows (PowerShell):**

```powershell
cd src
$env:LUA_PATH = "../runtime/lua/?.lua;../runtime/lua/?/init.lua;;"
$env:LUA_CPATH = "../runtime/?.dll;;"
echo '{"command":"ping"}' | luajit ..\api\lua\bridge.lua
```

On Windows, setting `LUA_CPATH` lets LuaJIT find the native DLLs in `runtime/` (like `lua-utf8.dll`), so you get full functionality instead of the fallback stubs.

## Environment Variables

| Variable | Default | Description |
|----------|---------|-------------|
| `POB_PATH` | Auto-detected from file location | Path to PathOfBuilding-PoE2 root |
| `LUAJIT_PATH` | `luajit` | Path to LuaJIT executable |
| `POB_API_HOST` | `127.0.0.1` | REST API bind host |
| `POB_API_PORT` | `8000` | REST API bind port |
| `POB_BRIDGE_STARTUP_TIMEOUT` | `30.0` | Seconds to wait for bridge ready signal |
| `POB_BRIDGE_COMMAND_TIMEOUT` | `30.0` | Seconds to wait for command responses |

## REST API Reference

### Build

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/build/new` | Create a new empty build |
| POST | `/build/load/xml` | Load build from XML (body: `{"xml": "...", "name": "..."}`) |
| GET | `/build/info` | Get build info (class, level, ascendancy) |
| GET | `/build/export/xml` | Export build as XML |

### Passive Tree

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/tree/nodes` | List allocated nodes |
| GET | `/tree/node/{id}` | Get node details |
| POST | `/tree/node/{id}/alloc` | Allocate a node |
| POST | `/tree/node/{id}/dealloc` | Deallocate a node |
| GET | `/tree/search?q=...` | Search nodes by name |

### Items

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/items` | List all items |
| GET | `/items/slots` | List equipment slots |
| POST | `/items/add` | Add item (body: `{"item_raw": "...", "slot": "..."}`) |
| POST | `/items/{id}/equip` | Equip item (body: `{"item_id": ..., "slot": "..."}`) |
| POST | `/items/slot/{slot}/unequip` | Unequip a slot |
| DELETE | `/items/{id}` | Delete item |

### Skills

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/skills` | List skill gem groups |
| POST | `/skills/add` | Add skill group (body: `{"skill_text": "..."}`) |
| DELETE | `/skills/{index}` | Remove skill group |
| POST | `/skills/main` | Set main skill (body: `{"index": 1}`) |

### Calculations

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/calc` | Get curated stats (DPS, life, resistances, etc.) |
| GET | `/calc/full` | Get full calculation output |
| GET | `/calc/stats?keys=Life,Mana` | Get specific stat keys |

### Config

| Method | Endpoint | Description |
|--------|----------|-------------|
| POST | `/config` | Set config option (body: `{"key": "...", "value": ...}`) |
| POST | `/config/custom-mods` | Set custom mods (body: `{"mods": "..."}`) |

### Health

| Method | Endpoint | Description |
|--------|----------|-------------|
| GET | `/health` | Health check |

## MCP Tools Reference

All 20 tools available to Claude Desktop:

| Tool | Description |
|------|-------------|
| `new_build` | Create a new empty build |
| `load_build_xml` | Load build from XML |
| `get_build_info` | Get class, level, ascendancy info |
| `export_build_xml` | Export build as XML |
| `alloc_node` | Allocate a passive tree node |
| `dealloc_node` | Deallocate a passive tree node |
| `get_allocated_nodes` | List allocated nodes |
| `search_nodes` | Search nodes by name |
| `get_node_info` | Get detailed node info |
| `list_items` | List items in the build |
| `add_item` | Add item from game copy-paste text |
| `equip_item` | Equip item to a slot |
| `list_slots` | List equipment slots |
| `list_skills` | List skill gem groups |
| `add_skill` | Add a skill gem group |
| `set_main_skill` | Set main skill for DPS calcs |
| `get_stats` | Get calculated build stats |
| `get_full_stats` | Get all calculated stats |
| `set_config` | Set a config option |
| `set_custom_mods` | Set custom modifiers |

## Skill Text Format

When adding skills via `add_skill` or `/skills/add`, use this format:

```
Label: My Attack Setup
Slot: Weapon 1
Lightning Arrow 20/0 1
Added Lightning Damage Support 20/0 1
```

Each gem line: `GemName level/quality count`

- `GemName`: The gem name (spaces allowed)
- `level/quality`: Gem level and quality separated by `/`
- `count`: Number of gems (usually 1)

## Item Text Format

When adding items via `add_item` or `/items/add`, use the game's copy-paste format:

```
Item Class: Bows
Rarity: Rare
Havoc Fletch
Recurve Bow
--------
Physical Damage: 25-65
Critical Hit Chance: 5.00%
Attacks per Second: 1.40
--------
Requirements:
Level: 18
Dex: 65
--------
+10% to Fire Resistance
Adds 5 to 10 Physical Damage
10% increased Attack Speed
```

## Troubleshooting

### "module 'xml' not found" or similar Lua errors

LuaJIT can't find the pure-Lua modules. Make sure `LUA_PATH` is set. The Python bridge sets this automatically. For standalone use:

```bash
export LUA_PATH="../runtime/lua/?.lua;../runtime/lua/?/init.lua;;"
```

### Bridge startup timeout

Increase the timeout:

```bash
export POB_BRIDGE_STARTUP_TIMEOUT=60
```

### "No module named 'mcp'" or Python import errors

Install dependencies with Python 3.10+:

```bash
pip install -r api/requirements.txt
```

### Claude Desktop doesn't show PoB tools

1. Check that the config JSON is valid
2. Verify the `python` path points to Python 3.10+
3. Check that `POB_PATH` is correct
4. Restart Claude Desktop completely
5. Check Claude Desktop's MCP logs for errors

### Windows: "luajit" is not recognized

LuaJIT isn't on your PATH. Either:
- Add the directory containing `luajit.exe` to your system PATH
- Set the `LUAJIT_PATH` environment variable to the full path of `luajit.exe` (in your Claude Desktop config or system environment)

### Windows: can't use PoB's bundled exe as LuaJIT

The bundled `runtime/Path of Building-PoE2.exe` is a GUI application that embeds LuaJIT — it's not a standalone Lua interpreter and can't run the bridge script. You need a separate LuaJIT installation (see Prerequisites above).
