"""Строгие stdlib-схемы для Knowledge Graph RAB9.

Используются dataclasses вместо Pydantic, чтобы стек зависел только от
стандартной библиотеки и NetworkX.
"""
from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional
import uuid


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def _short_id(length: int) -> str:
    return str(uuid.uuid4())[:length]


@dataclass
class Entity:
    name: str
    type: str
    source_file: str
    id: str = field(default_factory=lambda: _short_id(8))
    description: Optional[str] = None
    created_at: str = field(default_factory=_now_iso)


@dataclass
class Triple:
    subject: str
    predicate: str
    object: str
    provenance: str
    id: str = field(default_factory=lambda: _short_id(12))
    line_hint: Optional[int] = None
    confidence: float = 0.85
    extracted_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass
class Edge:
    source_node: str
    target_node: str
    predicate: str
    id: str = field(default_factory=lambda: _short_id(12))
    triples: list[str] = field(default_factory=list)
    source_files: list[str] = field(default_factory=list)
    confidence: float = 0.85
    assembled_at: str = field(default_factory=_now_iso)

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


@dataclass
class GraphQuery:
    question: str
    center_entity: Optional[str] = None
    max_hops: int = 2
    max_triples: int = 20

    def __post_init__(self) -> None:
        if not 1 <= self.max_hops <= 5:
            raise ValueError("max_hops must be between 1 and 5")
        if not 1 <= self.max_triples <= 100:
            raise ValueError("max_triples must be between 1 and 100")


@dataclass
class GraphAnswer:
    question: str
    answer: str
    cited_edges: list[str] = field(default_factory=list)
    confidence: float = 0.5
    graph_snapshot_built: Optional[str] = None

    def __post_init__(self) -> None:
        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")
