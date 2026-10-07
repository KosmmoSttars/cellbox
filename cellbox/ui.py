"""The main window: menu bar, toolbar, the field, status bar."""

import time
from collections import deque

from PyQt6.QtCore import QSize, Qt, QTimer
from PyQt6.QtGui import QAction, QActionGroup, QIcon, QKeySequence
from PyQt6.QtWidgets import (QApplication, QFrame, QHBoxLayout, QLabel, QMenu, QMenuBar, QSlider, QToolButton,
                             QVBoxLayout, QWidget)

from cellbox.canvas import FieldView
from cellbox.dialogs import AboutDialog, RuleDialog, SeedDialog
from cellbox.engine import SIZES, Field
from cellbox.icon import app_icon, icon_pixmap
from cellbox.palette import color_table
from cellbox.rules import PRESET_GROUPS, Rule, preset_name
from cellbox.settings import SPEED_MAX, Settings, new_seed
from cellbox.sound import SoundBank
from cellbox.win95 import Win95Frame, glyph

MAX_FRAME_BUDGET = 0.012   # seconds of stepping per frame at Max speed (the rest is for drawing)
FRAME_MS = 16
STATUS_EVERY = 0.1         # seconds between status bar refreshes


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
        self.settings = settings
        self.sounds = SoundBank(settings.sound, self)
        self.seeding = settings.seeding
        self.field = Field(settings.size, settings.rule)
        self.view = FieldView(self.field)
        self.view.view_changed.connect(self._update_status)

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

        self._apply_rule(self.field.rule, save=False)
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
        self.act_run = self._action("&Run", self.toggle_running, "Space")
        self.act_step = self._action("&Step", self.step_once, "N")
        self.act_reseed = self._action("&Reseed", self.reseed, "R")
        self.act_seed_options = self._action("Seed &Options...", self.seed_options)
        self.act_clear = self._action("&Clear", self.clear, "C")
        self.act_custom = self._action("&Custom...", self.custom_rule)
        self.act_zoom_in = self._action("Zoom &In", self.view.zoom_in, ["+", "="])
        self.act_zoom_out = self._action("Zoom &Out", self.view.zoom_out, ["-"])
        self.act_fit = self._action("&Fit to Window", self.view.fit, "F")
        self.act_sound = self._action("&Sounds", self._toggle_sound, checkable=True)
        self.act_sound.setChecked(self.sounds.enabled)
        self.act_exit = self._action("E&xit", self.close)
        self.act_about = self._action("&About Cellbox", lambda: AboutDialog(self).exec())

        self._rule_group = QActionGroup(self)
        self._rule_actions: dict[Rule, QAction] = {}
        for group in PRESET_GROUPS.values():
            for preset in group:
                action = QAction(f"{preset.name}\t{preset.rule}", self, checkable=True)
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
        file.addAction(self.act_exit)

        sim = bar.addMenu("&Simulation")
        for action in (self.act_run, self.act_step, None, self.act_reseed, self.act_seed_options,
                       self.act_clear):
            sim.addSeparator() if action is None else sim.addAction(action)

        self.rules_menu = bar.addMenu("&Rules")
        for title, group in PRESET_GROUPS.items():
            sub = self.rules_menu.addMenu(title)
            for preset in group:
                sub.addAction(self._rule_actions[preset.rule])
        self.rules_menu.addSeparator()
        self.rules_menu.addAction(self.act_custom)

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
            (self.btn_run, self._tool("step", "Step (N)", self.step_once)),
            (self._tool("seed", "Reseed (R)", self.reseed), self._tool("clear", "Clear (C)", self.clear)),
            (self._tool("rules", "Rules", menu=self.rules_menu),),
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
        self.st_population.setToolTip("Live cells")
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
        self.field.seed(self.seeding.density / 100, self.seeding.spot, self.seeding.seed)
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
        self.view.update()
        self._update_status()

    def set_size(self, size: int) -> None:
        if size == self.field.size:
            return
        self.field.resize(size)
        self.settings.size = size
        self.reseed()
        self.view.fit()

    # --- rules ------------------------------------------------------------------------------

    def _apply_rule(self, rule: Rule, save: bool = True) -> None:
        self.field.rule = rule
        self.view.set_color_table(color_table(rule))
        action = self._rule_actions.get(rule)
        if action is not None:
            action.setChecked(True)
        elif self._rule_group.checkedAction() is not None:
            self._rule_group.checkedAction().setChecked(False)
        name = preset_name(rule)
        self.set_title(f"Cellbox - {name or rule}")
        self.st_rule.setText(f"{name}  ({rule})" if name else f"Custom  ({rule})")
        if save:
            self.settings.rule = rule

    def custom_rule(self) -> None:
        dialog = RuleDialog(self, self.field.rule, self.sounds)
        if dialog.exec():
            self._apply_rule(dialog.rule)

    # --- status, sound, window --------------------------------------------------------------

    def _update_status(self) -> None:
        now = time.perf_counter()
        self._last_status = now
        while self._step_times and now - self._step_times[0] > 1.0:
            self._step_times.popleft()
        f = self.field
        self.st_generation.setText(f"Generation {f.generation:,}")
        self.st_population.setText(f"Population {f.population:,}")
        self.st_rate.setText(f"{len(self._step_times)} steps/s" if self.running else "Paused")
        self.st_view.setText(f"{f.size} x {f.size}, zoom {self.view.zoom}x")
        self.st_seed.setText(f"Seed {self.seeding.seed}")

    def _toggle_sound(self, on: bool) -> None:
        self.sounds.enabled = on
        self.settings.sound = on

    def _restore_window(self) -> None:
        geometry = self.settings.geometry
        if geometry is None or not self.restoreGeometry(geometry):
            screen = QApplication.primaryScreen().availableGeometry()
            w, h = min(860, int(screen.width() * 0.75)), min(820, int(screen.height() * 0.88))
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
