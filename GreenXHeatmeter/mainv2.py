#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import sys
import os
import sqlite3
from datetime import datetime, timezone

from PyQt5.QtWidgets import (
    QApplication, QWidget, QLabel, QPushButton, QGridLayout, QHBoxLayout,
    QVBoxLayout, QFrame, QSizePolicy, QSpacerItem, QButtonGroup
)
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap

# matplotlib for real charts
from matplotlib.backends.backend_qt5agg import FigureCanvasQTAgg as FigureCanvas
from matplotlib.figure import Figure

# --------- import backend ---------
from core_logic import (
    STORE, DEVICE_ID, ROMANIA_TZ, DB_PATH,
    TABLE_DAY, TABLE_MONTH, TABLE_YEAR, TABLE_TOTAL,
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
                # 50% mai mare ca înainte: ~72px înălțime era; îl mărim un pic
                self.logo_label.setPixmap(pm.scaledToHeight(96, Qt.SmoothTransformation))
        logo_layout.addWidget(self.logo_label, alignment=Qt.AlignCenter)

        # right buttons
        btn_layout = QVBoxLayout()
        btn_layout.setAlignment(Qt.AlignRight | Qt.AlignTop)
        top_right.addLayout(btn_layout, 1)

        self.btn_settings = QPushButton("Settings")
        self.btn_settings.setCheckable(True)
        self.btn_settings.setChecked(False)
        btn_layout.addWidget(self.btn_settings, alignment=Qt.AlignRight)

        self.btn_statistics = QPushButton("Statistics")
        self.btn_statistics.setCheckable(True)
        self.btn_statistics.setChecked(True)
        btn_layout.addWidget(self.btn_statistics, alignment=Qt.AlignRight)

        btn_layout.addSpacing(4)
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
        btn_layout.addWidget(btn_close, alignment=Qt.AlignRight)
        btn_layout.addStretch(1)

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
        self.btn_filter_copt = QPushButton("COPtotal")
        self.btn_filter_copw = QPushButton("COPwork")
        self.btn_filter_time = QPushButton("Time")

        for i, btn in enumerate(
                [self.btn_filter_cons, self.btn_filter_prod,
                 self.btn_filter_copt, self.btn_filter_copw, self.btn_filter_time]):
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
        self.btn_zoom_24h = QPushButton("24h")
        self.btn_zoom_12h = QPushButton("12h")
        self.btn_zoom_4h = QPushButton("4h")
        self.btn_zoom_1h = QPushButton("1h")
        self.btn_zoom_10m = QPushButton("10min")

        for i, btn in enumerate(
                [self.btn_zoom_24h, self.btn_zoom_12h,
                 self.btn_zoom_4h, self.btn_zoom_1h, self.btn_zoom_10m]):
            btn.setCheckable(True)
            if btn is self.btn_zoom_10m:
                btn.setChecked(True)  # implicit 10min
            self.btn_zoom_group.addButton(btn)
            zoom_row.addWidget(btn)

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

        # connect buttons -> update chart
        for btn in [self.btn_period_day, self.btn_period_month, self.btn_period_year, self.btn_period_total,
                    self.btn_filter_cons, self.btn_filter_prod, self.btn_filter_copt,
                    self.btn_filter_copw, self.btn_filter_time,
                    self.btn_zoom_24h, self.btn_zoom_12h, self.btn_zoom_4h,
                    self.btn_zoom_1h, self.btn_zoom_10m]:
            btn.clicked.connect(self.update_chart)

        # Timer UI
        self.ui_timer = QTimer(self)
        self.ui_timer.setInterval(1000)  # 1 sec
        self.ui_timer.timeout.connect(self.refresh_ui)
        self.ui_timer.start()

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
        self.lbl_datetime.setText(dt_ro.strftime("%Y-%m-%d %H:%M:%S"))

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
            # ascundem icon-urile H/C dacă n-avem nimic
            vals_dict["icon_h"].setVisible(False)
            vals_dict["unit_h"].setVisible(False)
            vals_dict["icon_c"].setVisible(False)
            vals_dict["unit_c"].setVisible(False)
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
            vals_dict["val_h"].setText(f"{prod_H:.2f}")
        else:
            vals_dict["icon_h"].setVisible(False)
            vals_dict["unit_h"].setVisible(False)
            vals_dict["val_h"].setText("—")

        # C row – show only if > 0
        if prod_C > 0:
            vals_dict["icon_c"].setVisible(True)
            vals_dict["unit_c"].setVisible(True)
            vals_dict["val_c"].setText(f"{prod_C:.2f}")
        else:
            vals_dict["icon_c"].setVisible(False)
            vals_dict["unit_c"].setVisible(False)
            vals_dict["val_c"].setText("—")

        vals_dict["val_cons"].setText(f"{cons_total:.2f}" if cons_total else "—")
        vals_dict["val_copw"].setText(f"{cop_work:.2f}" if cop_work is not None else "—")
        vals_dict["val_copt"].setText(f"{cop_total:.2f}" if cop_total is not None else "—")

    # =====================================================
    #  CHARTS
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
        if self.btn_filter_copt.isChecked():
            return "coptotal"
        if self.btn_filter_copw.isChecked():
            return "copwork"
        if self.btn_filter_time.isChecked():
            return "time"
        return "consumption"

    def get_zoom_seconds(self):
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
        zoom_s = self.get_zoom_seconds()
        now_utc = datetime.now(timezone.utc)
        start_ts = int(now_utc.timestamp()) - zoom_s

        cur = self.db.cursor()
        cur.execute(f"""
            SELECT ts_utc_s, status,
                   em_total_fwd, hm_positive_kwh, hm_negative_kwh,
                   hm_activepower, em_activepower
            FROM hp_samples
            WHERE ts_utc_s >= ?
            ORDER BY ts_utc_s;
        """, (start_ts,))
        rows = cur.fetchall()
        if not rows:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        times = []
        statuses = []
        em_total = []
        hm_pos = []
        hm_neg = []
        hm_pow = []
        em_pow = []

        for r in rows:
            ts = r["ts_utc_s"]
            dt_local = datetime.fromtimestamp(ts, tz=timezone.utc).astimezone(ROMANIA_TZ)
            times.append(dt_local)
            statuses.append(r["status"])
            em_total.append(r["em_total_fwd"])
            hm_pos.append(r["hm_positive_kwh"])
            hm_neg.append(r["hm_negative_kwh"])
            hm_pow.append(r["hm_activepower"])
            em_pow.append(r["em_activepower"])

        # colors by status
        color_map = {
            "S": "#FFD54F",   # yellow
            "ON": "#61D61E",  # green
            "H": "#FF9800",   # orange
            "D": "#4FC3F7",   # light blue
            "C": "#305CDE",   # blue
            "OFF": "#FFFFFF"  # white
        }
        colors = [color_map.get(st, "#AAAAAA") for st in statuses]

        y_vals = []

        if filt == "consumption":
            base_em = None
            for v in em_total:
                if v is not None:
                    base_em = v
                    break
            for v in em_total:
                if v is None or base_em is None:
                    y_vals.append(None)
                else:
                    y_vals.append(v - base_em)
            ylabel = "Consumed energy (kWh)"

        elif filt == "production":
            base_pos = None
            base_neg = None
            # base values
            for p, n in zip(hm_pos, hm_neg):
                if base_pos is None and p is not None:
                    base_pos = p
                if base_neg is None and n is not None:
                    base_neg = n
                if base_pos is not None and base_neg is not None:
                    break
            for p, n in zip(hm_pos, hm_neg):
                if p is None:
                    p = base_pos
                if n is None:
                    n = base_neg
                if base_pos is None or base_neg is None or p is None or n is None:
                    y_vals.append(None)
                else:
                    prod_H = max(p - base_pos, 0.0)
                    prod_C = abs(n - base_neg)
                    y_vals.append(prod_H + prod_C)
            ylabel = "Produced energy (kWh)"

        elif filt == "copwork":
            for st, hp, ep in zip(statuses, hm_pow, em_pow):
                if st not in ("H", "C") or hp is None or ep is None or ep <= 50:
                    y_vals.append(None)
                else:
                    em_kw = ep / 1000.0
                    if em_kw > 0:
                        y_vals.append(hp / em_kw)
                    else:
                        y_vals.append(None)
            ylabel = "COPwork (instant)"

        elif filt == "coptotal":
            # folosim COPtotal agregat pe 'day' ca linie orizontală
            prod, cons_tot, copw, copt = self._aggregate_period_generic("day")
            if copt is None:
                self.ax.text(0.5, 0.5, "No COPtotal data", color="white",
                             ha="center", va="center", transform=self.ax.transAxes)
                return
            self.ax.plot(times, [copt] * len(times), color="#61D61E", linewidth=2)
            self.ax.set_ylabel("COPtotal (day)")
            self.ax.set_title("Day - COPtotal")
            return

        else:  # "time" pentru Day nu are sens -> mesaj
            self.ax.text(0.5, 0.5, "Time filter applies from Month up", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # filtrăm None
        x_plot = []
        y_plot = []
        c_plot = []
        for t, y, c in zip(times, y_vals, colors):
            if y is not None:
                x_plot.append(t)
                y_plot.append(y)
                c_plot.append(c)

        if not x_plot:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        # linie albă + puncte colorate
        self.ax.plot(x_plot, y_plot, color="#FFFFFF", linewidth=0.8)
        self.ax.scatter(x_plot, y_plot, c=c_plot, s=15)

        self.ax.set_ylabel(ylabel)
        self.ax.set_title(f"Day - {filt.capitalize()}")

    # ------- generic aggregate for period (for COPtotal line etc.) -------
    def _aggregate_period_generic(self, level):
        """
        Return (produced_kwh, consumed_total_kwh, cop_work, cop_total)
        using summary tables; level in {"day","month","year","total"}
        """
        now_ro = datetime.now(ROMANIA_TZ)
        y = now_ro.year
        m = now_ro.month
        d = now_ro.day

        cur = self.db.cursor()

        if level == "day":
            cur.execute(f"""
                SELECT status,
                       SUM(consumption_kw) AS cons,
                       SUM(positive_kw)    AS pos,
                       SUM(negative_kw)    AS neg
                FROM {TABLE_MONTH}
                WHERE year=? AND month=? AND day=?
                GROUP BY status;
            """, (y, m, d))
        elif level == "month":
            cur.execute(f"""
                SELECT status,
                       SUM(consumption_kw) AS cons,
                       SUM(positive_kw)    AS pos,
                       SUM(negative_kw)    AS neg
                FROM {TABLE_YEAR}
                WHERE year=? AND month=?
                GROUP BY status;
            """, (y, m))
        elif level == "year":
            cur.execute(f"""
                SELECT status,
                       SUM(consumption_kw) AS cons,
                       SUM(positive_kw)    AS pos,
                       SUM(negative_kw)    AS neg
                FROM {TABLE_TOTAL}
                WHERE year=?
                GROUP BY status;
            """, (y,))
        elif level == "total":
            cur.execute(f"""
                SELECT status,
                       SUM(consumption_kw) AS cons,
                       SUM(positive_kw)    AS pos,
                       SUM(negative_kw)    AS neg
                FROM {TABLE_TOTAL}
                GROUP BY status;
            """)
        else:
            return None, None, None, None

        rows = cur.fetchall()
        if not rows:
            return None, None, None, None

        total_cons_all = 0.0
        cons_HC = 0.0
        prod_HC = 0.0

        for r in rows:
            st = r["status"]
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            total_cons_all += cons
            if st == "H":
                cons_HC += cons
                prod_HC += pos
            elif st == "C":
                cons_HC += cons
                prod_HC += abs(neg)

        produced = prod_HC
        consumed_total = total_cons_all
        cop_work = produced / cons_HC if cons_HC and cons_HC > 0 else None
        cop_total = produced / consumed_total if consumed_total and consumed_total > 0 else None

        return produced, consumed_total, cop_work, cop_total

    # ---------- MONTH / YEAR / TOTAL charts ----------
    def _plot_month_chart(self, filt):
        now_ro = datetime.now(ROMANIA_TZ)
        y = now_ro.year
        m = now_ro.month

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

        days = {}
        for r in rows:
            d = r["day"]
            st = r["status"]
            t = r["t_sum"] or 0.0
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            if d not in days:
                days[d] = {
                    "time": 0.0,
                    "cons_total": 0.0,
                    "prod_H": 0.0,
                    "prod_C": 0.0,
                    "cons_HC": 0.0,
                }
            days[d]["cons_total"] += cons
            if st != "ON":
                days[d]["time"] += t
            if st == "H":
                days[d]["prod_H"] += pos
                days[d]["cons_HC"] += cons
            elif st == "C":
                days[d]["prod_C"] += abs(neg)
                days[d]["cons_HC"] += cons

        xs = sorted(days.keys())
        ys = []

        for d in xs:
            info = days[d]
            prod_total = info["prod_H"] + info["prod_C"]
            cons_total = info["cons_total"]
            cons_HC = info["cons_HC"]
            if filt == "consumption":
                ys.append(cons_total)
                ylabel = "Consumed (kWh)"
            elif filt == "production":
                ys.append(prod_total)
                ylabel = "Produced (kWh)"
            elif filt == "copwork":
                val = prod_total / cons_HC if cons_HC and cons_HC > 0 else None
                ys.append(val)
                ylabel = "COPwork"
            elif filt == "coptotal":
                val = prod_total / cons_total if cons_total and cons_total > 0 else None
                ys.append(val)
                ylabel = "COPtotal"
            elif filt == "time":
                ys.append((info["time"] or 0.0) / 3600.0)  # ore
                ylabel = "Time (hours)"
            else:
                ys.append(cons_total)
                ylabel = "Consumed (kWh)"

        # filtrăm None
        xs_plot = []
        ys_plot = []
        for d, v in zip(xs, ys):
            if v is not None:
                xs_plot.append(d)
                ys_plot.append(v)

        if not xs_plot:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        self.ax.bar(xs_plot, ys_plot, color="#61D61E")
        self.ax.set_xlabel("Day of month")
        self.ax.set_ylabel(ylabel)
        self.ax.set_title(f"Month - {filt.capitalize()}")

    def _plot_year_chart(self, filt):
        now_ro = datetime.now(ROMANIA_TZ)
        y = now_ro.year

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

        months = {}
        for r in rows:
            m = r["month"]
            st = r["status"]
            t = r["t_sum"] or 0.0
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            if m not in months:
                months[m] = {
                    "time": 0.0,
                    "cons_total": 0.0,
                    "prod_H": 0.0,
                    "prod_C": 0.0,
                    "cons_HC": 0.0,
                }
            months[m]["cons_total"] += cons
            if st != "ON":
                months[m]["time"] += t
            if st == "H":
                months[m]["prod_H"] += pos
                months[m]["cons_HC"] += cons
            elif st == "C":
                months[m]["prod_C"] += abs(neg)
                months[m]["cons_HC"] += cons

        xs = sorted(months.keys())
        ys = []
        for m in xs:
            info = months[m]
            prod_total = info["prod_H"] + info["prod_C"]
            cons_total = info["cons_total"]
            cons_HC = info["cons_HC"]
            if filt == "consumption":
                ys.append(cons_total)
                ylabel = "Consumed (kWh)"
            elif filt == "production":
                ys.append(prod_total)
                ylabel = "Produced (kWh)"
            elif filt == "copwork":
                val = prod_total / cons_HC if cons_HC and cons_HC > 0 else None
                ys.append(val)
                ylabel = "COPwork"
            elif filt == "coptotal":
                val = prod_total / cons_total if cons_total and cons_total > 0 else None
                ys.append(val)
                ylabel = "COPtotal"
            elif filt == "time":
                ys.append((info["time"] or 0.0) / 3600.0)
                ylabel = "Time (hours)"
            else:
                ys.append(cons_total)
                ylabel = "Consumed (kWh)"

        xs_plot = []
        ys_plot = []
        for m, v in zip(xs, ys):
            if v is not None:
                xs_plot.append(m)
                ys_plot.append(v)

        if not xs_plot:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        self.ax.bar(xs_plot, ys_plot, color="#61D61E")
        self.ax.set_xlabel("Month")
        self.ax.set_ylabel(ylabel)
        self.ax.set_title(f"Year - {filt.capitalize()}")

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

        years = {}
        for r in rows:
            y = r["year"]
            st = r["status"]
            t = r["t_sum"] or 0.0
            cons = r["cons"] or 0.0
            pos = r["pos"] or 0.0
            neg = r["neg"] or 0.0

            if y not in years:
                years[y] = {
                    "time": 0.0,
                    "cons_total": 0.0,
                    "prod_H": 0.0,
                    "prod_C": 0.0,
                    "cons_HC": 0.0,
                }
            years[y]["cons_total"] += cons
            if st != "ON":
                years[y]["time"] += t
            if st == "H":
                years[y]["prod_H"] += pos
                years[y]["cons_HC"] += cons
            elif st == "C":
                years[y]["prod_C"] += abs(neg)
                years[y]["cons_HC"] += cons

        xs = sorted(years.keys())
        ys = []
        for y in xs:
            info = years[y]
            prod_total = info["prod_H"] + info["prod_C"]
            cons_total = info["cons_total"]
            cons_HC = info["cons_HC"]
            if filt == "consumption":
                ys.append(cons_total)
                ylabel = "Consumed (kWh)"
            elif filt == "production":
                ys.append(prod_total)
                ylabel = "Produced (kWh)"
            elif filt == "copwork":
                val = prod_total / cons_HC if cons_HC and cons_HC > 0 else None
                ys.append(val)
                ylabel = "COPwork"
            elif filt == "coptotal":
                val = prod_total / cons_total if cons_total and cons_total > 0 else None
                ys.append(val)
                ylabel = "COPtotal"
            elif filt == "time":
                ys.append((info["time"] or 0.0) / 3600.0)
                ylabel = "Time (hours)"
            else:
                ys.append(cons_total)
                ylabel = "Consumed (kWh)"

        xs_plot = []
        ys_plot = []
        for y, v in zip(xs, ys):
            if v is not None:
                xs_plot.append(y)
                ys_plot.append(v)

        if not xs_plot:
            self.ax.text(0.5, 0.5, "No data", color="white",
                         ha="center", va="center", transform=self.ax.transAxes)
            return

        self.ax.bar(xs_plot, ys_plot, color="#61D61E")
        self.ax.set_xlabel("Year")
        self.ax.set_ylabel(ylabel)
        self.ax.set_title(f"Total - {filt.capitalize()}")

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
