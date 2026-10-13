"""Win95 dialogs: custom rule, seeding options, about, and an error box."""

from PyQt6.QtCore import QEventLoop, Qt
from PyQt6.QtGui import QKeyEvent
from PyQt6.QtWidgets import (QButtonGroup, QCheckBox, QGridLayout, QGroupBox, QHBoxLayout, QLabel, QLineEdit,
                             QPushButton, QRadioButton, QSlider, QSpinBox, QVBoxLayout, QWidget)

from cellbox import __version__
from cellbox.rules import AnyRule, RuleError, parse, preset_name
from cellbox.settings import SeedOptions, new_seed
from cellbox.sound import SoundBank
from cellbox.win95 import Win95Frame, icon_pixmap


class Win95Dialog(Win95Frame):
    """A modal Win95 window with exec(): True when accepted with OK."""

    def __init__(self, title: str, parent: QWidget | None):
        super().__init__(title, parent)
        self.setWindowModality(Qt.WindowModality.ApplicationModal)
        self.setWindowTitle(title)
        self._accepted = False
        self._loop: QEventLoop | None = None
        self.default_button: QPushButton | None = None

    def button_row(self, *labels: str) -> tuple[QHBoxLayout, list[QPushButton]]:
        row = QHBoxLayout()
        row.addStretch()
        buttons = []
        for label in labels:
            btn = QPushButton(label)
            btn.setMinimumWidth(75)
            row.addWidget(btn)
            buttons.append(btn)
        return row, buttons

    def accept(self) -> None:
        self._accepted = True
        self.close()

    def exec(self) -> bool:
        self.adjustSize()
        parent = self.parentWidget()
        if parent is not None:
            center = parent.frameGeometry().center()
            self.move(center.x() - self.width() // 2, center.y() - self.height() // 2)
        self.show()
        self.activateWindow()
        self._loop = QEventLoop()
        self.close_requested.connect(self._loop.quit)
        self._loop.exec()
        return self._accepted

    def keyPressEvent(self, event: QKeyEvent) -> None:
        if event.key() == Qt.Key.Key_Escape:
            self.close()
        elif event.key() in (Qt.Key.Key_Return, Qt.Key.Key_Enter) and self.default_button is not None:
            self.on_enter()
        else:
            super().keyPressEvent(event)

    def on_enter(self) -> None:
        if self.default_button.isEnabled():
            self.default_button.click()


class RuleDialog(Win95Dialog):
    """Type a rule string; the OK button only works for a valid rule."""

    HELP = ("B lists the neighbor counts that bring a dead cell to life, S the counts that keep a live "
            "cell alive. Add /C and a state count for Generations rules: B2/S/C3 is Brian's Brain. "
            "WireWorld runs electrons along wires. Continuous Lenia: Lenia R=13 T=10 m=0.15 s=0.015 b=1 "
            "(radius, steps per time unit, growth center and width, ring heights like 1/2;1).")

    def __init__(self, parent: QWidget, rule: AnyRule, sounds: SoundBank):
        super().__init__("Custom Rule", parent)
        self._sounds = sounds
        self.rule = rule

        self._edit = QLineEdit(str(rule))
        self._edit.setMinimumWidth(320)
        self._edit.textChanged.connect(self._validate)
        self._status = QLabel()
        self._status.setWordWrap(True)
        self._status.setMinimumHeight(30)
        help_label = QLabel(self.HELP)
        help_label.setWordWrap(True)
        help_label.setFixedWidth(360)

        row, (ok, cancel) = self.button_row("OK", "Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.close)
        self._ok = self.default_button = ok

        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(8)
        caption = QLabel("&Rule:")
        caption.setBuddy(self._edit)
        lay.addWidget(caption)
        lay.addWidget(self._edit)
        lay.addWidget(self._status)
        lay.addWidget(help_label)
        lay.addLayout(row)
        self._validate(self._edit.text())
        self._edit.selectAll()
        self._edit.setFocus()

    def _validate(self, text: str) -> None:
        try:
            rule = parse(text)
        except RuleError as e:
            self._status.setObjectName("error")
            self._status.setText(str(e))
            self._ok.setEnabled(False)
        else:
            self.rule = rule
            self._status.setObjectName("")
            name = preset_name(rule)
            self._status.setText(f"{name}. {rule.describe()}" if name else rule.describe())
            self._ok.setEnabled(True)
        self._status.style().unpolish(self._status)
        self._status.style().polish(self._status)

    def on_enter(self) -> None:
        if self._ok.isEnabled():
            self._ok.click()
        else:
            self._sounds.play("error")


class SeedDialog(Win95Dialog):
    """Density, zone and seed number for the random fill. OK reseeds the field."""

    def __init__(self, parent: QWidget, options: SeedOptions):
        super().__init__("Seed Field", parent)

        self._density = QSlider(Qt.Orientation.Horizontal)
        self._density.setRange(1, 100)
        self._density.setValue(options.density)
        self._density.setTickPosition(QSlider.TickPosition.TicksBelow)
        self._density.setTickInterval(10)
        self._density_label = QLabel()
        self._density_label.setMinimumWidth(32)
        self._density.valueChanged.connect(lambda v: self._density_label.setText(f"{v}%"))
        self._density_label.setText(f"{options.density}%")

        density_box = QGroupBox("Density")
        dl = QHBoxLayout(density_box)
        dl.addWidget(self._density, 1)
        dl.addWidget(self._density_label)

        self._whole = QRadioButton("&Whole field")
        self._spot = QRadioButton("&Center spot")
        group = QButtonGroup(self)
        group.addButton(self._whole)
        group.addButton(self._spot)
        (self._spot if options.spot else self._whole).setChecked(True)
        zone_box = QGroupBox("Zone")
        zl = QVBoxLayout(zone_box)
        zl.addWidget(self._whole)
        zl.addWidget(self._spot)

        self._seed = QSpinBox()
        self._seed.setRange(0, 999_999)
        self._seed.setValue(min(options.seed, 999_999))
        roll = QPushButton("&New")
        roll.clicked.connect(lambda: self._seed.setValue(new_seed()))
        self._fixed = QCheckBox("&Same seed every time")
        self._fixed.setChecked(options.fixed)
        seed_box = QGroupBox("Seed")
        sl = QGridLayout(seed_box)
        sl.addWidget(self._seed, 0, 0)
        sl.addWidget(roll, 0, 1)
        sl.addWidget(self._fixed, 1, 0, 1, 2)
        note = QLabel("Otherwise every reseed (R) picks a new seed.\nThe one in use is shown in the status bar.")
        note.setStyleSheet("color: #404040;")
        sl.addWidget(note, 2, 0, 1, 2)

        row, (ok, cancel) = self.button_row("Seed", "Cancel")
        ok.clicked.connect(self.accept)
        cancel.clicked.connect(self.close)
        self.default_button = ok

        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(10, 10, 10, 8)
        lay.setSpacing(8)
        lay.addWidget(density_box)
        lay.addWidget(zone_box)
        lay.addWidget(seed_box)
        lay.addLayout(row)
        self.setMinimumWidth(300)

    def options(self) -> SeedOptions:
        return SeedOptions(self._density.value(), self._spot.isChecked(), self._seed.value(), self._fixed.isChecked())


SHORTCUTS = (
    ("Space", "Run or pause"),
    ("N", "One step"),
    ("R", "Reseed"),
    ("C", "Clear"),
    ("+  /  -", "Zoom in / out"),
    ("F", "Fit the field to the window"),
    ("Drag", "Pan (the field wraps around)"),
    ("Wheel", "Zoom at the cursor"),
    ("Ctrl+O  /  Ctrl+S", "Open / save an RLE pattern"),
    ("Ctrl+C  /  Ctrl+V", "Copy the field / paste a pattern as RLE"),
    ("Click", "Place another copy of the pattern"),
    ("Right-click  /  T", "Turn the pattern"),
    ("Esc", "Stop placing"),
)


class AboutDialog(Win95Dialog):
    def __init__(self, parent: QWidget):
        super().__init__("About Cellbox", parent)
        icon = QLabel()
        icon.setPixmap(icon_pixmap("info"))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        text = QLabel(f"<b>Cellbox</b> {__version__}<br>Cellular automata in a Windows 95 box.<br>"
                      "Life-like, Generations, Wireworld and Lenia on a wrap-around field.<br><br>"
                      "Lenia creatures from Bert Chan's catalogue (MIT license).<br>© KosmoStars")
        keys = QGridLayout()
        keys.setHorizontalSpacing(16)
        keys.setVerticalSpacing(2)
        for i, (key, what) in enumerate(SHORTCUTS):
            keys.addWidget(QLabel(f"<b>{key}</b>"), i, 0)
            keys.addWidget(QLabel(what), i, 1)
        keys_box = QGroupBox("Keyboard and mouse")
        keys_box.setLayout(keys)

        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(icon)
        top.addWidget(text, 1)
        row, (ok,) = self.button_row("OK")
        ok.clicked.connect(self.close)
        self.default_button = ok

        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(10)
        lay.addLayout(top)
        lay.addWidget(keys_box)
        lay.addLayout(row)


class ErrorDialog(Win95Dialog):
    def __init__(self, title: str, message: str, parent: QWidget | None = None):
        super().__init__(title, parent)
        icon = QLabel()
        icon.setPixmap(icon_pixmap("error"))
        icon.setAlignment(Qt.AlignmentFlag.AlignTop)
        text = QLabel(message)
        text.setWordWrap(True)
        text.setFixedWidth(320)
        text.setTextInteractionFlags(Qt.TextInteractionFlag.TextSelectableByMouse)
        top = QHBoxLayout()
        top.setSpacing(12)
        top.addWidget(icon)
        top.addWidget(text, 1)
        row, (ok,) = self.button_row("OK")
        ok.clicked.connect(self.close)
        self.default_button = ok
        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(12, 12, 12, 8)
        lay.setSpacing(12)
        lay.addLayout(top)
        lay.addLayout(row)
