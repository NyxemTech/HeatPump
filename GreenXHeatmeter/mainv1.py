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
    # QGridLayout nu-l folosim acum, dar lăsat în caz de extindere
from PyQt5.QtCore import Qt, QTimer
from PyQt5.QtGui import QFont, QPixmap

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


def load_icon(path, size=32):
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

        # LIVE card (no title)
        self.live_card = self._build_live_card()
        left.addWidget(self.live_card)

        # small separator
        sep = QFrame()
        sep.setObjectName("sepLine")
        sep.setFrameShape(QFrame.HLine)
        sep.setFixedHeight(2)
        left.addWidget(sep)

        # Last, Day, Month, Year, Total
        self.last_card, self.last_vals = self._build_summary_card("Last", show_cop_total=False)
        left.addWidget(self.last_card)

        self.day_card, self.day_vals = self._build_summary_card("Day")
        left.addWidget(self.day_card)

        self.month_card, self.month_vals = self._build_summary_card("Month")
        left.addWidget(self.month_card)

        self.year_card, self.year_vals = self._build_summary_card("Year")
        left.addWidget(self.year_card)

        self.total_card, self.total_vals = self._build_summary_card("Total")
        left.addWidget(self.total_card)

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
                self.logo_label.setPixmap(pm.scaledToHeight(72, Qt.SmoothTransformation))
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
            if i == 0:
                btn.setChecked(True)
            self.btn_zoom_group.addButton(btn)
            zoom_row.addWidget(btn)

        zoom_row.addStretch(1)

        # chart placeholder
        self.chart_frame = QFrame()
        self.chart_frame.setFrameShape(QFrame.StyledPanel)
        self.chart_frame.setStyleSheet("QFrame { border:1px solid #333; border-radius:8px; background-color:#080808; }")
        chart_layout = QVBoxLayout(self.chart_frame)
        chart_layout.setContentsMargins(4, 4, 4, 4)
        self.lbl_chart_placeholder = QLabel("Statistics graph (coming soon)")
        self.lbl_chart_placeholder.setAlignment(Qt.AlignCenter)
        self.lbl_chart_placeholder.setFont(self.normal_font)
        chart_layout.addWidget(self.lbl_chart_placeholder)
        controls_and_chart.addWidget(self.chart_frame, 1)

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

        # status row
        row_status = QHBoxLayout()
        self.live_status_icon = load_icon(ICON_STANDBY, size=32)
        row_status.addWidget(self.live_status_icon, 0, Qt.AlignLeft)

        self.live_status_label = QLabel("Status: —")
        self.live_status_label.setFont(self.bold_font)
        row_status.addWidget(self.live_status_label, 1, Qt.AlignLeft | Qt.AlignVCenter)

        layout.addLayout(row_status)

        # produced
        row_prod = QHBoxLayout()
        row_prod.addWidget(QLabel("Produced kW:"), 0, Qt.AlignLeft)
        self.live_produced = QLabel("—")
        self.live_produced.setFont(self.bold_font)
        row_prod.addWidget(self.live_produced, 1, Qt.AlignRight)
        layout.addLayout(row_prod)

        # consumed
        row_cons = QHBoxLayout()
        icon_e = load_icon(ICON_ELECTRIC, size=20)
        row_cons.addWidget(icon_e, 0, Qt.AlignLeft)
        lbl_c = QLabel("Consumed kW:")
        row_cons.addWidget(lbl_c, 0, Qt.AlignLeft)
        self.live_consumed = QLabel("—")
        self.live_consumed.setFont(self.bold_font)
        row_cons.addWidget(self.live_consumed, 1, Qt.AlignRight)
        layout.addLayout(row_cons)

        # COP
        row_cop = QHBoxLayout()
        row_cop.addWidget(QLabel("COP:"), 0, Qt.AlignLeft)
        self.live_cop = QLabel("—")
        self.live_cop.setFont(self.bold_font)
        row_cop.addWidget(self.live_cop, 1, Qt.AlignRight)
        layout.addLayout(row_cop)

        return frame

    def _build_summary_card(self, title, show_cop_total=True):
        frame = QFrame()
        frame.setProperty("class", "card")
        layout = QVBoxLayout(frame)
        layout.setContentsMargins(8, 4, 8, 4)
        layout.setSpacing(2)

        title_lbl = QLabel(title)
        title_lbl.setFont(self.bold_font)
        layout.addWidget(title_lbl, 0, Qt.AlignLeft)

        icon_label = None
        if title == "Last":
            row_top = QHBoxLayout()
            icon_label = load_icon(ICON_HEATING, size=24)
            row_top.addWidget(icon_label, 0, Qt.AlignLeft)
            self.last_status_text = QLabel("—")
            self.last_status_text.setFont(self.normal_font)
            row_top.addWidget(self.last_status_text, 1, Qt.AlignLeft)
            layout.addLayout(row_top)

        # Produced
        row_p = QHBoxLayout()
        row_p.addWidget(QLabel("Produced kWh:"), 0, Qt.AlignLeft)
        val_prod = QLabel("—")
        val_prod.setFont(self.bold_font)
        row_p.addWidget(val_prod, 1, Qt.AlignRight)
        layout.addLayout(row_p)

        # Consumed
        row_c = QHBoxLayout()
        row_c.addWidget(QLabel("Consumed kWh:"), 0, Qt.AlignLeft)
        val_cons = QLabel("—")
        val_cons.setFont(self.bold_font)
        row_c.addWidget(val_cons, 1, Qt.AlignRight)
        layout.addLayout(row_c)

        # COPwork
        row_copw = QHBoxLayout()
        row_copw.addWidget(QLabel("COPwork:"), 0, Qt.AlignLeft)
        val_copw = QLabel("—")
        val_copw.setFont(self.bold_font)
        row_copw.addWidget(val_copw, 1, Qt.AlignRight)
        layout.addLayout(row_copw)

        # COPtotal (not for Last)
        val_copt = None
        if show_cop_total:
            row_copt = QHBoxLayout()
            row_copt.addWidget(QLabel("COPtotal:"), 0, Qt.AlignLeft)
            val_copt = QLabel("—")
            val_copt.setFont(self.bold_font)
            row_copt.addWidget(val_copt, 1, Qt.AlignRight)
            layout.addLayout(row_copt)

        vals = {
            "icon": icon_label,
            "produced": val_prod,
            "consumed": val_cons,
            "cop_work": val_copw,
            "cop_total": val_copt,
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
            self.update_period_card("day", self.day_vals)
            self.update_period_card("month", self.month_vals)
            self.update_period_card("year", self.year_vals)
            self.update_period_card("total", self.total_vals)
        except Exception:
            # dacă DB este ocupată, nu vrem să crape UI
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

        icon_path = ICON_STANDBY
        if status == "H":
            icon_path = ICON_HEATING
        elif status == "C":
            icon_path = ICON_COOLING
        elif status == "D":
            icon_path = ICON_DEFROST
        if os.path.exists(icon_path):
            pm = QPixmap(icon_path)
            if not pm.isNull():
                self.live_status_icon.setPixmap(pm.scaled(32, 32, Qt.KeepAspectRatio, Qt.SmoothTransformation))

        hm_power = snap.get("hm_activepower")
        if status in ("H", "C") and hm_power is not None:
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
            for key, lbl in self.last_vals.items():
                if isinstance(lbl, QLabel) and key != "icon":
                    lbl.setText("—")
            if self.last_vals["icon"] is not None:
                self.last_vals["icon"].clear()
            self.last_status_text.setText("—")
            return

        status = row["status"]
        cons = row["consumption_kw"] or 0.0
        pos = row["positive_kw"] or 0.0
        neg = row["negative_kw"] or 0.0

        if status == "H":
            produced = pos
            status_text = "Heating"
            icon_path = ICON_HEATING
        else:
            produced = abs(neg)
            status_text = "Cooling"
            icon_path = ICON_COOLING

        cop_work = produced / cons if cons and cons > 0 else None

        self.last_status_text.setText(status_text)
        if self.last_vals["icon"] is not None and os.path.exists(icon_path):
            pm = QPixmap(icon_path)
            if not pm.isNull():
                self.last_vals["icon"].setPixmap(
                    pm.scaled(24, 24, Qt.KeepAspectRatio, Qt.SmoothTransformation)
                )

        self.last_vals["produced"].setText(f"{round2(produced):.2f}" if produced is not None else "—")
        self.last_vals["consumed"].setText(f"{round2(cons):.2f}" if cons is not None else "—")
        self.last_vals["cop_work"].setText(f"{cop_work:.2f}" if cop_work is not None else "—")
        # no COPtotal here

    # ----------------- aggregate helper -----------------
    def _aggregate_period(self, level):
        """
        Return (produced_kwh, consumed_total_kwh, cop_work, cop_total)
        for Day / Month / Year / Total using summary tables.
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

    def update_period_card(self, level, vals_dict):
        produced, consumed_total, cop_work, cop_total = self._aggregate_period(level)

        if produced is not None:
            vals_dict["produced"].setText(f"{produced:.2f}")
        else:
            vals_dict["produced"].setText("—")

        if consumed_total is not None:
            vals_dict["consumed"].setText(f"{consumed_total:.2f}")
        else:
            vals_dict["consumed"].setText("—")

        if cop_work is not None:
            vals_dict["cop_work"].setText(f"{cop_work:.2f}")
        else:
            vals_dict["cop_work"].setText("—")

        if vals_dict.get("cop_total") is not None:
            if cop_total is not None:
                vals_dict["cop_total"].setText(f"{cop_total:.2f}")
            else:
                vals_dict["cop_total"].setText("—")

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
