import multiprocessing
import random
from pathlib import Path

import numpy as np
from tqdm import tqdm
from moviepy.editor import (
    AudioFileClip,
    ColorClip,
    CompositeAudioClip,
    CompositeVideoClip,
    ImageClip,
    ImageSequenceClip,
    VideoFileClip,
    concatenate_videoclips,
)
import moviepy.audio.fx.all as afx
from PIL import Image, ImageDraw, ImageFont

from vibrava.audio.tts import AudioSegment, WordTimestamp
from vibrava.platforms.cat.story_parser import Sentence

# ---------------------------------------------------------------------------
# Font loading (cached by size)
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]

_font_cache: dict[int, ImageFont.FreeTypeFont | ImageFont.ImageFont] = {}


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    if size not in _font_cache:
        for path in _FONT_CANDIDATES:
            try:
                _font_cache[size] = ImageFont.truetype(path, size)
                break
            except (OSError, IOError):
                continue
        else:
            _font_cache[size] = ImageFont.load_default()
    return _font_cache[size]


_PADDING = 0.90

# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------

def _make_background_frame(img_path: Path, width: int, height: int) -> np.ndarray:
    """
    Image scaled to fit (with padding) centered on a black background.
    """
    img = Image.open(img_path).convert("RGB")

    bg = Image.new("RGB", (width, height), (0, 0, 0))

    fg_ratio = min(width / img.width, height / img.height) * _PADDING
    fg = img.resize(
        (int(img.width * fg_ratio), int(img.height * fg_ratio)), Image.LANCZOS
    )
    x = (width - fg.width) // 2
    y = (height - fg.height) // 2
    bg.paste(fg, (x, y))

    return np.array(bg)


def _wrap_text(text: str, font: ImageFont.FreeTypeFont, max_width: int) -> list[str]:
    """Word-wrap text to fit within max_width pixels."""
    words = text.split()
    lines: list[str] = []
    current: list[str] = []

    dummy = Image.new("RGB", (1, 1))
    draw = ImageDraw.Draw(dummy)

    for word in words:
        test = " ".join(current + [word])
        bbox = draw.textbbox((0, 0), test, font=font)
        if bbox[2] > max_width and current:
            lines.append(" ".join(current))
            current = [word]
        else:
            current.append(word)
    if current:
        lines.append(" ".join(current))

    return lines


def _render_caption_line(
    text: str, width: int, height: int,
    font_size_override: int | None = None,
    y_pct: float = 80.0,
) -> np.ndarray:
    """Render the full sentence as white text with black stroke near the bottom."""
    font_size = font_size_override if font_size_override is not None else max(44, height // 26)
    font = _load_font(font_size)
    max_text_width = int(width * 0.88)
    lines = _wrap_text(text, font, max_text_width)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    line_height = font_size + 12
    total_text_height = len(lines) * line_height
    y = int(height * y_pct / 100) - total_text_height // 2

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=4, stroke_fill="black")
        y += line_height

    return np.array(img)


def _build_caption_layout(
    words: list[WordTimestamp],
    width: int,
    height: int,
    font_size_override: int | None = None,
    y_pct: float = 80.0,
) -> tuple[ImageFont.FreeTypeFont | ImageFont.ImageFont, list[tuple[int, int]]]:
    """
    Compute font and (x, y) position for each word once per sentence.
    Returns (font, word_positions).
    """
    font_size = font_size_override if font_size_override is not None else max(44, height // 26)
    font = _load_font(font_size)
    full_text = " ".join(w.word for w in words)
    lines = _wrap_text(full_text, font, int(width * 0.88))

    line_height = font_size + 12
    y = int(height * y_pct / 100) - len(lines) * line_height // 2

    dummy = Image.new("RGBA", (1, 1))
    draw = ImageDraw.Draw(dummy)

    positions: list[tuple[int, int]] = []
    for line in lines:
        x = (width - draw.textbbox((0, 0), line, font=font)[2]) // 2
        for word in line.split():
            positions.append((x, y))
            x += draw.textbbox((0, 0), word + " ", font=font)[2]
        y += line_height

    return font, positions


def _render_caption_word(
    words: list[WordTimestamp],
    current_word_idx: int,
    width: int,
    height: int,
    font: ImageFont.FreeTypeFont | ImageFont.ImageFont,
    positions: list[tuple[int, int]],
) -> np.ndarray:
    """Render all words with the current word highlighted in yellow."""
    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)
    for i, (w, pos) in enumerate(zip(words, positions)):
        color = "yellow" if i == current_word_idx else "white"
        draw.text(pos, w.word, font=font, fill=color, stroke_width=4, stroke_fill="black")
    return np.array(img)


# ---------------------------------------------------------------------------
# GIF clip builder
# ---------------------------------------------------------------------------

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}


def _make_video_clip(video_path: Path, width: int, height: int, duration: float):
    """Load a video clip, trim to sentence duration, and scale-to-fit with padding."""
    clip = VideoFileClip(str(video_path), audio=False)
    if clip.duration > duration:
        clip = clip.subclip(0, duration)
    else:
        clip = clip.set_duration(duration)
    scale = min(width / clip.w, height / clip.h) * _PADDING
    new_w, new_h = int(clip.w * scale), int(clip.h * scale)
    x, y = (width - new_w) // 2, (height - new_h) // 2
    bg = ColorClip(size=(width, height), color=(0, 0, 0)).set_duration(clip.duration)
    return CompositeVideoClip([bg, clip.resize((new_w, new_h)).set_position((x, y))])


def _make_gif_clip(gif_path: Path, width: int, height: int, duration: float):
    """Load an animated GIF via PIL, resize frames, loop to fill duration."""
    gif = Image.open(gif_path)
    frames = []
    frame_durations = []
    try:
        while True:
            frame = gif.copy().convert("RGB")
            scale = min(width / frame.width, height / frame.height) * _PADDING
            fw, fh = int(frame.width * scale), int(frame.height * scale)
            frame = frame.resize((fw, fh), Image.LANCZOS)
            bg = Image.new("RGB", (width, height), (0, 0, 0))
            bg.paste(frame, ((width - fw) // 2, (height - fh) // 2))
            frames.append(np.array(bg))
            frame_durations.append(gif.info.get("duration", 100) / 1000.0)
            gif.seek(gif.tell() + 1)
    except EOFError:
        pass

    clip = ImageSequenceClip(frames, durations=frame_durations)
    return clip.loop(duration=duration)


# ---------------------------------------------------------------------------
# Overlay image
# ---------------------------------------------------------------------------

def _make_overlay_clip(
    overlay_path: Path,
    width: int,
    height: int,
    duration: float,
    size_frac: float = 1/6,
    padding: int = 20,
    opacity: float = 1.0,
    fade_in: float = 0.0,
    centered: bool = False,
) -> ImageClip:
    from moviepy.editor import VideoClip as _VideoClip

    img = Image.open(overlay_path).convert("RGBA")
    max_dim = max(1, int(width * size_frac))
    scale = min(max_dim / img.width, max_dim / img.height, 1.0)
    new_w, new_h = int(img.width * scale), int(img.height * scale)
    img = img.resize((new_w, new_h), Image.LANCZOS)
    canvas = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    if centered:
        x, y = (width - new_w) // 2, (height - new_h) // 2
    else:
        x, y = padding, height - new_h - padding
    canvas.paste(img, (x, y), img)
    clip = ImageClip(np.array(canvas), ismask=False).set_duration(duration)

    if opacity < 1.0 or fade_in > 0.0:
        clip = clip.set_opacity(opacity)
        if fade_in > 0.0:
            base_mask = clip.mask

            def _fade_frame(t):
                factor = min(t / fade_in, 1.0)
                return base_mask.get_frame(t) * factor

            clip = clip.set_mask(
                _VideoClip(_fade_frame, ismask=True).set_duration(duration)
            )

    return clip


# ---------------------------------------------------------------------------
# Main build function
# ---------------------------------------------------------------------------

def _make_image_clip(img_path: Path | None, width: int, height: int, duration: float):
    """Return a video clip for a single image (or black if None)."""
    if img_path and img_path.exists():
        ext = img_path.suffix.lower()
        if ext in _VIDEO_EXTENSIONS:
            return _make_video_clip(img_path, width, height, duration)
        elif ext == ".gif":
            return _make_gif_clip(img_path, width, height, duration)
        else:
            frame = _make_background_frame(img_path, width, height)
            return ImageClip(frame).set_duration(duration)
    frame = np.zeros((height, width, 3), dtype=np.uint8)
    return ImageClip(frame).set_duration(duration)


def build(
    sentences: list[Sentence],
    audio_map: dict[str, AudioSegment],
    image_map: dict[str, list[Path | None]],
    output_path: Path,
    resolution: tuple[int, int],
    pause_duration: float,
    caption_style: str,
    sfx_map: dict[str, tuple[Path, float] | None] | None = None,
    sentence_overlay_map: dict[str, tuple[Path, float, float] | None] | None = None,
    overlay_image_path: Path | None = None,
    overlay_image_size: float = 1/6,
    music_path: Path | None = None,
    music_volume: float = 0.15,
    music_start: float = 0.0,
    pause_jitter: float = 0.0,
    fps: int = 30,
    caption_font_size: int | None = None,
    caption_y_pct: float = 80.0,
) -> None:
    width, height = resolution
    clips = []

    estimated_duration = sum(audio_map[s.id].duration for s in sentences)
    print(f"[compose] {len(sentences)} sentences · ~{estimated_duration:.1f}s of audio")

    for sentence in tqdm(sentences, desc="building clips", unit="clip"):
        seg = audio_map[sentence.id]
        images = image_map.get(sentence.id) or [None]
        img_path = images[0] if images else None
        img2_path = images[1] if len(images) > 1 else None
        if sentence.pause_duration is not None:
            gap = sentence.pause_duration
        elif pause_jitter > 0:
            gap = random.uniform(0.1, pause_jitter)
        else:
            gap = pause_duration

        # Empty sentences (no text) are pure pause gaps — no audio.
        if seg.path is None:
            audio_clip = None
            audio_duration = 0.0
        else:
            # Load audio first — ffprobe/API durations can diverge from what MoviePy can read.
            audio_clip = AudioFileClip(str(seg.path))
            audio_duration = audio_clip.duration
        total_duration = audio_duration + gap

        # Base video: split at halfway point when a second image is provided
        if img2_path:
            half = audio_duration / 2
            clip1 = _make_image_clip(img_path, width, height, half)
            clip2 = _make_image_clip(img2_path, width, height, total_duration - half)
            video_clip = concatenate_videoclips([clip1, clip2], method="compose")
        else:
            video_clip = _make_image_clip(img_path, width, height, total_duration)

        sfx_entry = (sfx_map or {}).get(sentence.id)
        if sfx_entry:
            sfx_path, sfx_offset, sfx_duration = sfx_entry
            sfx_clip = AudioFileClip(str(sfx_path))
            if sfx_duration is not None:
                sfx_clip = sfx_clip.subclip(0, min(sfx_duration, sfx_clip.duration))
            sfx_clip = sfx_clip.set_start(max(sfx_offset, 0.0))
            clips_to_mix = ([audio_clip] if audio_clip else []) + [sfx_clip]
            video_clip = video_clip.set_audio(CompositeAudioClip(clips_to_mix))
        elif audio_clip:
            video_clip = video_clip.set_audio(audio_clip)

        # Captions
        if caption_style == "line" and sentence.text.strip():
            caption_frame = _render_caption_line(sentence.text, width, height, caption_font_size, caption_y_pct)
            caption_clip = ImageClip(caption_frame, ismask=False).set_duration(audio_duration)
            video_clip = CompositeVideoClip([video_clip, caption_clip])

        elif caption_style == "word":
            if not seg.words:
                # No word timestamps (e.g. TikTok TTS or empty sentence) — fall back to line captions
                if sentence.text.strip():
                    caption_frame = _render_caption_line(sentence.text, width, height, caption_font_size, caption_y_pct)
                    caption_clip = ImageClip(caption_frame, ismask=False).set_duration(audio_duration)
                    video_clip = CompositeVideoClip([video_clip, caption_clip])
            else:
                font, positions = _build_caption_layout(seg.words, width, height, caption_font_size, caption_y_pct)
                caption_clips = []
                for i, word in enumerate(seg.words):
                    end = seg.words[i + 1].start if i + 1 < len(seg.words) else audio_duration
                    duration = max(end - word.start, 0.05)
                    frame_arr = _render_caption_word(seg.words, i, width, height, font, positions)
                    wclip = (
                        ImageClip(frame_arr, ismask=False)
                        .set_start(word.start)
                        .set_duration(duration)
                    )
                    caption_clips.append(wclip)
                video_clip = CompositeVideoClip([video_clip] + caption_clips)

        # Per-sentence overlay — centered, alpha ramps to target by the midpoint
        ov_entry = (sentence_overlay_map or {}).get(sentence.id)
        if ov_entry:
            ov_path, ov_opacity, ov_size = ov_entry
            ov_clip = _make_overlay_clip(
                ov_path, width, height, total_duration,
                size_frac=ov_size, opacity=ov_opacity,
                fade_in=total_duration / 2,
                centered=True,
            )
            video_clip = CompositeVideoClip([video_clip, ov_clip])

        clips.append(video_clip)

    final = concatenate_videoclips(clips, method="compose")

    if overlay_image_path and overlay_image_path.exists():
        overlay = _make_overlay_clip(overlay_image_path, width, height, final.duration, size_frac=overlay_image_size)
        final = CompositeVideoClip([final, overlay])

    if music_path:
        music_duration = final.duration - music_start
        music = AudioFileClip(str(music_path)).volumex(music_volume)
        if music.duration < music_duration:
            music = afx.audio_loop(music, duration=music_duration)
        else:
            music = music.subclip(0, music_duration)
        music = music.set_start(music_start)
        final = final.set_audio(CompositeAudioClip([final.audio, music]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        preset="ultrafast",
        threads=multiprocessing.cpu_count(),
        logger="bar",
    )
