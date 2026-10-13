"""Cell colors from the 16-color VGA palette, as 256-entry color tables for an 8-bit QImage.

Life-like rules color a live cell by its age: newborn white, then yellow, lime, cyan and finally blue
for long-lived cells. Generations rules color by state: live cells white, dying cells fading from dark
red through purple to navy. Wireworld uses the classic colors: blue heads, red tails, yellow wire.
Lenia is continuous, so it gets the one 256-color table: a smooth ramp through VGA colors.
"""

from cellbox.rules import AnyRule, LeniaRule, Wireworld

VGA = {
    "black": 0x000000, "navy": 0x000080, "green": 0x008000, "teal": 0x008080,
    "maroon": 0x800000, "purple": 0x800080, "olive": 0x808000, "silver": 0xC0C0C0,
    "gray": 0x808080, "blue": 0x0000FF, "lime": 0x00FF00, "cyan": 0x00FFFF,
    "red": 0xFF0000, "magenta": 0xFF00FF, "yellow": 0xFFFF00, "white": 0xFFFFFF,
}

BACKGROUND = VGA["black"]

# (first age, color): a cell this old or older takes the color, until the next entry.
AGE_RAMP = ((1, "white"), (2, "yellow"), (3, "lime"), (7, "cyan"), (21, "blue"))
DYING_RAMP = ("maroon", "purple", "navy")
ALIVE = "white"


def _argb(rgb: int) -> int:
    return 0xFF000000 | rgb


def age_table() -> list[int]:
    table = [_argb(BACKGROUND)] * 256
    for i, (first, color) in enumerate(AGE_RAMP):
        last = AGE_RAMP[i + 1][0] if i + 1 < len(AGE_RAMP) else 256
        for age in range(first, last):
            table[age] = _argb(VGA[color])
    return table


def state_table(states: int) -> list[int]:
    table = [_argb(BACKGROUND)] * 256
    table[1] = _argb(VGA[ALIVE])
    dying = states - 2
    for k in range(dying):   # spread the ramp evenly over however many dying states there are
        table[2 + k] = _argb(VGA[DYING_RAMP[k * len(DYING_RAMP) // dying]])
    return table


# Wireworld by state: empty, head, tail, wire
WIRE_COLORS = ("black", "blue", "red", "yellow")

# Lenia: (value, color) stops, linearly blended in between
LENIA_RAMP = ((0.0, 0x000000), (0.18, 0x000080), (0.38, 0x0060C0), (0.58, 0x00C0A0), (0.76, 0x80FF40),
              (0.92, 0xFFFF00), (1.0, 0xFFFFFF))


def wire_table() -> list[int]:
    table = [_argb(BACKGROUND)] * 256
    for state, color in enumerate(WIRE_COLORS):
        table[state] = _argb(VGA[color])
    return table


def _blend(a: int, b: int, t: float) -> int:
    channels = [round(((a >> s) & 255) * (1 - t) + ((b >> s) & 255) * t) for s in (16, 8, 0)]
    return (channels[0] << 16) | (channels[1] << 8) | channels[2]


def lenia_table() -> list[int]:
    table = []
    for i in range(256):
        v = i / 255
        for (v0, c0), (v1, c1) in zip(LENIA_RAMP, LENIA_RAMP[1:]):
            if v <= v1:
                table.append(_argb(_blend(c0, c1, (v - v0) / (v1 - v0))))
                break
    return table


def color_table(rule: AnyRule) -> list[int]:
    if isinstance(rule, LeniaRule):
        return lenia_table()
    if isinstance(rule, Wireworld):
        return wire_table()
    return state_table(rule.states) if rule.is_generations else age_table()
