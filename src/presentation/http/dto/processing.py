from __future__ import annotations

from pydantic import BaseModel, ConfigDict, Field, field_validator

from domain.entities import PipelineRunStage

PROCESSING_CONTRACT_VERSION = "1"


class ProcessingModel(BaseModel):
    model_config = ConfigDict(from_attributes=True)


class ProcessingJobResponse(ProcessingModel):
    contract_version: str = PROCESSING_CONTRACT_VERSION
    run_id: str
    source_name: str
    source_object_key: str
    output_prefix: str


class ProcessingClaimRequest(ProcessingModel):
    contract_version: str

    @field_validator("contract_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != PROCESSING_CONTRACT_VERSION:
            raise ValueError("Неподдерживаемая версия processing-контракта.")
        return value


class ProcessingProgressRequest(ProcessingModel):
    contract_version: str
    stage: PipelineRunStage
    progress: int = Field(ge=0, le=99)
    message: str | None = Field(default=None, max_length=1024)
    create_event: bool = False

    @field_validator("contract_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != PROCESSING_CONTRACT_VERSION:
            raise ValueError("Неподдерживаемая версия processing-контракта.")
        return value


class ProcessingArtifactRequest(ProcessingModel):
    relative_path: str = Field(min_length=1, max_length=1024)
    content_type: str = Field(min_length=1, max_length=255)
    size_bytes: int = Field(ge=0)


class ProcessingVideoMetadataRequest(ProcessingModel):
    fps: float = Field(gt=0)
    frame_count: int = Field(gt=0)
    frame_stride: int = Field(gt=0)
    width: int = Field(gt=0)
    height: int = Field(gt=0)


class ProcessingCompleteRequest(ProcessingModel):
    contract_version: str
    metadata: ProcessingVideoMetadataRequest
    artifacts: list[ProcessingArtifactRequest] = Field(max_length=10_000)

    @field_validator("contract_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != PROCESSING_CONTRACT_VERSION:
            raise ValueError("Неподдерживаемая версия processing-контракта.")
        return value


class ProcessingFailRequest(ProcessingModel):
    contract_version: str
    error_code: str = Field(min_length=1, max_length=128)
    error_message: str = Field(min_length=1, max_length=100_000)

    @field_validator("contract_version")
    @classmethod
    def supported_version(cls, value: str) -> str:
        if value != PROCESSING_CONTRACT_VERSION:
            raise ValueError("Неподдерживаемая версия processing-контракта.")
        return value
