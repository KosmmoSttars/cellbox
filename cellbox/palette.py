"""Cell colors from the 16-color VGA palette, as 256-entry color tables for an 8-bit QImage.

Life-like rules color a live cell by its age: newborn white, then yellow, lime, cyan and finally blue
for long-lived cells. Generations rules color by state: live cells white, dying cells fading from dark
red through purple to navy.
"""

from cellbox.rules import Rule

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


def color_table(rule: Rule) -> list[int]:
    return state_table(rule.states) if rule.is_generations else age_table()
