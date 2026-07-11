from __future__ import annotations

from pathlib import Path
from typing import Annotated, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator


class StrictModel(BaseModel):
    model_config = ConfigDict(extra="forbid", validate_assignment=True)


class UiSettings(StrictModel):
    vault_layout_mode: Literal["masonry", "grid"] = "masonry"
    vault_tile_min_width: Annotated[int, Field(ge=80, le=600)] = 140
    inspector_visible: bool = True
    inspector_width: Annotated[int, Field(ge=320, le=760)] = 400
    privacy_blur: bool = False
    ram_tracking_enabled: bool = False


class WebviewSettings(StrictModel):
    devtools_enabled: bool = False
    context_menu_enabled: bool = False


class LoggingSettings(StrictModel):
    level: Literal["DEBUG", "INFO", "WARNING", "ERROR", "CRITICAL"] = "INFO"


class NetworkSettings(StrictModel):
    proxy: str = ""
    user_agent: str = "LMZ/1.0"


class PlatformConcurrency(StrictModel):
    workers: Annotated[int, Field(ge=1, le=64)] = 1
    jitter_range: tuple[Annotated[float, Field(ge=0)], Annotated[float, Field(ge=0)]] = (2.0, 4.0)

    @model_validator(mode="after")
    def validate_jitter_order(self):
        if self.jitter_range[0] > self.jitter_range[1]:
            raise ValueError("jitter_range minimum cannot exceed maximum")
        return self


class IngestionConcurrency(StrictModel):
    global_max_workers: Annotated[int, Field(ge=1, le=128)] = 10
    platforms: dict[str, PlatformConcurrency] = Field(default_factory=dict)


class AcceptedMedia(StrictModel):
    extensions: list[str] = Field(default_factory=lambda: [".jpg", ".jpeg", ".png", ".webp", ".mp4"])
    mime_types: list[str] = Field(
        default_factory=lambda: ["image/jpeg", "image/png", "image/webp", "video/mp4"]
    )

    @field_validator("extensions")
    @classmethod
    def validate_extensions(cls, values: list[str]) -> list[str]:
        if not values or any(not value.startswith(".") or value != value.lower() for value in values):
            raise ValueError("extensions must be a non-empty list of lowercase dotted suffixes")
        return values


class ProcessingSettings(StrictModel):
    flatten_transparency: bool = True
    background_preset: Literal["white", "black", "custom"] = "white"
    custom_color: tuple[
        Annotated[int, Field(ge=0, le=255)],
        Annotated[int, Field(ge=0, le=255)],
        Annotated[int, Field(ge=0, le=255)],
    ] = (255, 255, 255)


class IngestionSettings(StrictModel):
    concurrency: IngestionConcurrency = Field(default_factory=IngestionConcurrency)
    accepted_media: AcceptedMedia = Field(default_factory=AcceptedMedia)
    processing: ProcessingSettings = Field(default_factory=ProcessingSettings)


class VideoTaggingSettings(StrictModel):
    enabled: bool = True
    frame_count: Annotated[int, Field(ge=1, le=100)] = 5
    merge_min_frames: Annotated[int, Field(ge=1, le=100)] = 2
    merge_high_confidence: Annotated[float, Field(ge=0, le=1)] = 0.75

    @model_validator(mode="after")
    def validate_frame_threshold(self):
        if self.merge_min_frames > self.frame_count:
            raise ValueError("merge_min_frames cannot exceed frame_count")
        return self


class TaggingSettings(StrictModel):
    enabled: bool = True
    model_repo: str = "SmilingWolf/wd-vit-tagger-v3"
    device: Literal["auto", "cpu", "cuda"] = "auto"
    display_source: Literal["yaml", "database"] = "yaml"
    threshold: Annotated[float, Field(ge=0, le=1)] = 0.35
    max_tags: Annotated[int, Field(ge=1, le=1000)] = 30
    fail_ingestion_on_error: bool = False
    video: VideoTaggingSettings = Field(default_factory=VideoTaggingSettings)


class AppSettings(StrictModel):
    schema_version: Literal[1] = 1
    ui: UiSettings = Field(default_factory=UiSettings)
    webview: WebviewSettings = Field(default_factory=WebviewSettings)
    logging: LoggingSettings = Field(default_factory=LoggingSettings)
    network: NetworkSettings = Field(default_factory=NetworkSettings)
    ingestion: IngestionSettings = Field(default_factory=IngestionSettings)
    tagging: TaggingSettings = Field(default_factory=TaggingSettings)


class WorkspaceEntry(StrictModel):
    name: str
    config_path: str

    @field_validator("name", "config_path")
    @classmethod
    def non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("value cannot be empty")
        return value

    @field_validator("config_path")
    @classmethod
    def relative_path_without_escape(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = Path(normalized)
        if not path.is_absolute() and ".." in path.parts:
            raise ValueError("relative workspace config path cannot escape the data home")
        return normalized


class WorkspaceRegistry(StrictModel):
    schema_version: Literal[1] = 1
    active_workspace: str = "default"
    workspaces: dict[str, WorkspaceEntry]

    @model_validator(mode="after")
    def validate_active_workspace(self):
        for workspace_id in self.workspaces:
            if not workspace_id or any(
                not char.isalnum() and char not in {"-", "_"} for char in workspace_id
            ):
                raise ValueError(f"unsafe workspace id: {workspace_id!r}")
        if self.active_workspace not in self.workspaces:
            raise ValueError("active_workspace must identify a registered workspace")
        return self


class VaultEntry(StrictModel):
    name: str
    root: str

    @field_validator("name")
    @classmethod
    def non_empty_name(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("name cannot be empty")
        return value

    @field_validator("root")
    @classmethod
    def relative_root_without_escape(cls, value: str) -> str:
        normalized = value.replace("\\", "/").strip()
        path = Path(normalized)
        if not normalized or normalized == "." or path.is_absolute() or ".." in path.parts:
            raise ValueError("vault root must be workspace-relative and cannot escape the workspace")
        return normalized


class WorkspaceConfig(StrictModel):
    schema_version: Literal[1] = 1
    active_vault: str = "default"
    vaults: dict[str, VaultEntry]

    @model_validator(mode="after")
    def validate_active_vault(self):
        for vault_id in self.vaults:
            if not vault_id or any(
                not char.isalnum() and char not in {"-", "_"} for char in vault_id
            ):
                raise ValueError(f"unsafe vault id: {vault_id!r}")
        if self.active_vault not in self.vaults:
            raise ValueError("active_vault must identify a configured vault")
        return self


def default_app_settings() -> AppSettings:
    return AppSettings()


def default_workspace_registry() -> WorkspaceRegistry:
    return WorkspaceRegistry(
        workspaces={
            "default": WorkspaceEntry(name="Default", config_path="default/config.yaml"),
        }
    )


def default_workspace_config() -> WorkspaceConfig:
    return WorkspaceConfig(
        vaults={
            "default": VaultEntry(name="Default", root="data/vaults/default"),
        }
    )
