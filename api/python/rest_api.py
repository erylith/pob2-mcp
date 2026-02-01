"""FastAPI REST API for Path of Building PoE2."""

import logging
from contextlib import asynccontextmanager
from typing import Any

from fastapi import FastAPI, HTTPException, Query

from .lua_bridge import LuaBridge, LuaBridgeError
from .models import (
    AddItemRequest,
    AddSkillRequest,
    BuildFileInfo,
    BuildInfo,
    BuildXmlResponse,
    CalcStatsRequest,
    CreateFolderRequest,
    DeleteBuildFileRequest,
    EquipItemRequest,
    FolderInfo,
    HealthResponse,
    ItemSummary,
    LoadBuildFileRequest,
    LoadBuildXmlRequest,
    NodeInfo,
    NodeSummary,
    RenameBuildFileRequest,
    SaveBuildAsRequest,
    SearchNodesResponse,
    SetConfigRequest,
    SetCustomModsRequest,
    SetMainSkillRequest,
    SkillGroupInfo,
    SlotInfo,
    SuccessResponse,
)

logger = logging.getLogger(__name__)

# Global bridge instance
bridge: LuaBridge | None = None


def get_bridge() -> LuaBridge:
    """Get the global bridge instance, raising if not available."""
    if bridge is None or not bridge.is_running:
        raise HTTPException(status_code=503, detail="Lua bridge is not running")
    return bridge


def bridge_call(command: str, params: dict[str, Any] | None = None) -> dict[str, Any]:
    """Call a bridge command, converting errors to HTTP exceptions."""
    try:
        return get_bridge().send_command(command, params)
    except LuaBridgeError as e:
        raise HTTPException(status_code=400, detail=str(e)) from e


@asynccontextmanager
async def lifespan(app: FastAPI):
    """Start and stop the Lua bridge with the application."""
    global bridge
    bridge = LuaBridge()
    try:
        bridge.start()
        logger.info("Lua bridge started successfully")
        yield
    finally:
        if bridge is not None:
            bridge.shutdown()
            logger.info("Lua bridge shut down")


app = FastAPI(
    title="Path of Building PoE2 API",
    description="REST API for the Path of Building PoE2 calculation engine",
    version="0.1.0",
    lifespan=lifespan,
)


# ============================================================================
# Health
# ============================================================================

@app.get("/health", response_model=HealthResponse)
async def health():
    return HealthResponse(
        status="ok",
        bridge_running=bridge is not None and bridge.is_running,
    )


# ============================================================================
# Build endpoints
# ============================================================================

@app.post("/build/new", response_model=SuccessResponse)
async def new_build():
    bridge_call("new_build")
    return SuccessResponse()


@app.post("/build/load/xml", response_model=SuccessResponse)
async def load_build_xml(req: LoadBuildXmlRequest):
    bridge_call("load_build_xml", {"xml": req.xml, "name": req.name})
    return SuccessResponse()


@app.get("/build/info", response_model=BuildInfo)
async def get_build_info():
    result = bridge_call("get_build_info")
    return BuildInfo(**result)


@app.get("/build/export/xml", response_model=BuildXmlResponse)
async def export_build_xml():
    result = bridge_call("get_build_xml")
    return BuildXmlResponse(xml=result["xml"])


# ============================================================================
# Tree endpoints
# ============================================================================

@app.get("/tree/nodes", response_model=dict)
async def list_alloc_nodes():
    return bridge_call("list_alloc_nodes")


@app.get("/tree/node/{node_id}", response_model=NodeInfo)
async def get_node_info(node_id: int):
    result = bridge_call("get_node_info", {"node_id": node_id})
    return NodeInfo(**result)


@app.post("/tree/node/{node_id}/alloc", response_model=SuccessResponse)
async def alloc_node(node_id: int):
    bridge_call("alloc_node", {"node_id": node_id})
    return SuccessResponse()


@app.post("/tree/node/{node_id}/dealloc", response_model=SuccessResponse)
async def dealloc_node(node_id: int):
    bridge_call("dealloc_node", {"node_id": node_id})
    return SuccessResponse()


@app.get("/tree/search", response_model=SearchNodesResponse)
async def search_nodes(
    q: str = Query(..., min_length=1),
    max_results: int = Query(50, ge=1, le=500),
):
    result = bridge_call("search_nodes", {"query": q, "max_results": max_results})
    return SearchNodesResponse(
        nodes=[NodeSummary(**n) for n in result.get("nodes", [])],
        count=result.get("count", 0),
    )


# ============================================================================
# Item endpoints
# ============================================================================

@app.get("/items", response_model=dict)
async def list_items():
    return bridge_call("list_items")


@app.get("/items/slots", response_model=dict)
async def list_slots():
    return bridge_call("list_slots")


@app.post("/items/add", response_model=dict)
async def add_item(req: AddItemRequest):
    params: dict[str, Any] = {"item_raw": req.item_raw}
    if req.slot:
        params["slot"] = req.slot
    return bridge_call("add_item", params)


@app.post("/items/{item_id}/equip", response_model=SuccessResponse)
async def equip_item(item_id: int, req: EquipItemRequest):
    bridge_call("equip_item", {"item_id": item_id, "slot": req.slot})
    return SuccessResponse()


@app.post("/items/slot/{slot}/unequip", response_model=SuccessResponse)
async def unequip_slot(slot: str):
    bridge_call("unequip_slot", {"slot": slot})
    return SuccessResponse()


@app.delete("/items/{item_id}", response_model=SuccessResponse)
async def delete_item(item_id: int):
    bridge_call("delete_item", {"item_id": item_id})
    return SuccessResponse()


# ============================================================================
# Skill endpoints
# ============================================================================

@app.get("/skills", response_model=dict)
async def list_skills():
    return bridge_call("list_skills")


@app.post("/skills/add", response_model=dict)
async def add_skill(req: AddSkillRequest):
    return bridge_call("add_skill", {"skill_text": req.skill_text})


@app.delete("/skills/{index}", response_model=SuccessResponse)
async def remove_skill(index: int):
    bridge_call("remove_skill", {"index": index})
    return SuccessResponse()


@app.post("/skills/main", response_model=SuccessResponse)
async def set_main_skill(req: SetMainSkillRequest):
    bridge_call("set_main_skill", {"index": req.index})
    return SuccessResponse()


# ============================================================================
# Calc endpoints
# ============================================================================

@app.get("/calc", response_model=dict)
async def get_calc():
    """Get curated calculation output stats."""
    return bridge_call("get_output")


@app.get("/calc/full", response_model=dict)
async def get_calc_full():
    """Get the full calculation output (large)."""
    return bridge_call("get_full_output")


@app.get("/calc/stats", response_model=dict)
async def get_calc_stats(keys: str = Query("", description="Comma-separated stat keys")):
    """Get specific stat keys from the calculation output."""
    if keys:
        stat_keys = [k.strip() for k in keys.split(",") if k.strip()]
        return bridge_call("get_output", {"stats": stat_keys})
    return bridge_call("get_output")


# ============================================================================
# Config endpoints
# ============================================================================

@app.post("/config", response_model=SuccessResponse)
async def set_config(req: SetConfigRequest):
    bridge_call("set_config", {"key": req.key, "value": req.value})
    return SuccessResponse()


@app.post("/config/custom-mods", response_model=SuccessResponse)
async def set_custom_mods(req: SetCustomModsRequest):
    bridge_call("set_custom_mods", {"mods": req.mods})
    return SuccessResponse()


# ============================================================================
# File management endpoints
# ============================================================================

@app.get("/builds", response_model=dict)
async def list_builds(sub_path: str = Query("")):
    """List saved builds with metadata."""
    result = bridge_call("list_builds", {"sub_path": sub_path})
    return {
        "builds": [BuildFileInfo(**b) for b in result.get("builds", [])],
        "folders": [FolderInfo(**f) for f in result.get("folders", [])],
    }


@app.get("/builds/path", response_model=dict)
async def get_builds_path():
    """Get the current builds directory path."""
    result = bridge_call("get_builds_path")
    return result


@app.post("/build/load/file", response_model=SuccessResponse)
async def load_build_file(req: LoadBuildFileRequest):
    """Load a build from a file path."""
    bridge_call("load_build_file", {"path": req.path})
    return SuccessResponse()


@app.post("/build/save", response_model=SuccessResponse)
async def save_build():
    """Save the current build to its existing file."""
    bridge_call("save_build")
    return SuccessResponse()


@app.post("/build/save-as", response_model=dict)
async def save_build_as(req: SaveBuildAsRequest):
    """Save the current build to a new file."""
    return bridge_call("save_build_as", {"name": req.name, "sub_path": req.sub_path})


@app.delete("/builds/file", response_model=SuccessResponse)
async def delete_build_file(req: DeleteBuildFileRequest):
    """Delete a build file."""
    bridge_call("delete_build_file", {"path": req.path})
    return SuccessResponse()


@app.post("/builds/folder", response_model=dict)
async def create_folder(req: CreateFolderRequest):
    """Create a subfolder in the builds directory."""
    return bridge_call("create_folder", {"name": req.name, "sub_path": req.sub_path})


@app.post("/builds/rename", response_model=dict)
async def rename_build_file(req: RenameBuildFileRequest):
    """Rename a build file."""
    return bridge_call("rename_build_file", {"old_path": req.old_path, "new_name": req.new_name})
