from dataclasses import dataclass
from pathlib import Path


@dataclass
class WordTimestamp:
    word: str
    start: float
    end: float


@dataclass
class AudioSegment:
    path: Path | None
    duration: float
    words: list[WordTimestamp]
