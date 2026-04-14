import json
from dataclasses import dataclass
from pathlib import Path


@dataclass
class ClipEntry:
    id: str
    file: str        # relative to library dir
    tags: list[str]
    type: str        # "image" | "video"
    loop: bool


class ClipIndex:
    def __init__(self, clips: list[ClipEntry], library_dir: Path):
        self._clips = clips
        self.library_dir = library_dir

    @classmethod
    def load(cls, index_path: Path) -> "ClipIndex":
        with open(index_path) as f:
            data = json.load(f)
        clips = [
            ClipEntry(
                id=c["id"],
                file=c["file"],
                tags=c.get("tags", []),
                type=c.get("type", "image"),
                loop=c.get("loop", False),
            )
            for c in data.get("clips", [])
        ]
        return cls(clips, index_path.parent)

    def find_by_id(self, clip_id: str) -> ClipEntry | None:
        return next((c for c in self._clips if c.id == clip_id), None)

    def find_by_tags(self, tags: list[str]) -> list[ClipEntry]:
        """Return clips sorted by number of overlapping tags, descending."""
        tag_set = {t.lower() for t in tags}
        scored = []
        for clip in self._clips:
            score = len(tag_set & {t.lower() for t in clip.tags})
            if score > 0:
                scored.append((score, clip))
        scored.sort(key=lambda x: -x[0])
        return [clip for _, clip in scored]

    def resolve_path(self, entry: ClipEntry) -> Path:
        return self.library_dir / entry.file
