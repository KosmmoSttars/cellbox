"""The main window: menu bar, toolbar, the field, status bar."""

import time
from collections import deque
from pathlib import Path

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PyQt6.QtWidgets import (QApplication, QFileDialog, QFrame, QHBoxLayout, QLabel, QMenu, QMenuBar, QSlider,
                             QToolButton, QVBoxLayout, QWidget)

from cellbox.canvas import FieldView
from cellbox.dialogs import AboutDialog, ErrorDialog, RuleDialog, SeedDialog
from cellbox.engine import SIZES, Field
from cellbox.icon import app_icon, icon_pixmap
from cellbox.palette import color_table
from cellbox.patterns import Pattern, PatternError, library, load_rle, parse_rle, species, to_rle
from cellbox.rules import PRESET_GROUPS, AnyRule, LeniaRule, Wireworld, preset_for, preset_name
from cellbox.settings import SPEED_MAX, Settings, new_seed
from cellbox.sound import SoundBank
from cellbox.win95 import Win95Frame, glyph

MAX_FRAME_BUDGET = 0.012   # seconds of stepping per frame at Max speed (the rest is for drawing)
FRAME_MS = 16
STATUS_EVERY = 0.1         # seconds between status bar refreshes
PATTERN_ROOM = 3           # a loaded pattern gets a field at least this many times its size, if one exists
RLE_FILTER = "Patterns (*.rle);;All files (*.*)"


class StatusPanel(QLabel):
    def __init__(self, min_width: int):
        super().__init__()
        self.setFrameStyle(QFrame.Shape.Panel | QFrame.Shadow.Sunken)
        self.setMinimumWidth(min_width)
        self.setContentsMargins(3, 0, 3, 0)


class MainWindow(Win95Frame):
    def __init__(self, settings: Settings):
        super().__init__("Cellbox", resizable=True, icon=icon_pixmap(16))
        self.setWindowIcon(app_icon())
        self.setAcceptDrops(True)
        self.settings = settings
        self.sounds = SoundBank(settings.sound, self)
        self.seeding = settings.seeding
        self.field = Field(settings.size, settings.rule)
        self.view = FieldView(self.field)
        self.view.view_changed.connect(self._update_status)
        self.view.stamp_requested.connect(self._stamp)
        self.loaded: str | None = None   # the name of the pattern the field started from, if not a seed
        self.creature: Pattern | None = None   # the Lenia creature a reseed scatters, when not a preset's

        self.running = False
        self.speed = settings.speed
        self._step_times: deque[float] = deque()
        self._last_status = 0.0
        self._timer = QTimer(self)
        self._timer.setTimerType(Qt.TimerType.PreciseTimer)
        self._timer.timeout.connect(self._tick)

        self._build_actions()
        menu_bar = self._build_menus()
        toolbar = self._build_toolbar()
        well = QFrame()
        well.setFrameStyle(QFrame.Shape.WinPanel | QFrame.Shadow.Sunken)
        wl = QVBoxLayout(well)
        wl.setContentsMargins(2, 2, 2, 2)
        wl.addWidget(self.view)
        status = self._build_status()

        lay = QVBoxLayout(self.body)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        lay.addWidget(menu_bar)
        lay.addWidget(toolbar)
        lay.addWidget(well, 1)
        lay.addWidget(status)

        self._apply_rule(self.field.rule, save=False, reseed=False)
        self._apply_speed(self.speed)
        self._restore_window()
        self.reseed()

    # --- actions, menus, toolbar ------------------------------------------------------------

    def _action(self, text: str, slot, shortcut=None, checkable: bool = False) -> QAction:
        action = QAction(text, self)
        if shortcut is not None:
            shortcuts = shortcut if isinstance(shortcut, list) else [shortcut]
            action.setShortcuts([QKeySequence(s) for s in shortcuts])
        action.setCheckable(checkable)
        action.triggered.connect(slot)
        self.addAction(action)   # shortcuts work wherever the focus is in the window
        return action

    def _build_actions(self) -> None:
        self.act_open = self._action("&Open Pattern...", self.open_pattern, "Ctrl+O")
        self.act_paste = self._action("&Paste Pattern", self.paste_pattern, "Ctrl+V")
        self.act_save = self._action("&Save Pattern As...", self.save_pattern, "Ctrl+S")
        self.act_copy = self._action("&Copy Pattern", self.copy_pattern, "Ctrl+C")
        self.act_run = self._action("&Run", self.toggle_running, "Space")
        self.act_step = self._action("&Step", self.step_once, "N")
        self.act_reseed = self._action("&Reseed", self.reseed, "R")
        self.act_seed_options = self._action("Seed &Options...", self.seed_options)
        self.act_clear = self._action("&Clear", self.clear, "C")
        self.act_custom = self._action("&Custom...", self.custom_rule)
        self.act_stop_placing = self._action("S&top Placing\tEsc", self.stop_placing, "Esc")
        self.act_rotate = self._action("&Turn Pattern\tRight-click", self.view.rotate_pattern, "T")
        self.act_zoom_in = self._action("Zoom &In", self.view.zoom_in, ["+", "="])
        self.act_zoom_out = self._action("Zoom &Out", self.view.zoom_out, ["-"])
        self.act_fit = self._action("&Fit to Window", self.view.fit, "F")
        self.act_sound = self._action("&Sounds", self._toggle_sound, checkable=True)
        self.act_sound.setChecked(self.sounds.enabled)
        self.act_exit = self._action("E&xit", self.close)
        self.act_about = self._action("&About Cellbox", lambda: AboutDialog(self).exec())

        self._rule_group = QActionGroup(self)
        self._rule_actions: dict[AnyRule, QAction] = {}
        for group in PRESET_GROUPS.values():
            for preset in group:
                label = preset.name if preset.rule.family == "lenia" else f"{preset.name}\t{preset.rule}"
                action = QAction(label, self, checkable=True)
                action.triggered.connect(lambda _=False, r=preset.rule: self._apply_rule(r))
                self._rule_group.addAction(action)
                self._rule_actions[preset.rule] = action

        self._size_group = QActionGroup(self)
        self._size_actions: dict[int, QAction] = {}
        for size in SIZES:
            action = QAction(f"{size} x {size}", self, checkable=True)
            action.triggered.connect(lambda _=False, s=size: self.set_size(s))
            self._size_group.addAction(action)
            self._size_actions[size] = action
        self._size_actions[self.field.size].setChecked(True)

    def _build_menus(self) -> QMenuBar:
        bar = QMenuBar()
        file = bar.addMenu("&File")
        for action in (self.act_open, self.act_save, None, self.act_copy, self.act_paste, None, self.act_exit):
            file.addSeparator() if action is None else file.addAction(action)

        sim = bar.addMenu("&Simulation")
        for action in (self.act_run, self.act_step, None, self.act_reseed, self.act_seed_options,
                       self.act_clear):
            sim.addSeparator() if action is None else sim.addAction(action)

        self.rules_menu = bar.addMenu("&Rules")
        for title, group in PRESET_GROUPS.items():
            if len(group) == 1:
                self.rules_menu.addAction(self._rule_actions[group[0].rule])
                continue
            sub = self.rules_menu.addMenu(title)
            for preset in group:
                sub.addAction(self._rule_actions[preset.rule])
        self.rules_menu.addSeparator()
        self.rules_menu.addAction(self.act_custom)

        self.patterns_menu = bar.addMenu("&Patterns")
        for title, patterns in library().items():
            sub = self.patterns_menu.addMenu(title)
            section = None
            for pattern in patterns:
                if section is not None and pattern.section != section:
                    sub.addSeparator()
                section = pattern.section
                action = sub.addAction(pattern.name)
                action.triggered.connect(lambda _=False, p=pattern: self.load_pattern(p))
        self.patterns_menu.addSeparator()
        self.patterns_menu.addAction(self.act_open)
        self.patterns_menu.addAction(self.act_rotate)
        self.patterns_menu.addAction(self.act_stop_placing)

        view = bar.addMenu("&View")
        sizes = view.addMenu("Field &Size")
        for action in self._size_actions.values():
            sizes.addAction(action)
        view.addSeparator()
        for action in (self.act_zoom_in, self.act_zoom_out, self.act_fit):
            view.addAction(action)
        view.addSeparator()
        view.addAction(self.act_sound)

        help_menu = bar.addMenu("&Help")
        help_menu.addAction(self.act_about)
        self._update_placing_actions()
        return bar

    def _tool(self, name: str, tip: str, slot=None, menu: QMenu | None = None) -> QToolButton:
        btn = QToolButton()
        btn.setIcon(QIcon(glyph(name)))
        btn.setIconSize(QSize(16, 16))
        btn.setAutoRaise(True)
        btn.setToolTip(tip)
        btn.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        btn.pressed.connect(lambda: self.sounds.play("click"))
        if menu is not None:
            btn.setMenu(menu)
            btn.setPopupMode(QToolButton.ToolButtonPopupMode.InstantPopup)
        else:
            btn.clicked.connect(slot)
        return btn

    @staticmethod
    def _separator() -> QFrame:
        line = QFrame()
        line.setFrameStyle(QFrame.Shape.VLine | QFrame.Shadow.Sunken)
        line.setFixedHeight(20)
        return line

    def _build_toolbar(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(2, 1, 2, 1)
        lay.setSpacing(1)
        self.btn_run = self._tool("play", "Run (Space)", self.toggle_running)
        groups = (
            (self._tool("open", "Open pattern (Ctrl+O)", self.open_pattern),),
            (self.btn_run, self._tool("step", "Step (N)", self.step_once)),
            (self._tool("seed", "Reseed (R)", self.reseed), self._tool("clear", "Clear (C)", self.clear)),
            (self._tool("rules", "Rules", menu=self.rules_menu),
             self._tool("patterns", "Patterns", menu=self.patterns_menu)),
            (self._tool("zoom_out", "Zoom out (-)", self.view.zoom_out),
             self._tool("zoom_in", "Zoom in (+)", self.view.zoom_in),
             self._tool("fit", "Fit to window (F)", self.view.fit)),
        )
        for i, group in enumerate(groups):
            if i:
                lay.addSpacing(3)
                lay.addWidget(self._separator())
                lay.addSpacing(3)
            for btn in group:
                lay.addWidget(btn)
        lay.addSpacing(3)
        lay.addWidget(self._separator())
        lay.addSpacing(6)

        lay.addWidget(QLabel("Speed:"))
        self.speed_slider = QSlider(Qt.Orientation.Horizontal)
        self.speed_slider.setRange(1, SPEED_MAX)
        self.speed_slider.setFixedWidth(150)
        self.speed_slider.setFocusPolicy(Qt.FocusPolicy.NoFocus)
        self.speed_slider.setValue(self.speed)
        self.speed_slider.valueChanged.connect(self._apply_speed)
        lay.addWidget(self.speed_slider)
        self.speed_label = QLabel()
        self.speed_label.setMinimumWidth(60)
        lay.addWidget(self.speed_label)
        lay.addStretch()
        return bar

    def _build_status(self) -> QWidget:
        bar = QWidget()
        lay = QHBoxLayout(bar)
        lay.setContentsMargins(0, 0, 0, 0)
        lay.setSpacing(2)
        self.st_generation = StatusPanel(110)
        self.st_population = StatusPanel(120)
        self.st_rate = StatusPanel(80)
        self.st_rule = StatusPanel(120)
        self.st_view = StatusPanel(110)
        self.st_seed = StatusPanel(80)
        self.st_generation.setToolTip("Generation")
        self.st_rate.setToolTip("Steps per second, measured")
        lay.addWidget(self.st_generation)
        lay.addWidget(self.st_population)
        lay.addWidget(self.st_rate)
        lay.addWidget(self.st_rule, 1)
        lay.addWidget(self.st_view)
        lay.addWidget(self.st_seed)
        return bar

    # --- the simulation ---------------------------------------------------------------------

    def toggle_running(self) -> None:
        self.running = not self.running
        if self.running:
            self._timer.start()
        else:
            self._timer.stop()
            self._step_times.clear()
        self.act_run.setText("&Pause" if self.running else "&Run")
        self.btn_run.setIcon(QIcon(glyph("pause" if self.running else "play")))
        self.btn_run.setToolTip("Pause (Space)" if self.running else "Run (Space)")
        self._update_status()

    def _apply_speed(self, speed: int) -> None:
        self.speed = speed
        self.settings.speed = speed
        self.speed_label.setText("Max" if speed == SPEED_MAX else f"{speed} / s")
        self._timer.setInterval(FRAME_MS if speed == SPEED_MAX else round(1000 / speed))

    def _tick(self) -> None:
        now = time.perf_counter()
        if self.speed == SPEED_MAX:
            steps = 0
            while time.perf_counter() - now < MAX_FRAME_BUDGET:
                self.field.step()
                steps += 1
        else:
            self.field.step()
            steps = 1
        self._step_times.extend([now] * steps)
        self.view.update()
        if now - self._last_status >= STATUS_EVERY:
            self._update_status()

    def step_once(self) -> None:
        if self.running:
            self.toggle_running()
        self.field.step()
        self.view.update()
        self._update_status()

    def reseed(self) -> None:
        if not self.seeding.fixed:
            self.seeding.seed = new_seed()
        self.settings.seeding = self.seeding
        preset = preset_for(self.field.rule)
        creature = species(preset.species) if preset and preset.species else None
        if creature is None and self.creature is not None and self.creature.rule == self.field.rule:
            creature = self.creature
        self.field.seed(self.seeding.density / 100, self.seeding.spot, self.seeding.seed,
                        creature.cells if creature else None)
        self.loaded = None
        self.view.update()
        self._update_status()

    def seed_options(self) -> None:
        dialog = SeedDialog(self, self.seeding)
        if dialog.exec():
            self.seeding = dialog.options()
            self.seeding.fixed = True   # reseed with exactly what was just chosen...
            self.reseed()
            self.seeding.fixed = dialog.options().fixed   # ...then follow the checkbox
            self.settings.seeding = self.seeding

    def clear(self) -> None:
        self.field.clear()
        self.loaded = None
        self.view.update()
        self._update_status()

    def set_size(self, size: int, reseed: bool = True) -> None:
        if size == self.field.size:
            return
        self.field.resize(size)
        self.settings.size = size
        self._size_actions[size].setChecked(True)
        if reseed:
            self.reseed()
        self.view.fit()

    # --- rules ------------------------------------------------------------------------------

    def _apply_rule(self, rule: AnyRule, save: bool = True, reseed: bool = True) -> None:
        family_changed = rule.family != self.field.rule.family
        self.field.rule = rule
        self.view.set_color_table(color_table(rule))
        action = self._rule_actions.get(rule)
        if action is not None:
            action.setChecked(True)
        elif self._rule_group.checkedAction() is not None:
            self._rule_group.checkedAction().setChecked(False)
        name = preset_name(rule)
        if name is None and self.creature is not None and self.creature.rule == rule:
            name = self.creature.name
        short = name or ("Lenia" if isinstance(rule, LeniaRule) else str(rule))
        self.set_title(f"Cellbox - {short}")
        self.st_rule.setText(f"{name}  ({rule})" if name else f"Custom  ({rule})")
        self.st_population.setToolTip("Electron heads" if isinstance(rule, Wireworld)
                                      else "Sum of all cell values" if isinstance(rule, LeniaRule)
                                      else "Live cells")
        if save:
            self.settings.rule = rule
        # a Lenia creature is only itself with its own rule: a new Lenia rule gets a fresh start too
        if reseed and (family_changed or isinstance(rule, LeniaRule)):
            self.reseed()
        self._update_status()

    def custom_rule(self) -> None:
        dialog = RuleDialog(self, self.field.rule, self.sounds)
        if dialog.exec():
            self._apply_rule(dialog.rule)

    # --- patterns ---------------------------------------------------------------------------

    def load_pattern(self, pattern: Pattern) -> None:
        """A fresh field with the pattern in the middle; then more copies can be clicked into place."""
        if pattern.code is not None:
            self.creature = pattern
        if pattern.rule != self.field.rule or pattern.code is not None:
            self._apply_rule(pattern.rule, reseed=False)
        biggest = max(pattern.width, pattern.height)
        if biggest > SIZES[-1]:
            ErrorDialog("Cellbox", f"{pattern.name} is {pattern.width} x {pattern.height} cells: bigger than "
                                   f"the biggest field ({SIZES[-1]} x {SIZES[-1]}).", self).exec()
            return
        if biggest * PATTERN_ROOM > self.field.size:
            fitting = [s for s in SIZES if s >= biggest * PATTERN_ROOM] or [SIZES[-1]]
            self.set_size(fitting[0], reseed=False)
        self.field.clear()
        n = self.field.size
        top, left = (n - pattern.height) // 2, (n - pattern.width) // 2
        self.field.stamp(pattern.cells, top, left)
        self.loaded = pattern.name
        self.view.show_area(n / 2, n / 2, int(pattern.height * 2.5), int(pattern.width * 2.5))
        self.view.update()
        self._place(pattern)
        if not self.running:
            self.toggle_running()

    def _place(self, pattern: Pattern) -> None:
        self.view.set_pattern(pattern)
        self._update_placing_actions()
        self._update_status()

    def stop_placing(self) -> None:
        if self.view.pattern is not None:
            self.view.set_pattern(None)
            self._update_placing_actions()
            self._update_status()

    def _update_placing_actions(self) -> None:
        placing = self.view.pattern is not None
        self.act_stop_placing.setEnabled(placing)
        self.act_rotate.setEnabled(placing)

    def _stamp(self, row: int, col: int) -> None:
        pattern = self.view.pattern
        if pattern is None:
            return
        if pattern.rule.family != self.field.rule.family:
            self._apply_rule(pattern.rule, reseed=False)
        try:
            self.field.stamp(pattern.cells, row, col)
        except ValueError as e:
            ErrorDialog("Cellbox", str(e), self).exec()
            return
        self.sounds.play("click")
        self.view.update()
        self._update_status()

    def _open_text(self, text: str, name: str) -> None:
        try:
            pattern = parse_rle(text, name=name)
        except PatternError as e:
            self.sounds.play("error")
            ErrorDialog("Cellbox", str(e), self).exec()
            return
        self.load_pattern(pattern)

    def open_path(self, path: Path) -> None:
        try:
            pattern = load_rle(path)
        except PatternError as e:
            self.sounds.play("error")
            ErrorDialog("Cellbox", str(e), self).exec()
            return
        self.settings.last_folder = str(path.parent)
        self.load_pattern(pattern)

    def _file_dialog(self, title: str, save: bool, name: str = "") -> str:
        dialog = QFileDialog(self, title, str(Path(self.settings.last_folder) / name), RLE_FILTER)
        dialog.setOption(QFileDialog.Option.DontUseNativeDialog)   # keeps the Win95 look
        dialog.setAcceptMode(QFileDialog.AcceptMode.AcceptSave if save else QFileDialog.AcceptMode.AcceptOpen)
        dialog.setFileMode(QFileDialog.FileMode.AnyFile if save else QFileDialog.FileMode.ExistingFile)
        dialog.setDefaultSuffix("rle")
        if not dialog.exec() or not dialog.selectedFiles():
            return ""
        return dialog.selectedFiles()[0]

    def open_pattern(self) -> None:
        path = self._file_dialog("Open Pattern", save=False)
        if path:
            self.open_path(Path(path))

    def paste_pattern(self) -> None:
        text = QApplication.clipboard().text()
        if not text.strip():
            self.sounds.play("error")
            ErrorDialog("Cellbox", "The clipboard is empty. Copy a pattern in RLE format first, for example "
                                   "from LifeWiki or Golly.", self).exec()
            return
        self._open_text(text, "Pasted pattern")

    def _current_pattern(self) -> Pattern | None:
        cells = self.field.extract()
        if cells is None:
            self.sounds.play("error")
            ErrorDialog("Cellbox", "The field is empty: there is nothing to save.", self).exec()
            return None
        name = self.loaded or "Cellbox pattern"
        return Pattern(name, self.field.rule, cells,
                       comments=(f"Generation {self.field.generation:,} in Cellbox.",))

    def save_pattern(self) -> None:
        pattern = self._current_pattern()
        if pattern is None:
            return
        path = self._file_dialog("Save Pattern As", save=True, name=f"{pattern.name}.rle")
        if not path:
            return
        try:
            Path(path).write_text(to_rle(pattern), encoding="utf-8")
        except OSError as e:
            ErrorDialog("Cellbox", f"Could not save the pattern.\n{e.strerror or e}", self).exec()
            return
        self.settings.last_folder = str(Path(path).parent)

    def copy_pattern(self) -> None:
        pattern = self._current_pattern()
        if pattern is not None:
            QApplication.clipboard().setText(to_rle(pattern))

    def dragEnterEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile() or event.mimeData().hasText():
            event.acceptProposedAction()

    def dropEvent(self, event) -> None:
        urls = event.mimeData().urls()
        if urls and urls[0].isLocalFile():
            self.open_path(Path(urls[0].toLocalFile()))
        elif event.mimeData().hasText():
            self._open_text(event.mimeData().text(), "Dropped pattern")

    # --- status, sound, window --------------------------------------------------------------

    def _update_status(self) -> None:
        now = time.perf_counter()
        self._last_status = now
        while self._step_times and now - self._step_times[0] > 1.0:
            self._step_times.popleft()
        f = self.field
        self.st_generation.setText(f"Generation {f.generation:,}")
        if isinstance(f.rule, LeniaRule):
            self.st_population.setText(f"Mass {f.population:,.0f}")
        elif isinstance(f.rule, Wireworld):
            self.st_population.setText(f"Electrons {f.population:,}")
        else:
            self.st_population.setText(f"Population {f.population:,}")
        self.st_rate.setText(f"{len(self._step_times)} steps/s" if self.running else "Paused")
        self.st_view.setText(f"{f.size} x {f.size}, zoom {self.view.zoom}x")
        if self.view.pattern is not None:
            self.st_seed.setText("Click: place  Right-click: turn  Esc: done")
        elif self.loaded:
            self.st_seed.setText(self.loaded)
        else:
            self.st_seed.setText(f"Seed {self.seeding.seed}")

    def _toggle_sound(self, on: bool) -> None:
        self.sounds.enabled = on
        self.settings.sound = on

    def _restore_window(self) -> None:
        geometry = self.settings.geometry
        if geometry is None or not self.restoreGeometry(geometry):
            screen = QApplication.primaryScreen().availableGeometry()
            w, h = min(900, int(screen.width() * 0.75)), min(820, int(screen.height() * 0.88))
            self.resize(w, h)
            self.move(screen.center().x() - w // 2, screen.center().y() - h // 2)
        self._first_show = True

    def showEvent(self, event) -> None:
        super().showEvent(event)
        if self._first_show:
            self._first_show = False
            if self.settings.maximized:
                self.set_maximized(True)
            QTimer.singleShot(0, self.view.fit)
            QTimer.singleShot(0, self.toggle_running)   # an aquarium: it is already alive when it opens

    def closeEvent(self, event) -> None:
        self._timer.stop()
        self.settings.maximized = self.maximized
        if self.maximized:
            self.set_maximized(False)
        self.settings.geometry = self.saveGeometry()
        super().closeEvent(event)
