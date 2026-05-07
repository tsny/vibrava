import hashlib
from pathlib import Path

from vibrava.audio.tts import AudioSegment, WordTimestamp


def apply(
    seg: AudioSegment,
    pitch_shift: float = 0.0,
    speed: float = 1.0,
    cache_dir: Path | None = None,
) -> AudioSegment:
    """Apply pitch shift (semitones) and/or speed multiplier to a TTS segment."""
    if seg.path is None or (pitch_shift == 0.0 and speed == 1.0):
        return seg

    import librosa
    import soundfile as sf

    cache_key = hashlib.md5(f"{seg.path.stem}|{pitch_shift}|{speed}".encode()).hexdigest()
    out_dir = cache_dir or seg.path.parent / "fx"
    out_path = out_dir / f"{cache_key}.wav"

    if not out_path.exists():
        out_dir.mkdir(parents=True, exist_ok=True)
        y, sr = librosa.load(str(seg.path), sr=None, mono=True)

        if speed != 1.0:
            y = librosa.effects.time_stretch(y, rate=speed)

        if pitch_shift != 0.0:
            y = librosa.effects.pitch_shift(y, sr=sr, n_steps=pitch_shift)

        sf.write(str(out_path), y, sr)

    new_duration = seg.duration / speed
    new_words = [
        WordTimestamp(w.word, w.start / speed, w.end / speed) for w in seg.words
    ]
    return AudioSegment(path=out_path, duration=new_duration, words=new_words)
