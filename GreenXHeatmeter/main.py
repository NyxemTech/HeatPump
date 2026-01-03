#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import sqlite3
from datetime import datetime, timezone, timedelta

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QGridLayout, QHBoxLayout,
    QVBoxLayout, QFrame, QSizePolicy, QSpacerItem, QButtonGroup,
    QComboBox, QDateEdit
)
from PyQt5.QtCore import Qt, QTimer, QDate
from PyQt5.QtGui import QFont, QPixmap

# matplotlib for real charts
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure
import matplotlib.dates as mdates

# --------- import backend ---------
from core_logic import (
    STORE, DEVICE_ID, ROMANIA_TZ, DB_PATH,
    TABLE_DAY, TABLE_MONTH, TABLE_YEAR, TABLE_TOTAL, TABLE_SAMPLES,
    start_system,
)

# --------- paths for images ---------
BASE_DIR = os.path.dirname(os.path.abspath(__file__))

ICON_STANDBY   = os.path.join(BASE_DIR, "Standby.png")
ICON_HEATING   = os.path.join(BASE_DIR, "Heating.png")
ICON_COOLING   = os.path.join(BASE_DIR, "Cooling.png")
ICON_DEFROST   = os.path.join(BASE_DIR, "Defrost.png")
ICON_ELECTRIC  = os.path.join(BASE_DIR, "Electricity.png")
LOGO_PATH      = os.path.join(BASE_DIR, "GreenX logo HeatPump - white BIG.png")


def load_icon(path, size=24):
    lbl = QLabel()
    if os.path.exists(path):
        pm = QPixmap(path)
        if not pm.isNull():
            lbl.setPixmap(pm.scaled(size, size, Qt.KeepAspectRatio, Qt.SmoothTransformation))
    lbl.setFixedSize(size + 4, size + 4)
    lbl.setAlignment(Qt.AlignCenter)
    return lbl


def round2(v):
    try:
        if v is None:
            return None
        return round(float(v), 2)
    except Exception:
        return None


# =========================================================
#  DASHBOARD
# =========================================================
class Dashboard(QWidget):
    def __init__(self):
        super().__init__()

        # start backend threads
        self.bus_reader, self.heat_reader, self.db_writer = start_system()

        # DB connection (read-only usage in UI)
        self.db = sqlite3.connect(DB_PATH, check_same_thread=False)
        self.db.row_factory = sqlite3.Row

        # cached availability info for calendar
        self.available_dates = set()             # set of "YYYY-MM-DD"
        self.available_months_by_year = {}       # year -> set(month_int)
        self.available_years = []                # [year_int]

        # window
        self.setWindowFlag(Qt.FramelessWindowHint, True)
        self.setMinimumSize(1024, 600)
        self.showFullScreen()

        self.setStyleSheet("""
            QWidget { background-color:#000; color:#fff; }
            QLabel  { color:#fff; }
            QPushButton {
                background:#222; color:#fff; border:1px solid #555;
                border-radius:6px; padding:4px 10px;
            }
            QPushButton:checked {
                background:#1db954; color:#000; border-color:#0f7a39;
            }
            QPushButton:hover {
                background:#333;
            }
            QFrame.card {
                border:1px solid #333; border-radius:10px;
                background-color:#111;
            }
            QFrame#sepLine {
                background-color:#333;
            }
        """)

        self.small_font = QFont("Arial", 9)
        self.normal_font = QFont("Arial", 11)
        self.bold_font = QFont("Arial", 11)
        self.bold_font.setBold(True)

        root = QHBoxLayout()
        root.setContentsMargins(8, 8, 8, 8)
        root.setSpacing(8)
        self.setLayout(root)

        # ---------- LEFT SIDE ----------
        left = QVBoxLayout()
        left.setSpacing(6)
        root.addLayout(left, 0)

        # LIVE card
        self.live_card = self._build_live_card()
        left.addWidget(self.live_card)

        # separator
        sep = QFrame()
        sep.setObjectName("sepLine")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(2)
        left.addWidget(sep)

        # Last, Day, Month (Year + Total eliminate)
        self.last_card, self.last_vals = self._build_last_card()
        left.addWidget(self.last_card)

        self.day_card, self.day_vals = self._build_daymonth_card("Day")
        left.addWidget(self.day_card)

        self.month_card, self.month_vals = self._build_daymonth_card("Month")
        left.addWidget(self.month_card)

        left.addStretch(1)

        # ---------- RIGHT SIDE ----------
        right = QVBoxLayout()
        right.setSpacing(6)
        root.addLayout(right, 1)

        # --- right top ---
        top_right = QHBoxLayout()
        top_right.setContentsMargins(0, 0, 0, 0)
        right.addLayout(top_right, 0)

        # left info
        info_layout = QVBoxLayout()
        info_layout.setSpacing(2)
        top_right.addLayout(info_layout, 1)

        self.lbl_datetime = QLabel("—")
        self.lbl_datetime.setFont(self.bold_font)
        info_layout.addWidget(self.lbl_datetime)

        self.lbl_location = QLabel("Osorhei, Romania")
        self.lbl_location.setFont(self.normal_font)
        info_layout.addWidget(self.lbl_location)

        self.lbl_ambient = QLabel("Ambient: — °C   Humidity: — %")
        self.lbl_ambient.setFont(self.small_font)
        info_layout.addWidget(self.lbl_ambient)

        info_layout.addStretch(1)

        # center logo
        logo_layout = QVBoxLayout()
        logo_layout.setAlignment(Qt.AlignCenter)
        top_right.addLayout(logo_layout, 1)

        self.logo_label = QLabel()
        if os.path.exists(LOGO_PATH):
            pm = QPixmap(LOGO_PATH)
            if not pm.isNull():
                self.logo_label.setPixmap(pm.scaledToHeight(96, Qt.SmoothTransformation))
        logo_layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)

        # right buttons - ALL IN ONE ROW (Settings, Statistics, X)
        btn_row = QHBoxLayout()
        btn_row.setAlignment(Qt.AlignRight | Qt.AlignTop)
        top_right.addLayout(btn_row, 1)

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setCheckable(True)
        self.btn_settings.setChecked(False)
        btn_row.addWidget(self.btn_settings, alignment=Qt.AlignRight)

        self.btn_statistics = QPushButton("Statistics")
        self.btn_statistics.setCheckable(True)
        self.btn_statistics.setChecked(True)
        btn_row.addWidget(self.btn_statistics, alignment=Qt.AlignRight)

        btn_close = QPushButton("X")
        btn_close.setStyleSheet("""
            QPushButton {
                background:#e53935; color:#fff; font-weight:bold;
                border:1px solid #8c1f1d; padding:2px 8px; border-radius:8px;
            }
            QPushButton:hover { background:#ef5350; }
            QPushButton:pressed { background:#c62828; }
        """)
        btn_close.clicked.connect(self.close)
        btn_row.addWidget(btn_close, alignment=Qt.AlignRight)
        btn_row.addStretch(1)

        # separator
        sep2 = QFrame()
        sep2.setObjectName("sepLine")
        sep2.setFrameShape(QFrame.HLine)
        sep2.setFixedHeight(2)
        right.addWidget(sep2)

        # ---------- RIGHT BOTTOM ----------
        controls_and_chart = QVBoxLayout()
        controls_and_chart.setSpacing(4)
        right.addLayout(controls_and_chart, 1)

        # Period row
        period_row = QHBoxLayout()
        period_row.setSpacing(4)
        controls_and_chart.addLayout(period_row)

        lbl_period = QLabel("Period:")
        lbl_period.setFont(self.small_font)
        period_row.addWidget(lbl_period)

        self.btn_period_group = QButtonGroup(self)
        self.btn_period_day = QPushButton("Day")
        self.btn_period_month = QPushButton("Month")
        self.btn_period_year = QPushButton("Year")
        self.btn_period_total = QPushButton("Total")

        for i, btn in enumerate(
                [self.btn_period_day, self.btn_period_month, self.btn_period_year, self.btn_period_total]):
            btn.setCheckable(True)
            if i == 0:
                btn.setChecked(True)
            self.btn_period_group.addButton(btn)
            period_row.addWidget(btn)

        period_row.addStretch(1)

        # ---- calendar selectors (right side) ----
        # Day: QDateEdit
        self.day_date_edit = QDateEdit(self)
        self.day_date_edit.setCalendarPopup(True)
        self.day_date_edit.setDisplayFormat("dd-MM-yyyy")
        self.day_date_edit.setFont(self.small_font)
        period_row.addWidget(self.day_date_edit)

        # Month: month + year combos
        self.period_month_combo = QComboBox(self)
        self.period_month_combo.setFont(self.small_font)
        period_row.addWidget(self.period_month_combo)

        self.period_year_combo = QComboBox(self)
        self.period_year_combo.setFont(self.small_font)
        period_row.addWidget(self.period_year_combo)

        # Filter row
        filter_row = QHBoxLayout()
        filter_row.setSpacing(4)
        controls_and_chart.addLayout(filter_row)

        lbl_filter = QLabel("Filter:")
        lbl_filter.setFont(self.small_font)
        filter_row.addWidget(lbl_filter)

        self.btn_filter_group = QButtonGroup(self)
        self.btn_filter_cons = QPushButton("Consumption")
        self.btn_filter_prod = QPushButton("Production")
        self.btn_filter_cop = QPushButton("COP")
        self.btn_filter_time = QPushButton("Time")

        for i, btn in enumerate(
                [self.btn_filter_cons, self.btn_filter_prod,
                 self.btn_filter_cop, self.btn_filter_time]):
            btn.setCheckable(True)
            if i == 0:
                btn.setChecked(True)
            self.btn_filter_group.addButton(btn)
            filter_row.addWidget(btn)

        filter_row.addStretch(1)

        # Zoom row
        zoom_row = QHBoxLayout()
        zoom_row.setSpacing(4)
        controls_and_chart.addLayout(zoom_row)

        lbl_zoom = QLabel("Zoom:")
        lbl_zoom.setFont(self.small_font)
        zoom_row.addWidget(lbl_zoom)

        self.btn_zoom_group = QButtonGroup(self)
        self.btn_zoom_24h = QPushButton("24h")   # or 1x (for month/year/total)
        self.btn_zoom_12h = QPushButton("12h")   # or 2x
        self.btn_zoom_4h = QPushButton("4h")     # or 3x
        self.btn_zoom_1h = QPushButton("1h")
        self.btn_zoom_10m = QPushButton("10min")

        for btn in [self.btn_zoom_24h, self.btn_zoom_12h,
                    self.btn_zoom_4h, self.btn_zoom_1h, self.btn_zoom_10m]:
            btn.setCheckable(True)
            self.btn_zoom_group.addButton(btn)
            zoom_row.addWidget(btn)

        # default zoom for Day
        self.btn_zoom_10m.setChecked(True)

        zoom_row.addStretch(1)

        # chart area cu matplotlib
        self.chart_frame = QFrame()
        self.chart_frame.setFrameShape(QFrame.StyledPanel)
        self.chart_frame.setStyleSheet("QFrame { border:1px solid #333; border-radius:8px; background-color:#080808; }")
        chart_layout = QVBoxLayout(self.chart_frame)
        chart_layout.setContentsMargins(4, 4, 4, 4)
        controls_and_chart.addWidget(self.chart_frame, 1)

        self.figure = Figure(facecolor="#000000")
        self.canvas = FigureCanvas(self.figure)
        chart_layout.addWidget(self.canvas)
        self.ax = self.figure.add_subplot(111)
        self.ax.set_facecolor("#101010")

        # -------- load available dates/months/years from DB --------
        self._load_available_dates()
        self._init_calendar_defaults()

        # connect calendar changes
        self.day_date_edit.dateChanged.connect(self.update_chart)
        self.period_year_combo.currentIndexChanged.connect(self._on_year_changed)
        self.period_month_combo.currentIndexChanged.connect(self.update_chart)

        # connect buttons -> update chart + controls
        for btn in [self.btn_period_day, self.btn_period_month, self.btn_period_year, self.btn_period_total]:
            btn.clicked.connect(self._on_period_changed)

        for btn in [self.btn_filter_cons, self.btn_filter_prod,
                    self.btn_filter_cop, self.btn_filter_time]:
            btn.clicked.connect(self.update_chart)

        for btn in [self.btn_zoom_24h, self.btn_zoom_12h,
                    self.btn_zoom_4h, self.btn_zoom_1h, self.btn_zoom_10m]:
            btn.clicked.connect(self.update_chart)

        # set initial visibility for calendar + zoom modes
        self._update_period_controls()

        # Timer UI
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(1000)  # 1 sec
        self.ui_timer.timeout.connect(self.refresh_ui)
        self.ui_timer.start()

    # =====================================================
    #  DB-based calendar setup
    # =====================================================
    def _load_available_dates(self):
        """Read distinct dates/months/years from hp_samples to drive calendar widgets."""
        try:
            cur = self.db.cursor()
            # distinct local dates
            cur.execute(f"""
                SELECT DISTINCT date(ts_utc_s, 'unixepoch','localtime') AS d
                FROM {TABLE_SAMPLES}
                ORDER BY d;
            """)
            rows = cur.fetchall()
            for r in rows:
                d = r["d"]
                if d:
                    self.available_dates.add(d)

            # distinct year+month
            cur.execute(f"""
                SELECT DISTINCT
                    CAST(strftime('%Y', ts_utc_s, 'unixepoch','localtime') AS INTEGER) AS y,
                    CAST(strftime('%m', ts_utc_s, 'unixepoch','localtime') AS INTEGER) AS m
                FROM {TABLE_SAMPLES}
                ORDER BY y, m;
            """)
            rows2 = cur.fetchall()
            year_set = set()
            for r in rows2:
                y = r["y"]
                m = r["m"]
                if y is None or m is None:
                    continue
                year_set.add(y)
                self.available_months_by_year.setdefault(y, set()).add(m)

            self.available_years = sorted(list(year_set))
        except Exception:
            # if something goes wrong, we just fall back to current date
            self.available_dates = set()
            self.available_months_by_year = {}
            self.available_years = []

    def _init_calendar_defaults(self):
        # Day date default = last available day or today
        if self.available_dates:
            last_date_str = sorted(self.available_dates)[-1]
            d = QDate.fromString(last_date_str, "yyyy-MM-dd")
        else:
            d = QDate.currentDate()
        if d.isValid():
            self.day_date_edit.setDate(d)
        else:
            self.day_date_edit.setDate(QDate.currentDate())

        # Year combo
        self.period_year_combo.clear()
        if self.available_years:
            for y in self.available_years:
                self.period_year_combo.addItem(str(y), y)
        else:
            # fallback: current year
            y = datetime.now(ROMANIA_TZ).year
            self.period_year_combo.addItem(str(y), y)
            self.available_years = [y]
            self.available_months_by_year.setdefault(y, set(range(1, 13)))

        # Month combo for selected year
        self._populate_month_combo_for_current_year()

    def _populate_month_combo_for_current_year(self):
        if self.period_year_combo.count() == 0:
            return
        current_year = self.period_year_combo.currentData()
        if current_year is None:
            current_year = self.available_years[0]

        months = sorted(list(self.available_months_by_year.get(current_year, set())))
        if not months:
            months = list(range(1, 13))  # fallback

        self.period_month_combo.clear()
        for m in months:
            label = datetime(current_year, m, 1).strftime("%b")
            self.period_month_combo.addItem(f"{label}", m)

    def _on_year_changed(self, idx):
        # only matters for Month/Year periods, but safe always
        self._populate_month_combo_for_current_year()
        self.update_chart()

    # =====================================================
    #  BUILD CARDS
    # =====================================================
    def _build_live_card(self):
        frame = QFrame()
        frame.setProperty("class", "card")

        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 6, 8, 6)
        layout.setSpacing(4)

        # status text, fara icon
        row_status = QHBoxLayout()
        self.live_status_label = QLabel("Status: —")
        self.live_status_label.setFont(self.bold_font)
        row_status.addWidget(self.live_status_label, 1, Qt.AlignLeft | Qt.AlignVCenter)
        layout.addLayout(row_status)

        # produced: icon H/C/D/S + value + kW
        row_prod = QHBoxLayout()
        self.live_mode_icon = load_icon(ICON_STANDBY, size=24)
        row_prod.addWidget(self.live_mode_icon, 0, Qt.AlignLeft)
        self.live_produced = QLabel("—")
        self.live_produced.setFont(self.bold_font)
        row_prod.addWidget(self.live_produced, 1, Qt.AlignRight)
        self.live_prod_unit = QLabel("kW")
        self.live_prod_unit.setFont(self.small_font)
        row_prod.addWidget(self.live_prod_unit, 0, Qt.AlignLeft)
        layout.addLayout(row_prod)

        # consumed: icon electric + value + kW
        row_cons = QHBoxLayout()
        self.live_e_icon = load_icon(ICON_ELECTRIC, size=20)
        row_cons.addWidget(self.live_e_icon, 0, Qt.AlignLeft)
        self.live_consumed = QLabel("—")
        self.live_consumed.setFont(self.bold_font)
        row_cons.addWidget(self.live_consumed, 1, Qt.AlignRight)
        lbl_unit_c = QLabel("kW")
        lbl_unit_c.setFont(self.small_font)
        row_cons.addWidget(lbl_unit_c, 0, Qt.AlignLeft)
        layout.addLayout(row_cons)

        # COP
        row_cop = QHBoxLayout()
        row_cop.addWidget(QLabel("COP:"), 0, Qt.AlignLeft)
        self.live_cop = QLabel("—")
        self.live_cop.setFont(self.bold_font)
        row_cop.addWidget(self.live_cop, 1, Qt.AlignRight)
        layout.addLayout(row_cop)

        return frame

    def _build_last_card(self):
        frame = QFrame()
        frame.setProperty("class", "card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        title_lbl = QLabel("Last")
        title_lbl.setFont(self.bold_font)
        layout.addWidget(title_lbl, 0, Qt.AlignLeft)

        # Produced: icon H or C + value + kWh
        row_p = QHBoxLayout()
        self.last_prod_icon = load_icon(ICON_HEATING, size=22)
        row_p.addWidget(self.last_prod_icon, 0, Qt.AlignLeft)
        val_prod = QLabel("—")
        val_prod.setFont(self.bold_font)
        row_p.addWidget(val_prod, 1, Qt.AlignRight)
        lbl_unit = QLabel("kWh")
        lbl_unit.setFont(self.small_font)
        row_p.addWidget(lbl_unit, 0, Qt.AlignLeft)
        layout.addLayout(row_p)

        # Consumed: icon electric + value + kWh
        row_c = QHBoxLayout()
        self.last_cons_icon = load_icon(ICON_ELECTRIC, size=20)
        row_c.addWidget(self.last_cons_icon, 0, Qt.AlignLeft)
        val_cons = QLabel("—")
        val_cons.setFont(self.bold_font)
        row_c.addWidget(val_cons, 1, Qt.AlignRight)
        lbl_unit_c = QLabel("kWh")
        lbl_unit_c.setFont(self.small_font)
        row_c.addWidget(lbl_unit_c, 0, Qt.AlignLeft)
        layout.addLayout(row_c)

        # COPwork
        row_copw = QHBoxLayout()
        row_copw.addWidget(QLabel("COPwork:"), 0, Qt.AlignLeft)
        val_copw = QLabel("—")
        val_copw.setFont(self.bold_font)
        row_copw.addWidget(val_copw, 1, Qt.AlignRight)
        layout.addLayout(row_copw)

        vals = {
            "prod_value": val_prod,
            "cons_value": val_cons,
            "cop_work":   val_copw,
        }
        return frame, vals

    def _build_daymonth_card(self, title):
        frame = QFrame()
        frame.setProperty("class", "card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(self.bold_font)
        layout.addWidget(title_lbl, 0, Qt.AlignLeft)

        # row H
        row_h = QHBoxLayout()
        icon_h = load_icon(ICON_HEATING, size=20)
        row_h.addWidget(icon_h, 0, Qt.AlignLeft)
        val_h = QLabel("—")
        val_h.setFont(self.bold_font)
        row_h.addWidget(val_h, 1, Qt.AlignRight)
        unit_h = QLabel("kWh")
        unit_h.setFont(self.small_font)
        row_h.addWidget(unit_h, 0, Qt.AlignLeft)
        layout.addLayout(row_h)

        # row C
        row_c = QHBoxLayout()
        icon_c = load_icon(ICON_COOLING, size=20)
        row_c.addWidget(icon_c, 0, Qt.AlignLeft)
        val_c = QLabel("—")
        val_c.setFont(self.bold_font)
        row_c.addWidget(val_c, 1, Qt.AlignRight)
        unit_c = QLabel("kWh")
        unit_c.setFont(self.small_font)
        row_c.addWidget(unit_c, 0, Qt.AlignLeft)
        layout.addLayout(row_c)

        # row consumption (electric)
        row_cons = QHBoxLayout()
        icon_e = load_icon(ICON_ELECTRIC, size=20)
        row_cons.addWidget(icon_e, 0, Qt.AlignLeft)
        val_cons = QLabel("—")
        val_cons.setFont(self.bold_font)
        row_cons.addWidget(val_cons, 1, Qt.AlignRight)
        unit_cons = QLabel("kWh")
        unit_cons.setFont(self.small_font)
        row_cons.addWidget(unit_cons, 0, Qt.AlignLeft)
        layout.addLayout(row_cons)

        # COPwork
        row_copw = QHBoxLayout()
        row_copw.addWidget(QLabel("COPwork:"), 0, Qt.AlignLeft)
        val_copw = QLabel("—")
        val_copw.setFont(self.bold_font)
        row_copw.addWidget(val_copw, 1, Qt.AlignRight)
        layout.addLayout(row_copw)

        # COPtotal
        row_copt = QHBoxLayout()
        row_copt.addWidget(QLabel("COPtotal:"), 0, Qt.AlignLeft)
        val_copt = QLabel("—")
        val_copt.setFont(self.bold_font)
        row_copt.addWidget(val_copt, 1, Qt.AlignRight)
        layout.addLayout(row_copt)

        vals = {
            "icon_h": icon_h,
            "val_h": val_h,
            "unit_h": unit_h,
            "icon_c": icon_c,
            "val_c": val_c,
            "unit_c": unit_c,
            "val_cons": val_cons,
            "val_copw": val_copw,
            "val_copt": val_copt,
        }
        return frame, vals

    # =====================================================
    #  UPDATE UI
    # =====================================================
    def refresh_ui(self):
        snap = STORE.snapshot()

        # header: date/time + ambient
        ts_utc_s = snap.get("last_ts_utc_s")
        if ts_utc_s:
            dt_utc = datetime.fromtimestamp(int(ts_utc_s), tz=timezone.utc)
            dt_ro = dt_utc.astimezone(ROMANIA_TZ)
        else:
            dt_ro = datetime.now(ROMANIA_TZ)
        # Format: DAY-Month Year HH:MM (no seconds)
        self.lbl_datetime.setText(dt_ro.strftime("%d %b %Y %H:%M"))

        amb = snap.get("ts_ambient_temp")
        hum = snap.get("ts_ambient_humidity")
        amb_txt = "—" if amb is None else f"{amb:.1f}"
        hum_txt = "—" if hum is None else f"{hum:.1f}"
        self.lbl_ambient.setText(f"Ambient: {amb_txt} °C   Humidity: {hum_txt} %")

        self.update_live_card(snap)

        try:
            self.update_last_card()
            self.update_daymonth_card("day", self.day_vals)
            self.update_daymonth_card("month", self.month_vals)
            self.update_chart()
        except Exception:
            # nu vrem să crape UI dacă DB e ocupată
            pass

    def update_live_card(self, snap):
        status = snap.get("status")
        status_text = {
            "S": "Standby",
            "H": "Heating",
            "C": "Cooling",
            "D": "Defrost",
            "ON": "ON",
            "OFF": "OFF",
        }.get(status, "Unknown")
        self.live_status_label.setText(f"Status: {status_text}")

        # icon H/C/D/S pe linia de "produced"
        mode_icon_path = ICON_STANDBY
        if status == "H":
            mode_icon_path = ICON_HEATING
        elif status == "C":
            mode_icon_path = ICON_COOLING
        elif status == "D":
            mode_icon_path = ICON_DEFROST
        if os.path.exists(mode_icon_path):
            pm = QPixmap(mode_icon_path)
            if not pm.isNull():
                self.live_mode_icon.setPixmap(pm.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        hm_power = snap.get("hm_activepower")
        if status in ("H", "C", "D", "S") and hm_power is not None:
            self.live_produced.setText(f"{hm_power:.2f}")
        else:
            self.live_produced.setText("—")

        em_p = snap.get("em_activepower")
        if em_p is not None:
            em_kw = em_p / 1000.0
            self.live_consumed.setText(f"{em_kw:.2f}")
        else:
            self.live_consumed.setText("—")

        if status in ("H", "C") and hm_power is not None and em_p and em_p > 50:
            em_kw = em_p / 1000.0
            cop = hm_power / em_kw if em_kw > 0 else None
            if cop is not None:
                self.live_cop.setText(f"{cop:.2f}")
            else:
                self.live_cop.setText("—")
        else:
            self.live_cop.setText("—")

    # ----------------- LAST card -----------------
    def update_last_card(self):
        cur = self.db.cursor()
        cur.execute(f"""
            SELECT status, consumption_kw, positive_kw, negative_kw
            FROM {TABLE_DAY}
            WHERE status IN ('H','C')
            ORDER BY end_ts_utc_s DESC
            LIMIT 1;
        """)
        row = cur.fetchone()
        if not row:
            self.last_vals["prod_value"].setText("—")
            self.last_vals["cons_value"].setText("—")
            self.last_vals["cop_work"].setText("—")
            return

        status = row["status"]
        cons = row["consumption_kw"] or 0.0
        pos = row["positive_kw"] or 0.0
        neg = row["negative_kw"] or 0.0

        if status == "H":
            produced = pos
            icon_path = ICON_HEATING
        else:
            produced = abs(neg)
            icon_path = ICON_COOLING

        if os.path.exists(icon_path):
            pm = QPixmap(icon_path)
            if not pm.isNull():
                self.last_prod_icon.setPixmap(pm.scaled(22, 22, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        cop_work = produced / cons if cons and cons > 0 else None

        self.last_vals["prod_value"].setText(f"{round2(produced):.2f}")
        self.last_vals["cons_value"].setText(f"{round2(cons):.2f}")
        self.last_vals["cop_work"].setText(f"{cop_work:.2f}" if cop_work is not None else "—")

    # ----------------- DAY & MONTH cards -----------------
    def update_daymonth_card(self, level, vals_dict):
        """
        level = "day" sau "month"
        Folosește month_summary și year_summary:
          - Day: din TABLE_MONTH pentru ziua curentă
          - Month: din TABLE_YEAR pentru luna curentă
        """
        now_ro = datetime.now(ROMANIA_TZ)
        y = now_ro.year
        m = now_ro.month
        d = now_ro.day

        cur = self.db.cursor()

        if level == "day":
            cur.execute(f"""
                SELECT day, status,
                       SUM(total_time_s)     AS t_sum,
                       SUM(consumption_kw)   AS cons,
                       SUM(positive_kw)      AS pos,
                       SUM(negative_kw)      AS neg
                FROM {TABLE_MONTH}
                WHERE year=? AND month=? AND day=?
                GROUP BY day, status;
            """, (y, m, d))
        elif level == "month":
            cur.execute(f"""
                SELECT month AS day, status,
                       SUM(total_time_s)     AS t_sum,
                       SUM(consumption_kw)   AS cons,
                       SUM(positive_kw)      AS pos,
                       SUM(negative_kw)      AS neg
                FROM {TABLE_YEAR}
                WHERE year=? AND month=?
                GROUP BY month, status;
            """, (y, m))
        else:
            return

        rows = cur.fetchall()
        if not rows:
            vals_dict["val_h"].setText("—")
            vals_dict["val_c"].setText("—")
            vals_dict["val_cons"].setText("—")
            vals_dict["val_copw"].setText("—")
            vals_dict["val_copt"].setText("—")
            # hide icons + units + values if nothing
            vals_dict["icon_h"].setVisible(False)
            vals_dict["unit_h"].setVisible(False)
            vals_dict["val_h"].setVisible(False)

            vals_dict["icon_c"].setVisible(False)
            vals_dict["unit_c"].setVisible(False)
            vals_dict["val_c"].setVisible(False)
            return

        prod_H = 0.0
        prod_C = 0.0
        cons_total = 0.0
        cons_HC = 0.0

        for r in rows:
            st = r["status"]
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            cons_total += cons
            if st == "H":
                prod_H += pos
                cons_HC += cons
            elif st == "C":
                prod_C += abs(neg)
                cons_HC += cons

        production_total = prod_H + prod_C
        cop_work = production_total / cons_HC if cons_HC and cons_HC > 0 else None
        cop_total = production_total / cons_total if cons_total and cons_total > 0 else None

        # H row – show only if > 0
        if prod_H > 0:
            vals_dict["icon_h"].setVisible(True)
            vals_dict["unit_h"].setVisible(True)
            vals_dict["val_h"].setVisible(True)
            vals_dict["val_h"].setText(f"{prod_H:.2f}")
        else:
            vals_dict["icon_h"].setVisible(False)
            vals_dict["unit_h"].setVisible(False)
            vals_dict["val_h"].setVisible(False)
            vals_dict["val_h"].setText("—")

        # C row – show only if > 0
        if prod_C > 0:
            vals_dict["icon_c"].setVisible(True)
            vals_dict["unit_c"].setVisible(True)
            vals_dict["val_c"].setVisible(True)
            vals_dict["val_c"].setText(f"{prod_C:.2f}")
        else:
            vals_dict["icon_c"].setVisible(False)
            vals_dict["unit_c"].setVisible(False)
            vals_dict["val_c"].setVisible(False)
            vals_dict["val_c"].setText("—")

        vals_dict["val_cons"].setText(f"{cons_total:.2f}" if cons_total else "—")
        vals_dict["val_copw"].setText(f"{cop_work:.2f}" if cop_work is not None else "—")
        vals_dict["val_copt"].setText(f"{cop_total:.2f}" if cop_total is not None else "—")

    # =====================================================
    #  PERIOD / FILTER / ZOOM helpers
    # =====================================================
    def get_current_period(self):
        if self.btn_period_day.isChecked():
            return "day"
        if self.btn_period_month.isChecked():
            return "month"
        if self.btn_period_year.isChecked():
            return "year"
        if self.btn_period_total.isChecked():
            return "total"
        return "day"

    def get_current_filter(self):
        if self.btn_filter_cons.isChecked():
            return "consumption"
        if self.btn_filter_prod.isChecked():
            return "production"
        if self.btn_filter_cop.isChecked():
            return "cop"
        if self.btn_filter_time.isChecked():
            return "time"
        return "consumption"

    def get_zoom_seconds(self):
        """Used only for Day period."""
        if self.btn_zoom_24h.isChecked():
            return 24 * 3600
        if self.btn_zoom_12h.isChecked():
            return 12 * 3600
        if self.btn_zoom_4h.isChecked():
            return 4 * 3600
        if self.btn_zoom_1h.isChecked():
            return 1 * 3600
        if self.btn_zoom_10m.isChecked():
            return 10 * 60
        return 10 * 60

    def get_bar_width_scale(self):
        """For month/year/total: 1x / 2x / 3x as visual bar width."""
        if self.btn_zoom_24h.isChecked():
            return 0.6  # 1x
        if self.btn_zoom_12h.isChecked():
            return 0.9  # 2x
        if self.btn_zoom_4h.isChecked():
            return 1.2  # 3x
        # default
        return 0.6

    def _on_period_changed(self):
        self._update_period_controls()
        self.update_chart()

    def _update_period_controls(self):
        """Show/hide calendar widgets + adjust zoom labels depending on period."""
        period = self.get_current_period()

        # calendar widgets
        if period == "day":
            self.day_date_edit.setVisible(True)
            self.period_month_combo.setVisible(False)
            self.period_year_combo.setVisible(False)
        elif period == "month":
            self.day_date_edit.setVisible(False)
            self.period_month_combo.setVisible(True)
            self.period_year_combo.setVisible(True)
        elif period == "year":
            self.day_date_edit.setVisible(False)
            self.period_month_combo.setVisible(False)
            self.period_year_combo.setVisible(True)
        else:  # total
            self.day_date_edit.setVisible(False)
            self.period_month_combo.setVisible(False)
            self.period_year_combo.setVisible(False)

        # zoom buttons behavior
        if period == "day":
            # text for time zoom
            self.btn_zoom_24h.setText("24h")
            self.btn_zoom_12h.setText("12h")
            self.btn_zoom_4h.setText("4h")
            self.btn_zoom_1h.setText("1h")
            self.btn_zoom_10m.setText("10min")

            # show all time zoom buttons
            self.btn_zoom_24h.setVisible(True)
            self.btn_zoom_12h.setVisible(True)
            self.btn_zoom_4h.setVisible(True)
            self.btn_zoom_1h.setVisible(True)
            self.btn_zoom_10m.setVisible(True)

            # ensure some reasonable default
            if not any(btn.isChecked() for btn in
                       [self.btn_zoom_24h, self.btn_zoom_12h, self.btn_zoom_4h, self.btn_zoom_1h, self.btn_zoom_10m]):
                self.btn_zoom_10m.setChecked(True)
        else:
            # Zoom as 1x / 2x / 3x for bar width
            self.btn_zoom_24h.setText("1x")
            self.btn_zoom_12h.setText("2x")
            self.btn_zoom_4h.setText("3x")

            self.btn_zoom_24h.setVisible(True)
            self.btn_zoom_12h.setVisible(True)
            self.btn_zoom_4h.setVisible(True)

            # hide 1h and 10m in aggregated periods
            self.btn_zoom_1h.setVisible(False)
            self.btn_zoom_10m.setVisible(False)

            # default check 1x if none
            if not any(btn.isChecked() for btn in
                       [self.btn_zoom_24h, self.btn_zoom_12h, self.btn_zoom_4h]):
                self.btn_zoom_24h.setChecked(True)

    # =====================================================
    #  CHARTS
    # =====================================================
    def update_chart(self):
        period = self.get_current_period()
        filt = self.get_current_filter()

        self.ax.clear()
        self.ax.set_facecolor("#101010")

        if period == "day":
            self._plot_day_chart(filt)
        elif period == "month":
            self._plot_month_chart(filt)
        elif period == "year":
            self._plot_year_chart(filt)
        elif period == "total":
            self._plot_total_chart(filt)

        self.ax.grid(True, color="#333333", linestyle=":", linewidth=0.5)
        self.ax.tick_params(colors="#ffffff")
        for spine in self.ax.spines.values():
            spine.set_color("#777777")

        self.figure.tight_layout()
        self.canvas.draw_idle()

    # ---------- DAY chart (hp_samples) ----------
    def _plot_day_chart(self, filt):
        # Day selected from calendar (local time)
        qd = self.day_date_edit.date()
        if not qd.isValid():
            self.ax.text(0.5, 0.5, "Invalid date", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        day_local = qd.toPyDate()
        day_str = day_local.strftime("%Y-%m-%d")

        # if date not present in DB, just show "No data"
        if self.available_dates and day_str not in self.available_dates:
            self.ax.text(0.5, 0.5, "No data for selected day", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        start_local = datetime(day_local.year, day_local.month, day_local.day, 0, 0, 0, tzinfo=ROMANIA_TZ)
        end_local = start_local + timedelta(days=1)
        start_ts_utc = int(start_local.astimezone(timezone.utc).timestamp())
        end_ts_utc = int(end_local.astimezone(timezone.utc).timestamp())

        cur = self.db.cursor()
        cur.execute(f"""
            SELECT ts_utc_s, status,
                   em_activepower, hm_activepower
            FROM {TABLE_SAMPLES}
            WHERE ts_utc_s >= ? AND ts_utc_s < ?
            ORDER BY ts_utc_s;
        """, (start_ts_utc, end_ts_utc))
        rows = cur.fetchall()
        if not rows:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        times = []
        statuses = []
        em_powers = []
        hm_powers = []

        for r in rows:
            ts = r["ts_utc_s"]
            dt_local = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ROMANIA_TZ)
            times.append(dt_local)
            statuses.append(r["status"])
            em_powers.append(r["em_activepower"])
            hm_powers.append(r["hm_activepower"])

        # apply Day zoom window relative to the last timestamp of that day
        zoom_s = self.get_zoom_seconds()
        if times:
            t_max = times[-1]
            t_min = t_max - timedelta(seconds=zoom_s)
        else:
            t_min = None

        times_zoom = []
        statuses_zoom = []
        em_zoom = []
        hm_zoom = []
        for t, st, ep, hp in zip(times, statuses, em_powers, hm_powers):
            if t_min is not None and t < t_min:
                continue
            times_zoom.append(t)
            statuses_zoom.append(st)
            em_zoom.append(ep)
            hm_zoom.append(hp)

        if not times_zoom:
            self.ax.text(0.5, 0.5, "No data in zoom window", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # colors by status
        color_map = {
            "S": "#FFD54F",   # yellow
            "ON": "#61D61E",  # green
            "H": "#FF9800",   # orange
            "D": "#4FC3F7",   # light blue
            "C": "#305CDE",   # blue
            "OFF": "#FFFFFF"  # white
        }
        colors = [color_map.get(st, "#AAAAAA") for st in statuses_zoom]

        y_vals = []
        ylabel = ""

        if filt == "consumption":
            # em_activepower in kW
            for ep in em_zoom:
                if ep is None:
                    y_vals.append(None)
                else:
                    y_vals.append(ep / 1000.0)
            ylabel = "Consumption (kW)"

        elif filt == "production":
            # hm_activepower in kW
            for hp in hm_zoom:
                if hp is None:
                    y_vals.append(None)
                else:
                    y_vals.append(hp)
            ylabel = "Production (kW)"

        elif filt == "cop":
            # COP = hm_activepower / (em_activepower/1000)
            for st, hp, ep in zip(statuses_zoom, hm_zoom, em_zoom):
                if hp is None or ep is None or ep <= 50:
                    y_vals.append(None)
                else:
                    em_kw = ep / 1000.0
                    if em_kw > 0:
                        y_vals.append(hp / em_kw)
                    else:
                        y_vals.append(None)
            ylabel = "COP (instant)"

        else:
            self.ax.text(0.5, 0.5, "For Day: use Consumption / Production / COP", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # filter out None
        x_plot = []
        y_plot = []
        c_plot = []
        for t, y, c in zip(times_zoom, y_vals, colors):
            if y is not None:
                x_plot.append(t)
                y_plot.append(y)
                c_plot.append(c)

        if not x_plot:
            self.ax.text(0.5, 0.5, "No valid data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # line + colored points
        self.ax.plot(x_plot, y_plot, color="#FFFFFF", linewidth=0.8)
        self.ax.scatter(x_plot, y_plot, c=c_plot, s=15)

        self.ax.set_ylabel(ylabel)
        self.ax.set_title(f"Day {day_str} - {filt.capitalize()}")

        # x-axis only time HH:MM:SS
        self.ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M:%S', tz=ROMANIA_TZ))
        self.ax.set_xlabel("Time (HH:MM:SS)")

    # ---------- MONTH / YEAR / TOTAL charts ----------
    def _plot_month_chart(self, filt):
        # selected year/month
        if self.period_year_combo.count() == 0 or self.period_month_combo.count() == 0:
            self.ax.text(0.5, 0.5, "No month selected", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return
        y = self.period_year_combo.currentData()
        m = self.period_month_combo.currentData()
        if y is None or m is None:
            self.ax.text(0.5, 0.5, "Invalid month selection", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        cur = self.db.cursor()
        cur.execute(f"""
            SELECT day, status,
                   SUM(total_time_s)   AS t_sum,
                   SUM(consumption_kw) AS cons,
                   SUM(positive_kw)    AS pos,
                   SUM(negative_kw)    AS neg
            FROM {TABLE_MONTH}
            WHERE year=? AND month=?
            GROUP BY day, status
            ORDER BY day;
        """, (y, m))
        rows = cur.fetchall()
        if not rows:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # per day per status
        day_data = {}
        for r in rows:
            d = r["day"]
            st = r["status"]
            if st not in ("S", "H", "C", "D"):
                continue
            t = r["t_sum"] or 0.0
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            day_data.setdefault(d, {
                "S": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "H": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "C": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "D": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
            })
            day_data[d][st]["time"] += t
            day_data[d][st]["cons"] += cons
            day_data[d][st]["pos"] += pos
            day_data[d][st]["neg"] += neg

        xs = sorted(day_data.keys())
        if not xs:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        width = self.get_bar_width_scale()

        # compute values for each status per day
        S_vals = []
        H_vals = []
        C_vals = []
        D_vals = []
        H_cop_vals = []
        C_cop_vals = []
        T_cop_vals = []

        for d in xs:
            info = day_data[d]
            S_cons = info["S"]["cons"]
            H_cons = info["H"]["cons"]
            C_cons = info["C"]["cons"]
            D_cons = info["D"]["cons"]
            H_pos = info["H"]["pos"]
            C_neg = info["C"]["neg"]
            # times hours
            S_time_h = (info["S"]["time"] or 0.0) / 3600.0
            H_time_h = (info["H"]["time"] or 0.0) / 3600.0
            C_time_h = (info["C"]["time"] or 0.0) / 3600.0
            D_time_h = (info["D"]["time"] or 0.0) / 3600.0

            S_vals.append(S_cons)
            H_vals.append(H_cons)
            C_vals.append(abs(C_neg))
            D_vals.append(D_cons)

            H_cop = H_pos / H_cons if H_cons and H_cons > 0 else None
            C_cop = abs(C_neg) / C_cons if C_cons and C_cons > 0 else None
            total_pos = H_pos + abs(C_neg)
            total_cons = S_cons + H_cons + C_cons + D_cons
            T_cop = total_pos / total_cons if total_cons and total_cons > 0 else None

            H_cop_vals.append(H_cop)
            C_cop_vals.append(C_cop)
            T_cop_vals.append(T_cop)

            # overwrite for time filter later
            S_vals[-1] = S_time_h
            H_vals[-1] = H_time_h
            C_vals[-1] = C_time_h
            D_vals[-1] = D_time_h

        # indexes and offset for 4 bars S,H,C,D
        import numpy as np
        idx = np.arange(len(xs))

        if filt == "consumption":
            # recompute consumption arrays (we overwrote with time above)
            S_vals = []
            H_vals = []
            C_vals = []
            D_vals = []
            for d in xs:
                info = day_data[d]
                S_vals.append(info["S"]["cons"])
                H_vals.append(info["H"]["cons"])
                C_vals.append(info["C"]["cons"])
                D_vals.append(info["D"]["cons"])
            self._plot_4status_bars(idx, xs, S_vals, H_vals, C_vals, D_vals,
                                    width, "Consumed (kWh)", y_label="Consumption (kWh)")
            self.ax.set_title(f"Month {m:02d}/{y} - Consumption")

        elif filt == "production":
            # H positive_kw, C negative_kw
            H_vals = []
            C_vals = []
            for d in xs:
                info = day_data[d]
                H_vals.append(info["H"]["pos"])
                C_vals.append(abs(info["C"]["neg"]))
            # only H & C bars
            self._plot_2status_bars(idx, xs, H_vals, C_vals,
                                    width, "Produced (kWh)")
            self.ax.set_title(f"Month {m:02d}/{y} - Production")

        elif filt == "cop":
            # 3 bars: H COP, C COP, TOTAL COP
            H_c = []
            C_c = []
            T_c = []
            for d in xs:
                info = day_data[d]
                S_cons = info["S"]["cons"]
                H_cons = info["H"]["cons"]
                C_cons = info["C"]["cons"]
                D_cons = info["D"]["cons"]
                H_pos = info["H"]["pos"]
                C_neg = info["C"]["neg"]
                H_cop = H_pos / H_cons if H_cons and H_cons > 0 else None
                C_cop = abs(C_neg) / C_cons if C_cons and C_cons > 0 else None
                total_pos = H_pos + abs(C_neg)
                total_cons = S_cons + H_cons + C_cons + D_cons
                T_cop = total_pos / total_cons if total_cons and total_cons > 0 else None
                H_c.append(H_cop)
                C_c.append(C_cop)
                T_c.append(T_cop)
            self._plot_3status_bars(idx, xs, H_c, C_c, T_c, width,
                                    "COP", y_label="COP")
            self.ax.set_title(f"Month {m:02d}/{y} - COP")

        elif filt == "time":
            # time in hours for S,H,C,D
            S_vals = []
            H_vals = []
            C_vals = []
            D_vals = []
            for d in xs:
                info = day_data[d]
                S_vals.append((info["S"]["time"] or 0.0) / 3600.0)
                H_vals.append((info["H"]["time"] or 0.0) / 3600.0)
                C_vals.append((info["C"]["time"] or 0.0) / 3600.0)
                D_vals.append((info["D"]["time"] or 0.0) / 3600.0)
            self._plot_4status_bars(idx, xs, S_vals, H_vals, C_vals, D_vals,
                                    width, "Time (hours)", y_label="Time (hours)")
            self.ax.set_title(f"Month {m:02d}/{y} - Time")
        else:
            self.ax.text(0.5, 0.5, "Use Consumption / Production / COP / Time", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        self.ax.set_xlabel("Day of month")

    def _plot_year_chart(self, filt):
        # selected year
        if self.period_year_combo.count == 0:
            self.ax.text(0.5, 0.5, "No year selected", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return
        y = self.period_year_combo.currentData()
        if y is None:
            self.ax.text(0.5, 0.5, "Invalid year selection", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        cur = self.db.cursor()
        cur.execute(f"""
            SELECT month, status,
                   SUM(total_time_s)   AS t_sum,
                   SUM(consumption_kw) AS cons,
                   SUM(positive_kw)    AS pos,
                   SUM(negative_kw)    AS neg
            FROM {TABLE_YEAR}
            WHERE year=?
            GROUP BY month, status
            ORDER BY month;
        """, (y,))
        rows = cur.fetchall()
        if not rows:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # per month per status
        month_data = {}
        for r in rows:
            m = r["month"]
            st = r["status"]
            if st not in ("S", "H", "C", "D"):
                continue
            t = r["t_sum"] or 0.0
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            month_data.setdefault(m, {
                "S": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "H": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "C": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "D": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
            })
            month_data[m][st]["time"] += t
            month_data[m][st]["cons"] += cons
            month_data[m][st]["pos"] += pos
            month_data[m][st]["neg"] += neg

        xs = sorted(month_data.keys())
        if not xs:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        width = self.get_bar_width_scale()
        import numpy as np
        idx = np.arange(len(xs))

        if filt == "consumption":
            S_vals = []
            H_vals = []
            C_vals = []
            D_vals = []
            for m in xs:
                info = month_data[m]
                S_vals.append(info["S"]["cons"])
                H_vals.append(info["H"]["cons"])
                C_vals.append(info["C"]["cons"])
                D_vals.append(info["D"]["cons"])
            self._plot_4status_bars(idx, xs, S_vals, H_vals, C_vals, D_vals,
                                    width, "Consumed (kWh)", y_label="Consumption (kWh)")
            self.ax.set_title(f"Year {y} - Consumption")
        elif filt == "production":
            H_vals = []
            C_vals = []
            for m in xs:
                info = month_data[m]
                H_vals.append(info["H"]["pos"])
                C_vals.append(abs(info["C"]["neg"]))
            self._plot_2status_bars(idx, xs, H_vals, C_vals, width,
                                    "Produced (kWh)")
            self.ax.set_title(f"Year {y} - Production")
        elif filt == "cop":
            H_c = []
            C_c = []
            T_c = []
            for m in xs:
                info = month_data[m]
                S_cons = info["S"]["cons"]
                H_cons = info["H"]["cons"]
                C_cons = info["C"]["cons"]
                D_cons = info["D"]["cons"]
                H_pos = info["H"]["pos"]
                C_neg = info["C"]["neg"]
                H_cop = H_pos / H_cons if H_cons and H_cons > 0 else None
                C_cop = abs(C_neg) / C_cons if C_cons and C_cons > 0 else None
                total_pos = H_pos + abs(C_neg)
                total_cons = S_cons + H_cons + C_cons + D_cons
                T_cop = total_pos / total_cons if total_cons and total_cons > 0 else None
                H_c.append(H_cop)
                C_c.append(C_cop)
                T_c.append(T_cop)
            self._plot_3status_bars(idx, xs, H_c, C_c, T_c, width,
                                    "COP", y_label="COP")
            self.ax.set_title(f"Year {y} - COP")
        elif filt == "time":
            S_vals = []
            H_vals = []
            C_vals = []
            D_vals = []
            for m in xs:
                info = month_data[m]
                S_vals.append((info["S"]["time"] or 0.0) / 3600.0)
                H_vals.append((info["H"]["time"] or 0.0) / 3600.0)
                C_vals.append((info["C"]["time"] or 0.0) / 3600.0)
                D_vals.append((info["D"]["time"] or 0.0) / 3600.0)
            self._plot_4status_bars(idx, xs, S_vals, H_vals, C_vals, D_vals,
                                    width, "Time (hours)", y_label="Time (hours)")
            self.ax.set_title(f"Year {y} - Time")
        else:
            self.ax.text(0.5, 0.5, "Use Consumption / Production / COP / Time", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        self.ax.set_xlabel("Month")

    def _plot_total_chart(self, filt):
        cur = self.db.cursor()
        cur.execute(f"""
            SELECT year, status,
                   SUM(total_time_s)   AS t_sum,
                   SUM(consumption_kw) AS cons,
                   SUM(positive_kw)    AS pos,
                   SUM(negative_kw)    AS neg
            FROM {TABLE_TOTAL}
            GROUP BY year, status
            ORDER BY year;
        """)
        rows = cur.fetchall()
        if not rows:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        year_data = {}
        for r in rows:
            y = r["year"]
            st = r["status"]
            if st not in ("S", "H", "C", "D"):
                continue
            t = r["t_sum"] or 0.0
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            year_data.setdefault(y, {
                "S": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "H": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "C": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
                "D": {"time": 0.0, "cons": 0.0, "pos": 0.0, "neg": 0.0},
            })
            year_data[y][st]["time"] += t
            year_data[y][st]["cons"] += cons
            year_data[y][st]["pos"] += pos
            year_data[y][st]["neg"] += neg

        xs = sorted(year_data.keys())
        if not xs:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        width = self.get_bar_width_scale()
        import numpy as np
        idx = np.arange(len(xs))

        if filt == "consumption":
            S_vals = []
            H_vals = []
            C_vals = []
            D_vals = []
            for y in xs:
                info = year_data[y]
                S_vals.append(info["S"]["cons"])
                H_vals.append(info["H"]["cons"])
                C_vals.append(info["C"]["cons"])
                D_vals.append(info["D"]["cons"])
            self._plot_4status_bars(idx, xs, S_vals, H_vals, C_vals, D_vals,
                                    width, "Consumed (kWh)", y_label="Consumption (kWh)")
            self.ax.set_title("Total - Consumption")
        elif filt == "production":
            H_vals = []
            C_vals = []
            for y in xs:
                info = year_data[y]
                H_vals.append(info["H"]["pos"])
                C_vals.append(abs(info["C"]["neg"]))
            self._plot_2status_bars(idx, xs, H_vals, C_vals, width,
                                    "Produced (kWh)")
            self.ax.set_title("Total - Production")
        elif filt == "cop":
            H_c = []
            C_c = []
            T_c = []
            for y in xs:
                info = year_data[y]
                S_cons = info["S"]["cons"]
                H_cons = info["H"]["cons"]
                C_cons = info["C"]["cons"]
                D_cons = info["D"]["cons"]
                H_pos = info["H"]["pos"]
                C_neg = info["C"]["neg"]
                H_cop = H_pos / H_cons if H_cons and H_cons > 0 else None
                C_cop = abs(C_neg) / C_cons if C_cons and C_cons > 0 else None
                total_pos = H_pos + abs(C_neg)
                total_cons = S_cons + H_cons + C_cons + D_cons
                T_cop = total_pos / total_cons if total_cons and total_cons > 0 else None
                H_c.append(H_cop)
                C_c.append(C_cop)
                T_c.append(T_cop)
            self._plot_3status_bars(idx, xs, H_c, C_c, T_c, width,
                                    "COP", y_label="COP")
            self.ax.set_title("Total - COP")
        elif filt == "time":
            S_vals = []
            H_vals = []
            C_vals = []
            D_vals = []
            for y in xs:
                info = year_data[y]
                S_vals.append((info["S"]["time"] or 0.0) / 3600.0)
                H_vals.append((info["H"]["time"] or 0.0) / 3600.0)
                C_vals.append((info["C"]["time"] or 0.0) / 3600.0)
                D_vals.append((info["D"]["time"] or 0.0) / 3600.0)
            self._plot_4status_bars(idx, xs, S_vals, H_vals, C_vals, D_vals,
                                    width, "Time (hours)", y_label="Time (hours)")
            self.ax.set_title("Total - Time")
        else:
            self.ax.text(0.5, 0.5, "Use Consumption / Production / COP / Time", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        self.ax.set_xlabel("Year")

    # ===== helpers for grouped bars =====
    def _plot_4status_bars(self, idx, labels, S_vals, H_vals, C_vals, D_vals,
                           width, title, y_label=""):
        import numpy as np
        # offset: S,H,C,D
        offset = width * 1.5
        self.ax.bar(idx - offset, S_vals, width, label="Standby", color="#FFD54F")
        self.ax.bar(idx - 0.5 * width, H_vals, width, label="Heating", color="#FF9800")
        self.ax.bar(idx + 0.5 * width, C_vals, width, label="Cooling", color="#305CDE")
        self.ax.bar(idx + offset, D_vals, width, label="Defrost", color="#4FC3F7")
        self.ax.set_xticks(idx)
        self.ax.set_xticklabels(labels)
        self.ax.set_ylabel(y_label)
        self.ax.legend()

    def _plot_2status_bars(self, idx, labels, H_vals, C_vals, width, y_label):
        import numpy as np
        offset = width / 2.0
        self.ax.bar(idx - offset, H_vals, width, label="Heating", color="#FF9800")
        self.ax.bar(idx + offset, C_vals, width, label="Cooling", color="#305CDE")
        self.ax.set_xticks(idx)
        self.ax.set_xticklabels(labels)
        self.ax.set_ylabel(y_label)
        self.ax.legend()

    def _plot_3status_bars(self, idx, labels, H_vals, C_vals, T_vals, width, title, y_label=""):
        import numpy as np
        offset = width
        self.ax.bar(idx - offset, H_vals, width, label="COP Heating", color="#FF9800")
        self.ax.bar(idx, C_vals, width, label="COP Cooling", color="#305CDE")
        self.ax.bar(idx + offset, T_vals, width, label="COP Total", color="#61D61E")
        self.ax.set_xticks(idx)
        self.ax.set_xticklabels(labels)
        self.ax.set_ylabel(y_label)
        self.ax.legend()

    # =====================================================
    #  CLOSE / ESC
    # =====================================================
    def keyPressEvent(self, e):
        if e.key() in (Qt.Key_Escape, Qt.Key_Q):
            self.close()

    def closeEvent(self, e):
        try:
            self.bus_reader.running = False
            self.bus_reader.join(timeout=1.5)
        except Exception:
            pass
        try:
            self.heat_reader.running = False
            self.heat_reader.join(timeout=1.5)
        except Exception:
            pass
        try:
            self.db_writer.running = False
            self.db_writer.join(timeout=1.5)
        except Exception:
            pass
        try:
            self.db.close()
        except Exception:
            pass
        e.accept()


# =========================================================
#  MAIN
# =========================================================
if __name__ == "__main__":
    app = QApplication(sys.argv)
    w = Dashboard()
    w.show()
    sys.exit(app.exec_())
