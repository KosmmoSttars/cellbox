# Cellbox

Cellular automata in a Windows 95 box. Pick a rule, seed the field, and watch it live.

- **Rules**: Life-like rules in B/S notation (`B3/S23` is Conway's Life) and Generations rules with
  fading dying cells (`B2/S/C3` is Brian's Brain). Twelve presets in the Rules menu, or type your own
  under Rules → Custom.
- **Field**: 128², 256², 512² or 1024² cells on a torus: the edges wrap around.
- **Colors**: the 16-color VGA palette. Life-like cells change color with age (newborn white, then
  yellow, lime, cyan, and blue for the long-lived); Generations cells fade from dark red to navy.
- **Seeding**: density, the whole field or a spot in the center, and a seed number to replay a run.
- **Speed**: 1 to 60 steps per second, or Max. A numba-compiled kernel steps a 1024² field about
  200 times a second.

Settings (rule, size, seeding, speed, window) are kept in `%APPDATA%\KosmoStars\Cellbox.ini`; the
compiled engine is cached in `%LOCALAPPDATA%\KosmoStars\Cellbox\numba`, so only the first launch compiles it.

## Keys

| Key | Action |
| --- | --- |
| Space | Run or pause |
| N | One step |
| R | Reseed |
| C | Clear |
| + / - | Zoom in / out (or the mouse wheel) |
| F | Fit the field to the window (or double-click) |
| Drag | Pan |

## Run

```
pip install -r requirements.txt
python main.py
```

Tests: `pip install -r requirements-dev.txt`, then `python -m pytest`.

Build a single portable `Cellbox.exe`: `python tools/build.py`. Sounds are synthesized by
`tools/make_sounds.py`; any WAV in `assets/sounds` can be swapped for your own.
