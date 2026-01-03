#!/usr/bin/env python3
# -*- coding: utf-8 -*-

import os
import time
import threading
import sqlite3
from datetime import datetime, timezone, timedelta
from zoneinfo import ZoneInfo

from pymodbus.client import ModbusSerialClient

# ---------- Device / version ----------
DEVICE_ID = "version16"

# ---------- Helpers ----------
def u32(hi, lo):
    return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)

def i16(v):
    return v - 0x10000 if (v & 0x8000) else v

def now_utc_s():
    # UTC in seconds, no milliseconds
    return int(datetime.now(timezone.utc).timestamp())

def round2(v):
    if v is None:
        return None
    try:
        return round(float(v), 2)
    except Exception:
        return None

# ---------- RS485 / device configs ----------
HEAT_PORT     = "/dev/ttyAMA3"
HEAT_BAUD     = 2400
HEAT_PARITY   = "E"
HEAT_STOP     = 1
HEAT_BYTES    = 8
HEAT_TIMEOUT  = 2  # 1.5
HEAT_UNIT     = 144  # heat meter address

BUS_PORT      = "/dev/ttyAMA2"
BUS_BAUD      = 9600
BUS_PARITY    = "N"
BUS_STOP      = 1
BUS_BYTES     = 8
BUS_TIMEOUT   = 0.8

ENERGY_UNIT   = 1     # JSY-MK-354
TH_UNIT       = 2     # Temp/Humidity

BUS_POLL_SEC   = 1.2
HEAT_POLL_SEC  = 2.5  #1.8
INTER_READ_PAUSE = 0.2

# ---------- Logic parameters ----------
XSEC       = 5        # main logic check interval
ZSEC       = 10       # same non-standby status logging
YSEC       = 300      # standby periodic logging
HPWORK     = 300      # W
HPWORKMIN  = 90       # W
HPFLOW     = 0.2      # m3/h
HPDT       = 0.02      # °C
HPAMB      = 20       # °C

# ---------- SQLite ----------
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DB_PATH       = os.path.join(BASE_DIR, f"{DEVICE_ID}.db")
TABLE_SAMPLES = "hp_samples"
TABLE_DAY     = "day_summary"
TABLE_MONTH   = "month_summary"
TABLE_YEAR    = "year_summary"
TABLE_TOTAL   = "total_summary"

# ---------- Timezone ----------
ROMANIA_TZ = ZoneInfo("Europe/Bucharest")

# ---------- Shared datastore ----------
class DataStore:
    def __init__(self):
        self._d = {}
        self._lock = threading.Lock()

    def update(self, partial):
        with self._lock:
            self._d.update(partial)
            return self._d.copy()

    def snapshot(self):
        with self._lock:
            return self._d.copy()

STORE = DataStore()

# ---------- Readers ----------
class BusReader(threading.Thread):
    """
    EnergyMeter + Temp/Humidity

    From EnergyMeter:
      em_activepower (W)
      em_total_fwd   (kWh)

    From Temp Sensor:
      ts_ambient_temp
      ts_ambient_humidity
    """
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.client = ModbusSerialClient(
            port=BUS_PORT, baudrate=BUS_BAUD, parity=BUS_PARITY,
            stopbits=BUS_STOP, bytesize=BUS_BYTES, timeout=BUS_TIMEOUT
        )
        try:
            self.client.connect()
        except Exception:
            pass

    def safe_regs_holding(self, addr, cnt, unit):
        try:
            rr = self.client.read_holding_registers(address=addr, count=cnt, slave=unit)
            if rr and not rr.isError():
                return rr.registers
        except Exception:
            pass
        return None

    def run(self):
        next_t = time.time()
        while self.running:
            # Active power (W) 0x0109..0x010A
            regs_p = self.safe_regs_holding(0x0109, 2, ENERGY_UNIT)
            if regs_p:
                em_activepower = round2(u32(regs_p[0], regs_p[1]))
                STORE.update({"em_activepower": em_activepower})

            time.sleep(INTER_READ_PAUSE)

            # Total active energy (kWh) @0x0120..0x0121 (/100) -> em_total_fwd
            regs_e = self.safe_regs_holding(0x0120, 2, ENERGY_UNIT)
            if regs_e:
                em_total_fwd = round2(u32(regs_e[0], regs_e[1]) / 100.0)
                STORE.update({"em_total_fwd": em_total_fwd})

            time.sleep(INTER_READ_PAUSE)

            # Temp/Humidity sensor 0x0000..0x0001
            th = self.safe_regs_holding(0x0000, 2, TH_UNIT)
            if th:
                hum  = round2(th[0] / 10.0)
                temp = round2(i16(th[1]) / 10.0)
                STORE.update({
                    "ts_ambient_humidity": hum,
                    "ts_ambient_temp":     temp
                })

            next_t += BUS_POLL_SEC
            time.sleep(max(0.0, next_t - time.time()))

class HeatReader(threading.Thread):
    """
    HeatMeter:
      hm_positive_kwh
      hm_negative_kwh
      hm_temp_IN
      hm_temp_OUT
      hm_temp_diff
      hm_activeflow_m3h
      hm_totalflow
      hm_activepower
      hm_fault_code
      hm_work_h
    """
    def __init__(self):
        super().__init__(daemon=True)
        self.running = True
        self.client = ModbusSerialClient(
            port=HEAT_PORT, baudrate=HEAT_BAUD, parity=HEAT_PARITY,
            stopbits=HEAT_STOP, bytesize=HEAT_BYTES, timeout=HEAT_TIMEOUT
        )
        try:
            self.client.connect()
        except Exception:
            pass

    def safe_regs(self, addr, cnt):
        try:
            rr = self.client.read_holding_registers(address=addr, count=cnt, slave=HEAT_UNIT)
            if rr and not rr.isError():
                return rr.registers
        except Exception:
            pass
        return None

    def run(self):
        next_t = time.time()
        while self.running:
            # Positive cumulative energy (kWh) 0x0000..0x0001 (/100)
            regs = self.safe_regs(0x0000, 2)
            if regs:
                STORE.update({"hm_positive_kwh": round2(u32(regs[0], regs[1]) / 100.0)})

            # Negative cumulative energy (kWh) 0x0002..0x0003 (/100)
            regs = self.safe_regs(0x0002, 2)
            if regs:
                STORE.update({"hm_negative_kwh": round2(u32(regs[0], regs[1]) / 100.0)})

            # Temps (/100)
            regs = self.safe_regs(0x0004, 2)
            if regs:
                STORE.update({"hm_temp_IN": round2(u32(regs[0], regs[1]) / 100.0)})
            regs = self.safe_regs(0x0006, 2)
            if regs:
                STORE.update({"hm_temp_OUT": round2(u32(regs[0], regs[1]) / 100.0)})
            regs = self.safe_regs(0x0008, 2)
            if regs:
                STORE.update({"hm_temp_diff": round2(u32(regs[0], regs[1]) / 100.0)})

            # Cumulative flow + live flow
            regs = self.safe_regs(0x000A, 2)
            if regs:
                STORE.update({"hm_totalflow": round2(u32(regs[0], regs[1]) / 100.0)})  # m³ total
            regs = self.safe_regs(0x000C, 2)
            if regs:
                flow = round2(u32(regs[0], regs[1]) / 10000.0)
                STORE.update({
                    "hm_activeflow_m3h": flow,
                    "hm_flow_m3h": flow
                })

            # Power (kW)
            regs = self.safe_regs(0x000E, 2)
            if regs:
                STORE.update({"hm_activepower": round2(u32(regs[0], regs[1]) / 100.0)})

            # Fault + work hours
            regs = self.safe_regs(0x0010, 1)
            if regs:
                STORE.update({"hm_fault_code": int(regs[0])})
            regs = self.safe_regs(0x0011, 1)
            if regs:
                STORE.update({"hm_work_h": int(regs[0])})

            next_t += HEAT_POLL_SEC
            time.sleep(max(0.0, next_t - time.time()))

# ---------- SQLite writer + summaries ----------
class DBWriterSQLite(threading.Thread):
    def __init__(self, store: DataStore):
        super().__init__(daemon=True)
        self.store = store
        self.running = True
        self.conn = None

        self.first_saved = False        # pentru primul "ON"
        self.last_logical_status = None # ultima stare logică (S/H/C/D)
        self.last_status_stored = None  # ultimul status scris în hp_samples (ON/S/H/C/D)
        self.last_save_time = 0.0       # timp în secunde (time.time())
        self.current_day_local = datetime.now(ROMANIA_TZ).date()

        # Ultima citire (din ultimul loop), chiar dacă nu s-a scris în DB
        self.last_read_data = None
        self.last_read_ts_utc_s = None

        # Segmente offline (OFF) pe zile: { "YYYY-MM-DD": [(start_ts,end_ts), ...] }
        self.offline_segments = {}

        self.setup_db()

    # ---------- DB schema ----------
    def setup_db(self):
        dirn = os.path.dirname(DB_PATH)
        if dirn:
            os.makedirs(dirn, exist_ok=True)
        self.conn = sqlite3.connect(DB_PATH, isolation_level=None, check_same_thread=False)
        cur = self.conn.cursor()
        cur.execute("PRAGMA journal_mode=WAL;")
        cur.execute("PRAGMA synchronous=FULL;")
        cur.execute("PRAGMA temp_store=MEMORY;")
        cur.execute("PRAGMA busy_timeout=5000;")

        # Main samples table
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_SAMPLES} (
                ts_utc_s            INTEGER PRIMARY KEY,
                status              TEXT,

                em_activepower      REAL,
                em_total_fwd        REAL,

                hm_activepower      REAL,
                hm_positive_kwh     REAL,
                hm_negative_kwh     REAL,
                hm_temp_IN          REAL,
                hm_temp_OUT         REAL,
                hm_temp_diff        REAL,
                hm_activeflow_m3h   REAL,
                hm_totalflow        REAL,
                hm_fault_code       INTEGER,
                hm_work_h           REAL,

                ts_ambient_temp     REAL,
                ts_ambient_humidity REAL
            );
        """)
        cur.execute(f"CREATE INDEX IF NOT EXISTS idx_{TABLE_SAMPLES}_time ON {TABLE_SAMPLES}(ts_utc_s);")

        # Day summary
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_DAY} (
                day_date            TEXT,     -- 'YYYY-MM-DD'
                day_start_utc_s     INTEGER,
                status              TEXT,
                start_ts_utc_s      INTEGER,
                end_ts_utc_s        INTEGER,
                total_time_s        INTEGER,
                consumption_kw      REAL,
                positive_kw         REAL,
                negative_kw         REAL,
                hp_temp_in          REAL,
                hp_temp_out         REAL,
                hp_temp_diff        REAL,
                hp_activeflow_m3h   REAL,
                hp_totalflow        REAL,
                ts_ambient_temp     REAL,
                ts_ambient_humidity REAL,
                PRIMARY KEY(day_date, status, start_ts_utc_s)
            );
        """)

        # Month summary
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_MONTH} (
                year                INTEGER,
                month               INTEGER,
                day                 INTEGER,
                status              TEXT,
                total_time_s        INTEGER,
                consumption_kw      REAL,
                positive_kw         REAL,
                negative_kw         REAL,
                hp_temp_in          REAL,
                hp_temp_out         REAL,
                hp_temp_diff        REAL,
                hp_activeflow_m3h   REAL,
                hp_totalflow        REAL,
                ts_ambient_temp     REAL,
                ts_ambient_humidity REAL,
                times_a_day         INTEGER,
                PRIMARY KEY(year, month, day, status)
            );
        """)

        # Year summary
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_YEAR} (
                year                INTEGER,
                month               INTEGER,
                status              TEXT,
                total_time_s        INTEGER,
                consumption_kw      REAL,
                positive_kw         REAL,
                negative_kw         REAL,
                hp_temp_in          REAL,
                hp_temp_out         REAL,
                hp_temp_diff        REAL,
                hp_activeflow_m3h   REAL,
                hp_totalflow        REAL,
                ts_ambient_temp     REAL,
                ts_ambient_humidity REAL,
                times_a_month       INTEGER,
                PRIMARY KEY(year, month, status)
            );
        """)

        # Total summary (per year)
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {TABLE_TOTAL} (
                year                INTEGER,
                status              TEXT,
                total_time_s        INTEGER,
                consumption_kw      REAL,
                positive_kw         REAL,
                negative_kw         REAL,
                hp_temp_in          REAL,
                hp_temp_out         REAL,
                hp_temp_diff        REAL,
                hp_activeflow_m3h   REAL,
                hp_totalflow        REAL,
                ts_ambient_temp     REAL,
                ts_ambient_humidity REAL,
                times_a_year        INTEGER,
                PRIMARY KEY(year, status)
            );
        """)

    # ---------- Status logic ----------
    def compute_logical_status(self, d):
        """
        Logic:

        If em_activepower > HPWORK and hm_activeflow_m3h > 0:
            if Tin > Tout + HPDT      → H
            elif Tin + HPDT < Tout:
                if ambient < HPAMB    → D
                else                  → C
            else                      → last status
        elif em_activepower > HPWORKMIN and hm_activeflow_m3h > HPFLOW:
            status = last status
        else:
            status = S
        """
        em_p  = d.get("em_activepower") or 0.0
        flow  = d.get("hm_activeflow_m3h") or d.get("hm_flow_m3h") or 0.0
        t_in  = d.get("hm_temp_IN")
        t_out = d.get("hm_temp_OUT")
        amb   = d.get("ts_ambient_temp")

        # High power branch
        if em_p > HPWORK and flow > 0:
            if t_in is not None and t_out is not None:
                if t_in > t_out + HPDT:
                    return "H"   # Heating
                if t_in + HPDT < t_out:
                    if amb is not None and amb < HPAMB:
                        return "D"   # Defrost
                    else:
                        return "C"   # Cooling
                return self.last_logical_status or "S"
            else:
                return self.last_logical_status or "S"

        # Medium power + enough flow -> keep last status
        if em_p > HPWORKMIN and flow > HPFLOW:
            return self.last_logical_status or "S"

        # Standby
        return "S"

    # ---------- Insert sample ----------
    def insert_sample(self, cur, data, status, ts_utc_s):
        d = data or {}
        def g(name):
            v = d.get(name)
            return round2(v) if v is not None else None

        row = [
            ts_utc_s,
            status,
            g("em_activepower"),
            g("em_total_fwd"),
            g("hm_activepower"),
            g("hm_positive_kwh"),
            g("hm_negative_kwh"),
            g("hm_temp_IN"),
            g("hm_temp_OUT"),
            g("hm_temp_diff"),
            g("hm_activeflow_m3h"),
            g("hm_totalflow"),
            d.get("hm_fault_code"),
            d.get("hm_work_h"),
            g("ts_ambient_temp"),
            g("ts_ambient_humidity")
        ]
        placeholders = ",".join("?" for _ in row)
        sql = f"INSERT OR REPLACE INTO {TABLE_SAMPLES} VALUES ({placeholders});"
        cur.execute(sql, row)

        STORE.update({
            "last_ts_utc_s": ts_utc_s,
            "status": status
        })

    # ---------- OFF segments calculator ----------
    def compute_offline_segments(self, start_ts_utc_s, end_ts_utc_s):
        """
        Creează segmente OFF pe zile locale, între start_ts și end_ts (UTC sec).
        Rezultat: self.offline_segments = { "YYYY-MM-DD": [(start_ts,end_ts), ...] }
        """
        self.offline_segments = {}
        if start_ts_utc_s is None or end_ts_utc_s is None:
            return
        if end_ts_utc_s <= start_ts_utc_s:
            return

        dt_start_utc = datetime.fromtimestamp(start_ts_utc_s, tz=timezone.utc)
        dt_end_utc   = datetime.fromtimestamp(end_ts_utc_s,   tz=timezone.utc)
        dt_start_loc = dt_start_utc.astimezone(ROMANIA_TZ)
        dt_end_loc   = dt_end_utc.astimezone(ROMANIA_TZ)

        day_start = dt_start_loc.date()
        day_end   = dt_end_loc.date()

        day = day_start
        while day <= day_end:
            if day == day_start:
                seg_start_loc = dt_start_loc
            else:
                seg_start_loc = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=ROMANIA_TZ)

            if day == day_end:
                seg_end_loc = dt_end_loc
            else:
                seg_end_loc = datetime(day.year, day.month, day.day, 0, 0, 0, tzinfo=ROMANIA_TZ) + timedelta(days=1)

            seg_start_utc = int(seg_start_loc.astimezone(timezone.utc).timestamp())
            seg_end_utc   = int(seg_end_loc.astimezone(timezone.utc).timestamp())

            if seg_end_utc > seg_start_utc:
                dstr = day.strftime("%Y-%m-%d")
                self.offline_segments.setdefault(dstr, []).append((seg_start_utc, seg_end_utc))

            day += timedelta(days=1)

    # ---------- DAY summary ----------
    def build_day_summary_for_date(self, day_local):
        """
        Build DAY table rows for one local calendar day.

        - Pentru status ON: o linie cu start_ts = ultima înregistrare
          din hp_samples înainte de ON (dacă există) și end_ts = ts_ON,
          dar total_time_s=0 (ON doar eveniment).
        - Pentru S/H/C/D: segmente cu time/energy/medii.
        - Pentru OFF: se adaugă segmentele pre-calculate din self.offline_segments.
        """
        cur = self.conn.cursor()
        day_str = day_local.strftime("%Y-%m-%d")

        # Time range for this day in UTC seconds
        start_local = datetime(day_local.year, day_local.month, day_local.day, 0, 0, 0, tzinfo=ROMANIA_TZ)
        next_local  = start_local + timedelta(days=1)
        start_utc_s = int(start_local.astimezone(timezone.utc).timestamp())
        end_utc_s   = int(next_local.astimezone(timezone.utc).timestamp())

        # Load all samples for this day
        cur.execute(f"""
            SELECT ts_utc_s, status,
                   em_total_fwd, hm_positive_kwh, hm_negative_kwh,
                   hm_temp_IN, hm_temp_OUT, hm_temp_diff,
                   hm_activeflow_m3h, hm_totalflow,
                   ts_ambient_temp, ts_ambient_humidity
            FROM {TABLE_SAMPLES}
            WHERE ts_utc_s >= ? AND ts_utc_s <= ?
            ORDER BY ts_utc_s ASC;
        """, (start_utc_s, end_utc_s))
        rows = cur.fetchall()

        # Clear existing day_summary for that day (inclusiv OFF / ON / S/H/C/D)
        cur.execute(f"DELETE FROM {TABLE_DAY} WHERE day_date = ?;", (day_str,))

        # 1) Insert ON rows (cu start = ultima înregistrare anterioară)
        for r in rows:
            ts, st = r[0], r[1]
            if st != "ON":
                continue

            cur_prev = self.conn.cursor()
            cur_prev.execute(f"""
                SELECT ts_utc_s FROM {TABLE_SAMPLES}
                WHERE ts_utc_s < ? AND status NOT IN ('ON','OFF')
                ORDER BY ts_utc_s DESC
                LIMIT 1;
            """, (ts,))
            prev_row = cur_prev.fetchone()
            if prev_row:
                start_ts = int(prev_row[0])
            else:
                start_ts = ts

            total_time_s = 0  # ON este doar eveniment

            hp_temp_in        = round2(r[5])
            hp_temp_out       = round2(r[6])
            hp_temp_diff      = round2(r[7])
            hp_flow           = round2(r[8])
            hp_totalflow      = round2(r[9])
            ts_amb_temp       = round2(r[10])
            ts_amb_humidity   = round2(r[11])

            cur.execute(f"""
                INSERT OR REPLACE INTO {TABLE_DAY} (
                    day_date, day_start_utc_s, status,
                    start_ts_utc_s, end_ts_utc_s, total_time_s,
                    consumption_kw, positive_kw, negative_kw,
                    hp_temp_in, hp_temp_out, hp_temp_diff,
                    hp_activeflow_m3h, hp_totalflow,
                    ts_ambient_temp, ts_ambient_humidity
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """, (
                day_str,
                start_utc_s,
                "ON",
                start_ts,
                ts,
                int(total_time_s),
                None, None, None,
                hp_temp_in, hp_temp_out, hp_temp_diff,
                hp_flow, hp_totalflow,
                ts_amb_temp, ts_amb_humidity
            ))

        # 2) Segmente pentru S/H/C/D (ON = boundary)
        allowed_status = {"S", "H", "C", "D"}

        segment_start_idx = None
        segment_status = None

        for i, r in enumerate(rows):
            st = r[1]

            if st not in allowed_status:
                if segment_start_idx is not None:
                    self._store_day_segment(cur, day_str, start_utc_s, rows, segment_start_idx, i - 1)
                    segment_start_idx = None
                    segment_status = None
                continue

            if segment_start_idx is None:
                segment_start_idx = i
                segment_status = st
            else:
                if st != segment_status:
                    self._store_day_segment(cur, day_str, start_utc_s, rows, segment_start_idx, i - 1)
                    segment_start_idx = i
                    segment_status = st

        if segment_start_idx is not None:
            self._store_day_segment(cur, day_str, start_utc_s, rows, segment_start_idx, len(rows) - 1)

        # 3) OFF segments din offline_segments (dacă există pentru ziua asta)
        off_list = self.offline_segments.get(day_str, [])
        for seg_start, seg_end in off_list:
            if seg_end <= seg_start:
                continue
            s = max(seg_start, start_utc_s)
            e = min(seg_end,   end_utc_s)
            if e <= s:
                continue
            total_time_s = e - s

            cur.execute(f"""
                INSERT OR REPLACE INTO {TABLE_DAY} (
                    day_date, day_start_utc_s, status,
                    start_ts_utc_s, end_ts_utc_s, total_time_s,
                    consumption_kw, positive_kw, negative_kw,
                    hp_temp_in, hp_temp_out, hp_temp_diff,
                    hp_activeflow_m3h, hp_totalflow,
                    ts_ambient_temp, ts_ambient_humidity
                ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
            """, (
                day_str,
                start_utc_s,
                "OFF",
                s,
                e,
                int(total_time_s),
                None, None, None,
                None, None, None,
                None, None,
                None, None
            ))

        self.conn.commit()

    def _store_day_segment(self, cur, day_str, day_start_utc_s, rows, i_start, i_end):
        """
        Store one segment in DAY table, from rows[i_start] to rows[i_end].

        Segmentul aparține status-ului din rows[i_start][1] (S/H/C/D).

        i_end poate fi:
          - un rând cu același status (ex: H, H, H ...)
          - PRIMUL rând cu ALT status (ex: H, H, D sau H, H, ON),
            ca să nu pierdem cei 5 secunde și 0.01 kWh.

        IMPORTANT:
          - time  = ts(end) - ts(start)
          - consumption_kw = em_total_fwd(end)      - em_total_fwd(start)
          - positive_kw    = hm_positive_kwh(end)   - hm_positive_kwh(start)
          - negative_kw    = hm_negative_kwh(end)   - hm_negative_kwh(start)
        """
        if i_end <= i_start:
            return

        first = rows[i_start]
        last  = rows[i_end]

        ts_start = first[0]
        status   = first[1]
        ts_end   = last[0]

        if status not in {"S", "H", "C", "D"}:
            return
        if ts_end <= ts_start:
            return

        em_start      = first[2]
        hp_pos_start  = first[3]
        hp_neg_start  = first[4]
        totflow_start = first[9]

        em_end      = last[2]
        hp_pos_end  = last[3]
        hp_neg_end  = last[4]
        totflow_end = last[9]

        total_time_s = ts_end - ts_start
        consumption_kw = (em_end - em_start) if (em_end is not None and em_start is not None) else None
        positive_kw    = (hp_pos_end - hp_pos_start) if (hp_pos_end is not None and hp_pos_start is not None) else None
        negative_kw    = (hp_neg_end - hp_neg_start) if (hp_neg_end is not None and hp_neg_start is not None) else None
        totalflow_diff = (totflow_end - totflow_start) if (totflow_end is not None and totflow_start is not None) else None

        seg = rows[i_start:i_end+1]

        def avg(col_idx):
            vals = [r[col_idx] for r in seg
                    if r[1] == status and r[col_idx] is not None]
            return round2(sum(vals) / len(vals)) if vals else None

        hp_temp_in_avg        = avg(5)
        hp_temp_out_avg       = avg(6)
        hp_temp_diff_avg      = avg(7)
        hp_activeflow_m3h_avg = avg(8)
        ts_ambient_temp_avg   = avg(10)
        ts_ambient_hum_avg    = avg(11)

        cur.execute(f"""
            INSERT OR REPLACE INTO {TABLE_DAY} (
                day_date, day_start_utc_s, status,
                start_ts_utc_s, end_ts_utc_s, total_time_s,
                consumption_kw, positive_kw, negative_kw,
                hp_temp_in, hp_temp_out, hp_temp_diff,
                hp_activeflow_m3h, hp_totalflow,
                ts_ambient_temp, ts_ambient_humidity
            ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
        """, (
            day_str,
            day_start_utc_s,
            status,
            ts_start,
            ts_end,
            int(total_time_s),
            round2(consumption_kw),
            round2(positive_kw),
            round2(negative_kw),
            hp_temp_in_avg,
            hp_temp_out_avg,
            hp_temp_diff_avg,
            hp_activeflow_m3h_avg,
            round2(totalflow_diff),
            ts_ambient_temp_avg,
            ts_ambient_hum_avg
        ))

    # ---------- MONTH, YEAR, TOTAL ----------
    def update_month_year_total_for_day(self, day_local):
        """
        From day_summary for given local day:
          -> update month_summary (per day+status)
          -> update year_summary (per month+status)
          -> update total_summary (per year+status)
        """
        cur = self.conn.cursor()
        day_str = day_local.strftime("%Y-%m-%d")
        year = day_local.year
        month = day_local.month
        day   = day_local.day

        # MONTH table
        cur.execute(f"DELETE FROM {TABLE_MONTH} WHERE year=? AND month=? AND day=?;",
                    (year, month, day))

        cur.execute(f"""
            SELECT status,
                   COUNT(*)                        AS cnt,
                   SUM(total_time_s)               AS t_sum,
                   SUM(consumption_kw)             AS cons_sum,
                   SUM(positive_kw)                AS pos_sum,
                   SUM(negative_kw)                AS neg_sum,
                   SUM(hp_temp_in * total_time_s)  AS tin_weighted,
                   SUM(hp_temp_out * total_time_s) AS tout_weighted,
                   SUM(hp_temp_diff * total_time_s)AS dt_weighted,
                   SUM(hp_activeflow_m3h * total_time_s) AS flow_weighted,
                   SUM(hp_totalflow)               AS flow_tot_sum,
                   SUM(ts_ambient_temp * total_time_s) AS ambt_weighted,
                   SUM(ts_ambient_humidity * total_time_s) AS ambh_weighted,
                   SUM(total_time_s)               AS t_weight
            FROM {TABLE_DAY}
            WHERE day_date=?
            GROUP BY status;
        """, (day_str,))
        rows = cur.fetchall()

        for (status,
             cnt, t_sum, cons_sum, pos_sum, neg_sum,
             tin_weighted, tout_weighted, dt_weighted,
             flow_weighted, flow_tot_sum,
             ambt_weighted, ambh_weighted,
             t_weight) in rows:

            times_a_day = int(cnt) if cnt else 0

            def wavg(weighted, total_t):
                return round2(weighted / total_t) if (weighted is not None and total_t and total_t > 0) else None

            if status == "ON":
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_MONTH} (
                        year, month, day, status,
                        total_time_s, consumption_kw, positive_kw, negative_kw,
                        hp_temp_in, hp_temp_out, hp_temp_diff,
                        hp_activeflow_m3h, hp_totalflow,
                        ts_ambient_temp, ts_ambient_humidity,
                        times_a_day
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, (
                    year, month, day, status,
                    0,
                    None, None, None,
                    None, None, None,
                    None, None,
                    None, None,
                    times_a_day
                ))
            else:
                t_sum_int = int(t_sum) if t_sum else 0
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_MONTH} (
                        year, month, day, status,
                        total_time_s, consumption_kw, positive_kw, negative_kw,
                        hp_temp_in, hp_temp_out, hp_temp_diff,
                        hp_activeflow_m3h, hp_totalflow,
                        ts_ambient_temp, ts_ambient_humidity,
                        times_a_day
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, (
                    year, month, day, status,
                    t_sum_int,
                    round2(cons_sum),
                    round2(pos_sum),
                    round2(neg_sum),
                    wavg(tin_weighted, t_weight),
                    wavg(tout_weighted, t_weight),
                    wavg(dt_weighted, t_weight),
                    wavg(flow_weighted, t_weight),
                    round2(flow_tot_sum),
                    wavg(ambt_weighted, t_weight),
                    wavg(ambh_weighted, t_weight),
                    times_a_day
                ))

        # YEAR table
        cur.execute(f"DELETE FROM {TABLE_YEAR} WHERE year=? AND month=?;", (year, month))
        cur.execute(f"""
            SELECT status,
                   SUM(total_time_s)                      AS t_sum,
                   SUM(consumption_kw)                    AS cons_sum,
                   SUM(positive_kw)                       AS pos_sum,
                   SUM(negative_kw)                       AS neg_sum,
                   SUM(hp_temp_in * total_time_s)         AS tin_weighted,
                   SUM(hp_temp_out * total_time_s)        AS tout_weighted,
                   SUM(hp_temp_diff * total_time_s)       AS dt_weighted,
                   SUM(hp_activeflow_m3h * total_time_s)  AS flow_weighted,
                   SUM(hp_totalflow)                      AS flow_tot_sum,
                   SUM(ts_ambient_temp * total_time_s)    AS ambt_weighted,
                   SUM(ts_ambient_humidity * total_time_s)AS ambh_weighted,
                   SUM(total_time_s)                      AS t_weight,
                   SUM(times_a_day)                       AS times_a_month
            FROM {TABLE_MONTH}
            WHERE year=? AND month=?
            GROUP BY status;
        """, (year, month))
        rows = cur.fetchall()

        for (status,
             t_sum, cons_sum, pos_sum, neg_sum,
             tin_weighted, tout_weighted, dt_weighted,
             flow_weighted, flow_tot_sum,
             ambt_weighted, ambh_weighted,
             t_weight, times_a_month) in rows:

            times_a_month = int(times_a_month) if times_a_month else 0

            def wavg(weighted, total_t):
                return round2(weighted / total_t) if (weighted is not None and total_t and total_t > 0) else None

            if status == "ON":
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_YEAR} (
                        year, month, status,
                        total_time_s, consumption_kw, positive_kw, negative_kw,
                        hp_temp_in, hp_temp_out, hp_temp_diff,
                        hp_activeflow_m3h, hp_totalflow,
                        ts_ambient_temp, ts_ambient_humidity,
                        times_a_month
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, (
                    year, month, status,
                    0,
                    None, None, None,
                    None, None, None,
                    None, None,
                    None, None,
                    times_a_month
                ))
            else:
                t_sum_int = int(t_sum) if t_sum else 0
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_YEAR} (
                        year, month, status,
                        total_time_s, consumption_kw, positive_kw, negative_kw,
                        hp_temp_in, hp_temp_out, hp_temp_diff,
                        hp_activeflow_m3h, hp_totalflow,
                        ts_ambient_temp, ts_ambient_humidity,
                        times_a_month
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, (
                    year, month, status,
                    t_sum_int,
                    round2(cons_sum),
                    round2(pos_sum),
                    round2(neg_sum),
                    wavg(tin_weighted, t_weight),
                    wavg(tout_weighted, t_weight),
                    wavg(dt_weighted, t_weight),
                    wavg(flow_weighted, t_weight),
                    round2(flow_tot_sum),
                    wavg(ambt_weighted, t_weight),
                    wavg(ambh_weighted, t_weight),
                    times_a_month
                ))

        # TOTAL table (per year)
        cur.execute(f"DELETE FROM {TABLE_TOTAL} WHERE year=?;", (year,))
        cur.execute(f"""
            SELECT status,
                   SUM(total_time_s)                      AS t_sum,
                   SUM(consumption_kw)                    AS cons_sum,
                   SUM(positive_kw)                       AS pos_sum,
                   SUM(negative_kw)                       AS neg_sum,
                   SUM(hp_temp_in * total_time_s)         AS tin_weighted,
                   SUM(hp_temp_out * total_time_s)        AS tout_weighted,
                   SUM(hp_temp_diff * total_time_s)       AS dt_weighted,
                   SUM(hp_activeflow_m3h * total_time_s)  AS flow_weighted,
                   SUM(hp_totalflow)                      AS flow_tot_sum,
                   SUM(ts_ambient_temp * total_time_s)    AS ambt_weighted,
                   SUM(ts_ambient_humidity * total_time_s)AS ambh_weighted,
                   SUM(total_time_s)                      AS t_weight,
                   SUM(times_a_month)                     AS times_a_year
            FROM {TABLE_YEAR}
            WHERE year=?
            GROUP BY status;
        """, (year,))
        rows = cur.fetchall()

        for (status,
             t_sum, cons_sum, pos_sum, neg_sum,
             tin_weighted, tout_weighted, dt_weighted,
             flow_weighted, flow_tot_sum,
             ambt_weighted, ambh_weighted,
             t_weight, times_a_year) in rows:

            times_a_year = int(times_a_year) if times_a_year else 0

            def wavg(weighted, total_t):
                return round2(weighted / total_t) if (weighted is not None and total_t and total_t > 0) else None

            if status == "ON":
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_TOTAL} (
                        year, status,
                        total_time_s, consumption_kw, positive_kw, negative_kw,
                        hp_temp_in, hp_temp_out, hp_temp_diff,
                        hp_activeflow_m3h, hp_totalflow,
                        ts_ambient_temp, ts_ambient_humidity,
                        times_a_year
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, (
                    year, status,
                    0,
                    None, None, None,
                    None, None, None,
                    None, None,
                    None, None,
                    times_a_year
                ))
            else:
                t_sum_int = int(t_sum) if t_sum else 0
                cur.execute(f"""
                    INSERT OR REPLACE INTO {TABLE_TOTAL} (
                        year, status,
                        total_time_s, consumption_kw, positive_kw, negative_kw,
                        hp_temp_in, hp_temp_out, hp_temp_diff,
                        hp_activeflow_m3h, hp_totalflow,
                        ts_ambient_temp, ts_ambient_humidity,
                        times_a_year
                    ) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?);
                """, (
                    year, status,
                    t_sum_int,
                    round2(cons_sum),
                    round2(pos_sum),
                    round2(neg_sum),
                    wavg(tin_weighted, t_weight),
                    wavg(tout_weighted, t_weight),
                    wavg(dt_weighted, t_weight),
                    wavg(flow_weighted, t_weight),
                    round2(flow_tot_sum),
                    wavg(ambt_weighted, t_weight),
                    wavg(ambh_weighted, t_weight),
                    times_a_year
                ))

        self.conn.commit()

    # ---------- Main run loop ----------
    def run(self):
        cur = self.conn.cursor()
        while self.running:
            time.sleep(XSEC)

            data_now = self.store.snapshot()
            if not data_now:
                continue

            ts_now_utc_s = now_utc_s()
            now_t = time.time()
            now_utc = datetime.fromtimestamp(ts_now_utc_s, tz=timezone.utc)
            now_local = now_utc.astimezone(ROMANIA_TZ)

            # Day change
            today = now_local.date()
            if today != self.current_day_local:
                prev_day = self.current_day_local
                self.build_day_summary_for_date(prev_day)
                self.update_month_year_total_for_day(prev_day)
                self.conn.commit()
                self.current_day_local = today

            logical_status = self.compute_logical_status(data_now)

            pending_offline = None

            if not self.first_saved:
                status_to_store = "ON"

                cur_prev = self.conn.cursor()
                cur_prev.execute(f"""
                    SELECT ts_utc_s FROM {TABLE_SAMPLES}
                    WHERE status NOT IN ('ON','OFF')
                    ORDER BY ts_utc_s DESC
                    LIMIT 1;
                """)
                row = cur_prev.fetchone()
                if row:
                    offline_start_ts = int(row[0])
                    if ts_now_utc_s > offline_start_ts:
                        pending_offline = (offline_start_ts, ts_now_utc_s)
            else:
                status_to_store = logical_status

            prev_status_stored = self.last_status_stored
            status_changed = (
                prev_status_stored is not None
                and status_to_store != prev_status_stored
            )

            # decidem dacă scriem
            if not self.first_saved:
                should_write = True
            else:
                if status_changed:
                    should_write = True
                else:
                    if status_to_store == "S":
                        interval_needed = YSEC
                    else:
                        interval_needed = ZSEC
                    should_write = (now_t - self.last_save_time) >= interval_needed

            if not should_write:
                self.last_logical_status = logical_status
                self.last_read_data = data_now
                self.last_read_ts_utc_s = ts_now_utc_s
                continue

            # Bridge S -> alt status cu citirea anterioară
            if (
                self.first_saved
                and status_changed
                and prev_status_stored == "S"
                and status_to_store != "S"
            ):
                dt_since_last_write = now_t - self.last_save_time
                if (
                    dt_since_last_write > XSEC
                    and self.last_read_data is not None
                    and self.last_read_ts_utc_s is not None
                ):
                    self.insert_sample(cur, self.last_read_data, "S", self.last_read_ts_utc_s)

            # Scriem statusul actual
            self.insert_sample(cur, data_now, status_to_store, ts_now_utc_s)
            self.conn.commit()

            if not self.first_saved:
                self.first_saved = True

                if pending_offline is not None:
                    off_start, off_end = pending_offline
                    self.compute_offline_segments(off_start, off_end)

                    for day_str in sorted(self.offline_segments.keys()):
                        day_local = datetime.fromisoformat(day_str).date()
                        self.build_day_summary_for_date(day_local)
                        self.update_month_year_total_for_day(day_local)
                    self.conn.commit()

            self.last_logical_status = logical_status
            self.last_save_time = now_t
            self.last_status_stored = status_to_store

            self.last_read_data = data_now
            self.last_read_ts_utc_s = ts_now_utc_s

            if status_changed:
                day_local = now_local.date()
                self.build_day_summary_for_date(day_local)
                self.update_month_year_total_for_day(day_local)
                self.conn.commit()

# ---------- funcție helper pentru GUI ----------
def start_system():
    """
    Pornim BusReader, HeatReader și DBWriterSQLite
    și returnăm thread-urile pentru a putea fi oprite din GUI.
    """
    bus = BusReader()
    heat = HeatReader()
    writer = DBWriterSQLite(STORE)

    bus.start()
    heat.start()
    writer.start()

    return bus, heat, writer
