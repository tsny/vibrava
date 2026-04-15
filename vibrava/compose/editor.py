from pathlib import Path

import numpy as np
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
# Font loading
# ---------------------------------------------------------------------------

_FONT_CANDIDATES = [
    "/System/Library/Fonts/Helvetica.ttc",
    "/System/Library/Fonts/Arial.ttf",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "/usr/share/fonts/truetype/liberation/LiberationSans-Bold.ttf",
]


def _load_font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    for path in _FONT_CANDIDATES:
        try:
            return ImageFont.truetype(path, size)
        except (OSError, IOError):
            continue
    return ImageFont.load_default()


# ---------------------------------------------------------------------------
# Frame builders
# ---------------------------------------------------------------------------

def _make_background_frame(img_path: Path, width: int, height: int) -> np.ndarray:
    """
    Image scaled to fit (with padding) centered on a black background.
    """
    img = Image.open(img_path).convert("RGB")

    bg = Image.new("RGB", (width, height), (0, 0, 0))

    padding = 0.90
    fg_ratio = min(width / img.width, height / img.height) * padding
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


def _render_caption_line(text: str, width: int, height: int) -> np.ndarray:
    """Render the full sentence as white text with black stroke near the bottom."""
    font_size = max(44, height // 26)
    font = _load_font(font_size)
    max_text_width = int(width * 0.88)
    lines = _wrap_text(text, font, max_text_width)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    line_height = font_size + 12
    total_text_height = len(lines) * line_height
    y = height - total_text_height - 120

    for line in lines:
        bbox = draw.textbbox((0, 0), line, font=font)
        x = (width - (bbox[2] - bbox[0])) // 2
        draw.text((x, y), line, font=font, fill="white", stroke_width=4, stroke_fill="black")
        y += line_height

    return np.array(img)


def _render_caption_word(
    words: list[WordTimestamp],
    current_word_idx: int,
    width: int,
    height: int,
) -> np.ndarray:
    """
    Render all words of the sentence near the bottom, with the current
    word highlighted in yellow.
    """
    font_size = max(44, height // 26)
    font = _load_font(font_size)
    full_text = " ".join(w.word for w in words)
    max_text_width = int(width * 0.88)
    lines = _wrap_text(full_text, font, max_text_width)

    img = Image.new("RGBA", (width, height), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    line_height = font_size + 12
    total_text_height = len(lines) * line_height
    y = height - total_text_height - 120

    current_word = words[current_word_idx].word if current_word_idx < len(words) else ""
    word_counter = 0

    for line in lines:
        line_words = line.split()
        x_cursor = (width - draw.textbbox((0, 0), line, font=font)[2]) // 2

        for word in line_words:
            color = "yellow" if word == current_word and word_counter == current_word_idx else "white"
            draw.text((x_cursor, y), word, font=font, fill=color, stroke_width=4, stroke_fill="black")
            word_width = draw.textbbox((0, 0), word + " ", font=font)[2]
            x_cursor += word_width
            word_counter += 1

        y += line_height

    return np.array(img)


# ---------------------------------------------------------------------------
# GIF clip builder
# ---------------------------------------------------------------------------

_VIDEO_EXTENSIONS = {".mp4", ".mov", ".avi", ".webm"}


def _make_video_clip(video_path: Path, width: int, height: int):
    """Load a video clip and scale-to-fit with padding. Plays at natural duration."""
    clip = VideoFileClip(str(video_path), audio=False)
    padding = 0.90
    scale = min(width / clip.w, height / clip.h) * padding
    new_w, new_h = int(clip.w * scale), int(clip.h * scale)
    clip = clip.resize((new_w, new_h))
    bg = ColorClip((width, height), color=(0, 0, 0)).set_duration(clip.duration)
    clip = clip.set_position(((width - new_w) // 2, (height - new_h) // 2))
    return CompositeVideoClip([bg, clip])


def _make_gif_clip(gif_path: Path, width: int, height: int, duration: float):
    """Load an animated GIF via PIL, resize frames, loop to fill duration."""
    gif = Image.open(gif_path)
    padding = 0.90

    frames = []
    frame_durations = []
    try:
        while True:
            frame = gif.copy().convert("RGB")
            scale = min(width / frame.width, height / frame.height) * padding
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
# Main build function
# ---------------------------------------------------------------------------

def build(
    sentences: list[Sentence],
    audio_map: dict[str, AudioSegment],
    image_map: dict[str, Path | None],
    output_path: Path,
    resolution: tuple[int, int],
    pause_duration: float,
    caption_style: str,
    music_path: Path | None = None,
    music_volume: float = 0.15,
    fps: int = 30,
) -> None:
    width, height = resolution
    clips = []

    for sentence in sentences:
        seg = audio_map[sentence.id]
        img_path = image_map.get(sentence.id)
        total_duration = seg.duration + pause_duration

        # Base video frame
        if img_path and img_path.exists():
            ext = img_path.suffix.lower()
            if ext in _VIDEO_EXTENSIONS:
                video_clip = _make_video_clip(img_path, width, height)
            elif ext == ".gif":
                video_clip = _make_gif_clip(img_path, width, height, total_duration)
            else:
                frame = _make_background_frame(img_path, width, height)
                video_clip = ImageClip(frame).set_duration(total_duration)
        else:
            frame = np.zeros((height, width, 3), dtype=np.uint8)
            video_clip = ImageClip(frame).set_duration(total_duration)

        # Audio — only for speech portion, silence fills the pause naturally
        audio_clip = AudioFileClip(str(seg.path)).subclip(0, seg.duration)
        video_clip = video_clip.set_audio(audio_clip)

        # Captions
        if caption_style == "line":
            caption_frame = _render_caption_line(sentence.text, width, height)
            caption_clip = ImageClip(caption_frame, ismask=False).set_duration(seg.duration)
            video_clip = CompositeVideoClip([video_clip, caption_clip])

        elif caption_style == "word" and seg.words:
            caption_clips = []
            for i, word in enumerate(seg.words):
                end = seg.words[i + 1].start if i + 1 < len(seg.words) else seg.duration
                duration = max(end - word.start, 0.05)
                frame_arr = _render_caption_word(seg.words, i, width, height)
                wclip = (
                    ImageClip(frame_arr, ismask=False)
                    .set_start(word.start)
                    .set_duration(duration)
                )
                caption_clips.append(wclip)
            video_clip = CompositeVideoClip([video_clip] + caption_clips)

        clips.append(video_clip)

    final = concatenate_videoclips(clips, method="compose")

    if music_path:
        music = AudioFileClip(str(music_path)).volumex(music_volume)
        if music.duration < final.duration:
            music = afx.audio_loop(music, duration=final.duration)
        else:
            music = music.subclip(0, final.duration)
        final = final.set_audio(CompositeAudioClip([final.audio, music]))

    output_path.parent.mkdir(parents=True, exist_ok=True)
    final.write_videofile(
        str(output_path),
        fps=fps,
        codec="libx264",
        audio_codec="aac",
        logger=None,
    )
