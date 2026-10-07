"""Synthesizes Cellbox's sound effects into assets/sounds/.

All sounds are generated from scratch (no samples), so they are free to ship. Building blocks and the
error chord come from Floppy's generator. Run again any time to restore the defaults:

    python tools/make_sounds.py [--force]

Any WAV file can be replaced with your own recording (16-bit PCM WAV) without changing code.
"""

import math
import random
import struct
import sys
import wave
from pathlib import Path

SR = 44100
OUT = Path(__file__).resolve().parent.parent / "assets" / "sounds"


def silence(seconds: float) -> list[float]:
    return [0.0] * int(seconds * SR)


def mix_into(buf: list[float], part: list[float], at: float, gain: float = 1.0) -> None:
    start = int(at * SR)
    if start + len(part) > len(buf):
        buf.extend([0.0] * (start + len(part) - len(buf)))
    for i, v in enumerate(part):
        buf[start + i] += v * gain


def damped(freq: float, seconds: float, tau: float, phase: float = 0.0) -> list[float]:
    """A decaying sine: the basic 'ping' of a struck piece of metal."""
    n = int(seconds * SR)
    return [math.sin(2 * math.pi * freq * i / SR + phase) * math.exp(-i / SR / tau) for i in range(n)]


def noise_burst(seconds: float, tau: float, smooth: float = 0.0) -> list[float]:
    """Decaying noise; smooth (0..1) is a one-pole low-pass amount."""
    out, prev = [], 0.0
    for i in range(int(seconds * SR)):
        v = random.uniform(-1, 1)
        prev = prev * smooth + v * (1 - smooth)
        out.append(prev * math.exp(-i / SR / tau))
    return out


def fade(buf: list[float], fade_in: float = 0.004, fade_out: float = 0.01) -> list[float]:
    n_in, n_out = int(fade_in * SR), int(fade_out * SR)
    for i in range(min(n_in, len(buf))):
        buf[i] *= i / n_in
    for i in range(min(n_out, len(buf))):
        buf[-1 - i] *= i / n_out
    return buf


def save(name: str, buf: list[float], peak: float = 0.89) -> None:
    top = max(1e-9, max(abs(v) for v in buf))
    data = b"".join(struct.pack("<h", int(v / top * peak * 32767)) for v in buf)
    with wave.open(str(OUT / name), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(SR)
        w.writeframes(data)


def click() -> list[float]:
    """A short plastic button click: a tick and a tiny body thump."""
    buf = silence(0.05)
    mix_into(buf, noise_burst(0.004, 0.0009, 0.3), 0.0, 0.7)
    mix_into(buf, damped(2900, 0.012, 0.0022), 0.0, 0.45)
    mix_into(buf, damped(420, 0.03, 0.006), 0.001, 0.35)
    return fade(buf, 0.0005, 0.01)


def error() -> list[float]:
    """An original dissonant 'something went wrong' chord (not the real Windows sound)."""
    seconds = 0.75
    notes = ((440.0, 1.0), (622.25, 0.8), (164.81, 0.6))   # A4 + D#5 tritone over E3
    buf = []
    for i in range(int(seconds * SR)):
        tt = i / SR
        env = (1 - math.exp(-tt / 0.004)) * math.exp(-tt / 0.28)
        vib = 1 + 0.003 * math.sin(2 * math.pi * 6 * tt)
        s = 0.0
        for f, g in notes:
            s += g * (math.sin(2 * math.pi * f * vib * tt) + 0.3 * math.sin(4 * math.pi * f * vib * tt))
        buf.append(s * env)
    return fade(buf)


SOUNDS = {
    "click.wav": (click, 0.5),
    "error.wav": (error, 0.89),
}


def main() -> None:
    force = "--force" in sys.argv
    random.seed(144)
    OUT.mkdir(parents=True, exist_ok=True)
    for name, (make, peak) in SOUNDS.items():
        if (OUT / name).exists() and not force:
            print(f"keep   {name} (exists; use --force to regenerate)")
            continue
        save(name, make(), peak)
        print(f"wrote  {name}")


if __name__ == "__main__":
    main()
