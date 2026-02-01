"""Pydantic request/response models for the PoB REST API."""

from typing import Any, Optional

from pydantic import BaseModel, Field


# ============================================================================
# Build models
# ============================================================================

class LoadBuildXmlRequest(BaseModel):
    xml: str = Field(..., description="Build XML content")
    name: str = Field("Imported Build", description="Build name")


class BuildInfo(BaseModel):
    className: Optional[str] = None
    ascendClassName: Optional[str] = None
    level: Optional[int] = None
    mainSocketGroup: Optional[int] = None
    viewMode: Optional[str] = None
    buildName: Optional[str] = None


class BuildXmlResponse(BaseModel):
    xml: str


# ============================================================================
# Tree / Node models
# ============================================================================

class NodeInfo(BaseModel):
    id: int
    name: str | None = None
    type: str | None = None
    alloc: bool = False
    ascendancyName: str | None = None
    mods: list[str] | None = None
    linked: list[int] | None = None
    classStartIndex: int | None = None
    isMultipleChoice: bool = False
    isMultipleChoiceOption: bool = False
    passivePointsGranted: int = 0


class NodeSummary(BaseModel):
    id: int
    name: str | None = None
    type: str | None = None
    alloc: bool = False
    ascendancyName: str | None = None


class AllocNodeRequest(BaseModel):
    node_id: int


class SearchNodesRequest(BaseModel):
    query: str = Field(..., min_length=1)
    max_results: int = Field(50, ge=1, le=500)


class SearchNodesResponse(BaseModel):
    nodes: list[NodeSummary]
    count: int


# ============================================================================
# Item models
# ============================================================================

class ItemSummary(BaseModel):
    id: int
    name: str
    baseName: str | None = None
    type: str | None = None
    rarity: str | None = None


class SlotInfo(BaseModel):
    slotName: str
    itemId: int = 0
    itemName: str | None = None


class AddItemRequest(BaseModel):
    item_raw: str = Field(..., description="Item text in PoE copy-paste format")
    slot: str | None = Field(None, description="Optional slot to equip the item to")


class EquipItemRequest(BaseModel):
    item_id: int
    slot: str


class UnequipSlotRequest(BaseModel):
    slot: str


# ============================================================================
# Skill models
# ============================================================================

class GemInfo(BaseModel):
    nameSpec: str | None = None
    level: int | None = None
    quality: int | None = None
    enabled: bool = True
    count: int | None = None
    skillId: str | None = None
    gemId: str | None = None


class SkillGroupInfo(BaseModel):
    index: int
    label: str | None = None
    enabled: bool = True
    slot: str | None = None
    source: str | None = None
    mainActiveSkill: int | None = None
    isMainGroup: bool = False
    gems: list[GemInfo] = []


class AddSkillRequest(BaseModel):
    skill_text: str = Field(
        ...,
        description=(
            "Skill text in paste format. Example:\n"
            "Label: My Skill\n"
            "Fireball 20/0 1\n"
            "Combustion Support 20/0 1"
        ),
    )


class SetMainSkillRequest(BaseModel):
    index: int = Field(..., ge=1)


# ============================================================================
# Calc / Output models
# ============================================================================

class CalcStatsRequest(BaseModel):
    keys: list[str] = Field(
        default_factory=list,
        description="Specific stat keys to retrieve. Empty means curated defaults.",
    )


# ============================================================================
# Config models
# ============================================================================

class SetConfigRequest(BaseModel):
    key: str
    value: Any


class SetCustomModsRequest(BaseModel):
    mods: str = Field(..., description="Custom modifier text, one mod per line")


# ============================================================================
# File management models
# ============================================================================

class BuildFileInfo(BaseModel):
    id: str
    name: str
    fileName: str
    fullPath: str
    level: int
    className: str | None = None
    ascendClassName: str | None = None
    modified: int


class FolderInfo(BaseModel):
    name: str
    fullPath: str


class ListBuildsResponse(BaseModel):
    builds: list[BuildFileInfo]
    folders: list[FolderInfo]


class BuildsPathResponse(BaseModel):
    builds_path: str


class LoadBuildFileRequest(BaseModel):
    path: str


class SaveBuildAsRequest(BaseModel):
    name: str
    sub_path: str = ""


class DeleteBuildFileRequest(BaseModel):
    path: str


class CreateFolderRequest(BaseModel):
    name: str
    sub_path: str = ""


class RenameBuildFileRequest(BaseModel):
    old_path: str
    new_name: str


# ============================================================================
# Generic responses
# ============================================================================

class SuccessResponse(BaseModel):
    success: bool = True


class ErrorResponse(BaseModel):
    detail: str


class HealthResponse(BaseModel):
    status: str = "ok"
    bridge_running: bool = False
