import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from PyQt5 import QtCore, QtWidgets
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusIOException


# ---------------------------
#  Modbus wrapper
# ---------------------------

class ModbusWrapper:
    def __init__(self, port="/dev/ttyAMA3", slave_id=1, baudrate=9600): #
        self.port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.client: Optional[ModbusSerialClient] = None

    def connect(self) -> bool:
        if self.client:
            self.client.close()

        self.client = ModbusSerialClient(
            port=self.port,
            baudrate=self.baudrate,
            parity="N",
            stopbits=1,
            bytesize=8,
            timeout=1.0,
        )
        return self.client.connect()

    def read_block(self, start: int, count: int) -> Optional[List[int]]:
        """
        Read a consecutive block of holding registers.

        Handles different pymodbus versions and communication errors.
        Returns None on any error (no exception raised).
        """
        if not self.client:
            return None

        rr = None

        # Try new-style API first (pymodbus 3.x): address, *, count=, slave=
        try:
            rr = self.client.read_holding_registers(
                start,
                count=count,
                slave=self.slave_id,
            )
        except TypeError:
            # Fallback: older style with unit=
            try:
                rr = self.client.read_holding_registers(
                    start,
                    count=count,
                    unit=self.slave_id,
                )
            except TypeError:
                # Very old: address + count only
                try:
                    rr = self.client.read_holding_registers(start, count)
                except Exception:
                    return None
        except ModbusIOException:
            # No response from slave
            return None
        except Exception:
            # Any other unexpected error
            return None

        if rr is None or rr.isError():
            return None

        return rr.registers

    def read_all_registers(self) -> Dict[int, int]:
        """
        Read all registers 0x0000 .. 0x00A1 (0 .. 161) in two blocks.
        Returns a dict {address: value}. If communication fails, it may be empty.
        """
        data: Dict[int, int] = {}

        # Modbus limit ~125 registers per read
        blocks = [
            (0x0000, 120),  # 0 .. 119  (0x0000 .. 0x0077)
            (0x0078, 42),   # 0x0078 .. 0x00A1
        ]
        for start, count in blocks:
            regs = self.read_block(start, count)
            if regs is None:
                # Communication error for this block -> skip, but DON'T crash
                continue
            for i, val in enumerate(regs):
                data[start + i] = val
        return data

    def write_register(self, address: int, value: int) -> bool:
        """
        Write a single holding register, compatible with multiple pymodbus versions.
        Returns False on any error (no exception raised).
        """
        if not self.client:
            return False

        rq = None

        # New-style: write_register(address, value, slave=...)
        try:
            rq = self.client.write_register(
                address,
                value,
                slave=self.slave_id,
            )
        except TypeError:
            # Old-style: write_register(address, value, unit=...)
            try:
                rq = self.client.write_register(
                    address,
                    value,
                    unit=self.slave_id,
                )
            except TypeError:
                # Very old: maybe only (address, value)
                try:
                    rq = self.client.write_register(address, value)
                except Exception:
                    return False
        except ModbusIOException:
            return False
        except Exception:
            return False

        return (rq is not None) and (not rq.isError())


# ---------------------------
#  Register definitions
# ---------------------------

@dataclass
class RegisterDef:
    addr: int
    name: str
    rw: str      # "R" or "RW"
    group: str   # GUI tab name
    scale: Optional[float] = None  # e.g. 0.5 for temp*2, 0.1 for temp*10
    unit: str = ""
    note: str = ""                 # short explanation


REGS: List[RegisterDef] = [
    # ---- Sensors & temperatures ----
    RegisterDef(0x0000, "BTW inlet temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0001, "BTW outlet temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0002, "Heating coil temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0003, "Cooling coil temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0004, "Ambient temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0005, "DHW tank temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0006, "Suction temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0007, "Exhaust temp", "R", "Sensors", 0.5, "°C",
                note="Discharge gas temperature"),
    RegisterDef(0x0008, "Solar water temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x0009, "BTW tank temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x000A, "IPM / heat sink temp", "R", "Sensors", 0.1, "°C"),
    RegisterDef(0x000B, "EVI inlet temp", "R", "Sensors", 0.1, "°C"),
    RegisterDef(0x000C, "EVI outlet temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x000D, "Ground in temp", "R", "Sensors", 0.5, "°C"),
    RegisterDef(0x000E, "Ground out temp", "R", "Sensors", 0.5, "°C"),

    # ---- Actuators / feedback ----
    RegisterDef(0x000F, "Main EEV opening", "R", "Actuators", None, "steps"),
    RegisterDef(0x0010, "EVI EEV opening", "R", "Actuators", None, "steps"),
    RegisterDef(0x0011, "Fan1 speed", "R", "Actuators"),
    RegisterDef(0x0012, "Fan2 speed", "R", "Actuators"),
    RegisterDef(0x0013, "DC bus voltage", "R", "Actuators", None, "V"),
    RegisterDef(0x0014, "Compressor frequency", "R", "Actuators", None, "Hz"),
    RegisterDef(0x0015, "Compressor current", "R", "Actuators", None, "A"),

    # ---- Outputs ----
    RegisterDef(0x0016, "Output flag 1", "R", "Outputs",
                note="Bits: HW EH, AC EH1, AC EH2, Defrost, 3-way valve, Sterilization"),
    RegisterDef(0x0017, "Output flag 2", "R", "Outputs",
                note="Bits: High fan, 4-way valve, Fan, EVI valve, Compressor"),
    RegisterDef(0x0018, "Output flag 3", "R", "Outputs",
                note="Bits: Circulation pump, Cooling 3-way, Ground pump, Solar pump, crank/chassis"),

    # ---- Faults & inverter ----
    RegisterDef(0x0019, "Fault flag 1", "R", "Faults"),
    RegisterDef(0x001A, "Fault flag 2", "R", "Faults"),
    RegisterDef(0x001B, "Fault flag 3", "R", "Faults"),
    RegisterDef(0x001C, "Fault flag 4", "R", "Faults"),
    RegisterDef(0x001D, "Fault flag 5", "R", "Faults"),
    RegisterDef(0x001E, "Fault flag 6", "R", "Faults"),
    RegisterDef(0x001F, "Fault flag 7", "R", "Faults"),
    RegisterDef(0x0020, "Fault flag 8", "R", "Faults"),
    RegisterDef(0x0021, "Fault flag 9", "R", "Faults"),
    RegisterDef(0x0022, "Inverter module flag 1", "R", "Faults"),
    RegisterDef(0x0023, "Inverter module flag 2", "R", "Faults"),
    RegisterDef(0x0024, "Reserved 0x0024", "R", "Reserved"),

    # ---- Runtime counters ----
    RegisterDef(0x0025, "Pump runtime (h)", "R", "Runtime"),
    RegisterDef(0x0026, "Compressor runtime (h)", "R", "Runtime"),
    RegisterDef(0x0027, "AC EH1 runtime (h)", "R", "Runtime"),
    RegisterDef(0x0028, "AC EH2 runtime (h)", "R", "Runtime"),
    RegisterDef(0x0029, "DHW EH runtime (h)", "R", "Runtime"),
    RegisterDef(0x002A, "Ground pump runtime (h)", "R", "Runtime"),
    RegisterDef(0x002B, "Pump start count", "R", "Runtime"),
    RegisterDef(0x002C, "Compressor start count", "R", "Runtime"),
    RegisterDef(0x002D, "AC EH1 start count", "R", "Runtime"),
    RegisterDef(0x002E, "AC EH2 start count", "R", "Runtime"),
    RegisterDef(0x002F, "DHW EH start count", "R", "Runtime"),
    RegisterDef(0x0030, "Night mode status", "R", "Runtime"),
    RegisterDef(0x0031, "Reserved 0x0031", "R", "Reserved"),
    RegisterDef(0x0032, "Reserved 0x0032", "R", "Reserved"),
    RegisterDef(0x0033, "Reserved 0x0033", "R", "Reserved"),
    RegisterDef(0x0034, "Reserved 0x0034", "R", "Reserved"),
    RegisterDef(0x0035, "Reserved 0x0035", "R", "Reserved"),

    # ---- Control flags & modes ----
    RegisterDef(0x0036, "Control flag 1", "RW", "Control",
                note="Bit7 HW EH, Bit6 Power, Bit5 AC EH, Bit4 Solar system"),
    RegisterDef(0x0037, "Control flag 2", "RW", "Control",
                note="Bit6 Sterilization, Bit4 Main EEV auto/man, Bit3 Freq auto/man, Bit1 EVI auto/man, Bit0 EVI ON/OFF"),
    RegisterDef(0x0038, "Control flag 3", "RW", "Control",
                note="Bit7 Night, Bit6 Refrigerant, Bit5/4 HP/LP, Bit3/2 Fan1/2 used, Bit0 Fan auto/man"),
    RegisterDef(0x0039, "Mode selection", "RW", "Control",
                note="0=DHW,1=Heat,2=Cool,3=DHW+Heat,4=DHW+Cool"),

    # ---- Setpoints ----
    RegisterDef(0x003A, "DHW set temp", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x003B, "Heating set temp", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x003C, "Cooling set temp", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x003D, "Curve set temp / room", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x003E, "Auto curve start BTW", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x003F, "Auto curve max BTW", "RW", "Setpoints", None, "°C"),

    RegisterDef(0x0040, "DHW hysteresis ΔT", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x0041, "BTW hysteresis ΔT", "RW", "Setpoints", None, "°C"),
    RegisterDef(0x0042, "Reserved 0x0042", "RW", "Reserved"),
    RegisterDef(0x0043, "Reserved 0x0043", "RW", "Reserved"),

    # ---- Frequency & fan ----
    RegisterDef(0x0044, "Frequency code", "RW", "Freq/Fan",
                note="Selects internal model table"),
    RegisterDef(0x0045, "Manual frequency", "RW", "Freq/Fan", None, "Hz",
                note="Used when Control flag2 Bit3=1 (manual freq)"),
    RegisterDef(0x0046, "DHW tank factor", "RW", "Freq/Fan",
                note="Scales Fmax in DHW mode"),
    RegisterDef(0x0047, "Exhaust TP0", "RW", "Freq/Fan", None, "°C"),
    RegisterDef(0x0048, "Exhaust TP1", "RW", "Freq/Fan", None, "°C"),
    RegisterDef(0x0049, "Exhaust TP2", "RW", "Freq/Fan", None, "°C"),
    RegisterDef(0x004A, "Exhaust TP3", "RW", "Freq/Fan", None, "°C"),
    RegisterDef(0x004B, "Exhaust TP4", "RW", "Freq/Fan", None, "°C"),
    RegisterDef(0x004C, "Manual fan index", "RW", "Freq/Fan",
                note="1..6, used when fan manual"),
    RegisterDef(0x004D, "Manual fan speed 1", "RW", "Freq/Fan"),
    RegisterDef(0x004E, "Manual fan speed 2", "RW", "Freq/Fan"),
    RegisterDef(0x004F, "Manual fan speed 3", "RW", "Freq/Fan"),
    RegisterDef(0x0050, "Manual fan speed 4", "RW", "Freq/Fan"),
    RegisterDef(0x0051, "Manual fan speed 5", "RW", "Freq/Fan"),
    RegisterDef(0x0052, "Manual fan speed 6", "RW", "Freq/Fan"),

    # ---- Main EEV & EVI ----
    RegisterDef(0x0053, "Main EEV initial opening", "RW", "EEV/EVI", None, "steps"),
    RegisterDef(0x0054, "Main EEV manual opening", "RW", "EEV/EVI", None, "steps",
                note="Used when Control flag2 Bit4=1 (manual main valve)"),
    RegisterDef(0x0055, "Reserved 0x0055", "RW", "Reserved"),
    RegisterDef(0x0056, "Reserved 0x0056", "RW", "Reserved"),
    RegisterDef(0x0057, "EVI start ambient temp", "RW", "EEV/EVI", None, "°C"),
    RegisterDef(0x0058, "EVI start ΔT", "RW", "EEV/EVI", None, "°C"),
    RegisterDef(0x0059, "EVI target superheat", "RW", "EEV/EVI", None, "°C"),
    RegisterDef(0x005A, "EVI initial opening", "RW", "EEV/EVI", None, "steps"),
    RegisterDef(0x005B, "EVI manual opening", "RW", "EEV/EVI", None, "steps"),

    # ---- Defrost ----
    RegisterDef(0x005C, "Defrost cycle", "RW", "Defrost", None, "min"),
    RegisterDef(0x005D, "Defrost entry temp", "RW", "Defrost", None, "°C"),
    RegisterDef(0x005E, "Defrost exit temp", "RW", "Defrost", None, "°C"),
    RegisterDef(0x005F, "Defrost max time", "RW", "Defrost", None, "min"),
    RegisterDef(0x0060, "ΔT defrost ambient entry", "RW", "Defrost", None, "°C"),
    RegisterDef(0x0061, "Defrost coil exit temp", "RW", "Defrost", None, "°C"),
    RegisterDef(0x0062, "Ambient defrost entry", "RW", "Defrost", None, "°C"),
    RegisterDef(0x0063, "Defrost frequency", "RW", "Defrost", None, "Hz"),
    RegisterDef(0x0064, "Reserved 0x0064", "RW", "Reserved"),
    RegisterDef(0x0065, "Reserved 0x0065", "RW", "Reserved"),

    # ---- DHW EH & heating mode ----
    RegisterDef(0x0066, "DHW EH ΔT", "RW", "Heating/EH", None, "°C"),
    RegisterDef(0x0067, "DHW EH start delay", "RW", "Heating/EH", None, "min"),
    RegisterDef(0x0068, "Heating mode", "RW", "Heating/EH",
                note="manual/auto/segmented (0..2)"),
    RegisterDef(0x0069, "Reserved 0x0069", "RW", "Reserved"),
    RegisterDef(0x006A, "Reserved 0x006A", "RW", "Reserved"),
    RegisterDef(0x006B, "Reserved 0x006B", "RW", "Reserved"),
    RegisterDef(0x006C, "BTW pump mode", "RW", "Heating/EH",
                note="0=continuous,1=5min stop,2=anti-freeze cycling"),
    RegisterDef(0x006D, "Reserved 0x006D", "RW", "Reserved"),
    RegisterDef(0x006E, "Heat source mode", "RW", "Heating/EH",
                note="0=Air-source,1=Ground-source"),
    RegisterDef(0x006F, "Ground outlet overcool protect", "RW", "Heating/EH", None, "°C"),
    RegisterDef(0x0070, "Ground outlet antifreeze", "RW", "Heating/EH", None, "°C"),
    RegisterDef(0x0071, "Ground ambient antifreeze", "RW", "Heating/EH", None, "°C"),
    RegisterDef(0x0072, "Heating function mode", "RW", "Heating/EH"),

    # ---- Timers & segmented temps ----
    RegisterDef(0x0073, "Timer period 1", "RW", "Timers"),
    RegisterDef(0x0074, "Timer period 2", "RW", "Timers"),
    RegisterDef(0x0075, "Timer period 3", "RW", "Timers"),
    RegisterDef(0x0076, "Timer period 4", "RW", "Timers"),
    RegisterDef(0x0077, "Period1 heating set temp", "RW", "Timers", None, "°C"),
    RegisterDef(0x0078, "Period2 heating set temp", "RW", "Timers", None, "°C"),
    RegisterDef(0x0079, "Period3 heating set temp", "RW", "Timers", None, "°C"),
    RegisterDef(0x007A, "Period4 heating set temp", "RW", "Timers", None, "°C"),
    RegisterDef(0x007B, "Reserved 0x007B", "RW", "Reserved"),

    # ---- Sterilization ----
    RegisterDef(0x007C, "Sterilization temp", "RW", "Sterilization", None, "°C"),
    RegisterDef(0x007D, "Sterilization cycle (days)", "RW", "Sterilization"),
    RegisterDef(0x007E, "Sterilization start hour", "RW", "Sterilization", None, "h"),
    RegisterDef(0x007F, "Sterilization max time", "RW", "Sterilization", None, "min"),
    RegisterDef(0x0080, "High temp hold time", "RW", "Sterilization", None, "min"),

    # ---- Timer enable + detailed times ----
    RegisterDef(0x0081, "Timing enable bits", "RW", "Timers",
                note="Bits0-3 enable periods 1..4"),
    RegisterDef(0x0082, "Timer1 ON hour", "RW", "Timers"),
    RegisterDef(0x0083, "Timer1 ON minute", "RW", "Timers"),
    RegisterDef(0x0084, "Timer1 OFF hour", "RW", "Timers"),
    RegisterDef(0x0085, "Timer1 OFF minute", "RW", "Timers"),
    RegisterDef(0x0086, "Timer2 ON hour", "RW", "Timers"),
    RegisterDef(0x0087, "Timer2 ON minute", "RW", "Timers"),
    RegisterDef(0x0088, "Timer2 OFF hour", "RW", "Timers"),
    RegisterDef(0x0089, "Timer2 OFF minute", "RW", "Timers"),
    RegisterDef(0x008A, "Timer3 ON hour", "RW", "Timers"),
    RegisterDef(0x008B, "Timer3 ON minute", "RW", "Timers"),
    RegisterDef(0x008C, "Timer3 OFF hour", "RW", "Timers"),
    RegisterDef(0x008D, "Timer3 OFF minute", "RW", "Timers"),
    RegisterDef(0x008E, "Timer4 ON hour", "RW", "Timers"),
    RegisterDef(0x008F, "Timer4 ON minute", "RW", "Timers"),
    RegisterDef(0x0090, "Timer4 OFF hour", "RW", "Timers"),
    RegisterDef(0x0091, "Timer4 OFF minute", "RW", "Timers"),

    # ---- Superheat / evaporation ----
    RegisterDef(0x0092, "Exhaust superheat", "RW", "Night & Limits", None, "°C"),
    RegisterDef(0x0093, "Evaporation temp", "RW", "Night & Limits", None, "°C"),
    RegisterDef(0x0094, "Evaporation ON diff", "RW", "Night & Limits", None, "°C"),
    RegisterDef(0x0095, "Evaporation OFF hysteresis", "RW", "Night & Limits", None, "°C"),

    # ---- Night mode & max freq ----
    RegisterDef(0x0096, "Fan max speed", "RW", "Night & Limits"),
    RegisterDef(0x0097, "Fan min speed", "RW", "Night & Limits"),
    RegisterDef(0x0098, "Night mode frequency", "RW", "Night & Limits", None, "Hz"),
    RegisterDef(0x0099, "Night mode fan speed", "RW", "Night & Limits"),
    RegisterDef(0x009A, "Night mode start hour", "RW", "Night & Limits"),
    RegisterDef(0x009B, "Night mode end hour", "RW", "Night & Limits"),
    RegisterDef(0x009C, "DHW max frequency", "RW", "Night & Limits", None, "Hz"),
    RegisterDef(0x009D, "Heating max frequency", "RW", "Night & Limits", None, "Hz"),
    RegisterDef(0x009E, "Cooling max frequency", "RW", "Night & Limits", None, "Hz"),

    # ---- AC EH & thresholds ----
    RegisterDef(0x009F, "AC EH2 delay", "RW", "Heating/EH", None, "min"),
    RegisterDef(0x00A0, "Air-source EH start ambient", "RW", "Heating/EH", None, "°C"),
    RegisterDef(0x00A1, "Ground-source EH start inlet", "RW", "Heating/EH", None, "°C"),
]

REG_BY_ADDR: Dict[int, RegisterDef] = {r.addr: r for r in REGS}


# ---------------------------
#  GUI
# ---------------------------

class RegisterTable(QtWidgets.QTableWidget):
    COL_ADDR = 0
    COL_NAME = 1
    COL_RW = 2
    COL_RAW = 3
    COL_VALUE = 4
    COL_UNIT = 5
    COL_INPUT = 6
    COL_BTN = 7
    COL_NOTE = 8

    def __init__(self, regs: List[RegisterDef], modbus: ModbusWrapper, parent=None):
        super().__init__(parent)
        self.modbus = modbus
        self.regs = regs
        self.setColumnCount(9)
        self.setHorizontalHeaderLabels([
            "Addr", "Name", "R/W", "Raw", "Value", "Unit", "New value", "Write", "Note"
        ])
        self.setRowCount(len(regs))
        self._setup_rows()
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)
        self.verticalHeader().setVisible(False)

    def _setup_rows(self):
        for row, reg in enumerate(self.regs):
            addr_item = QtWidgets.QTableWidgetItem(f"0x{reg.addr:04X}")
            addr_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_ADDR, addr_item)

            name_item = QtWidgets.QTableWidgetItem(reg.name)
            name_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_NAME, name_item)

            rw_item = QtWidgets.QTableWidgetItem(reg.rw)
            rw_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_RW, rw_item)

            raw_item = QtWidgets.QTableWidgetItem("")
            raw_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_RAW, raw_item)

            val_item = QtWidgets.QTableWidgetItem("")
            val_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_VALUE, val_item)

            unit_item = QtWidgets.QTableWidgetItem(reg.unit)
            unit_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_UNIT, unit_item)

            input_edit = QtWidgets.QLineEdit()
            if reg.rw == "R":
                input_edit.setEnabled(False)
            self.setCellWidget(row, self.COL_INPUT, input_edit)

            btn = QtWidgets.QPushButton("Write")
            btn.setEnabled(reg.rw == "RW")
            btn.clicked.connect(self._make_write_handler(row))
            self.setCellWidget(row, self.COL_BTN, btn)

            note_item = QtWidgets.QTableWidgetItem(reg.note)
            note_item.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
            self.setItem(row, self.COL_NOTE, note_item)

    def _make_write_handler(self, row: int):
        def handler():
            reg = self.regs[row]
            if reg.rw != "RW":
                return
            editor: QtWidgets.QLineEdit = self.cellWidget(row, self.COL_INPUT)
            text = editor.text().strip()
            if not text:
                return
            try:
                if reg.scale is not None:
                    real_val = float(text)
                    raw = int(round(real_val / reg.scale))
                else:
                    raw = int(text)
            except ValueError:
                QtWidgets.QMessageBox.warning(self, "Invalid input",
                                              f"Cannot convert '{text}' to int/float")
                return

            ok = self.modbus.write_register(reg.addr, raw)
            if not ok:
                QtWidgets.QMessageBox.warning(self, "Write failed",
                                              f"Write to 0x{reg.addr:04X} failed")

        return handler

    def update_values(self, data: Dict[int, int]):
        for row, reg in enumerate(self.regs):
            raw_val = data.get(reg.addr, None)
            raw_item = self.item(row, self.COL_RAW)
            val_item = self.item(row, self.COL_VALUE)

            if raw_val is None:
                raw_item.setText("N/A")
                val_item.setText("N/A")
                continue

            raw_item.setText(str(raw_val))

            if reg.scale is not None:
                real_val = raw_val * reg.scale
                val_item.setText(f"{real_val:.1f}")
            else:
                val_item.setText(str(raw_val))


class MainWindow(QtWidgets.QMainWindow):
    def __init__(self, modbus: ModbusWrapper):
        super().__init__()
        self.modbus = modbus
        self.setWindowTitle("Heatpump Modbus Monitor")

        self.tabs = QtWidgets.QTabWidget()
        self.setCentralWidget(self.tabs)

        # Group registers into tabs
        groups: Dict[str, List[RegisterDef]] = {}
        for reg in REGS:
            groups.setdefault(reg.group, []).append(reg)

        self.tables: List[RegisterTable] = []
        for group_name in sorted(groups.keys()):
            regs = sorted(groups[group_name], key=lambda r: r.addr)
            table = RegisterTable(regs, modbus)
            self.tables.append(table)
            self.tabs.addTab(table, group_name)

        self.status = self.statusBar()
        self.status.showMessage("Connecting...")

        # Poll timer: every 2 seconds
        self.timer = QtCore.QTimer(self)
        self.timer.setInterval(2000)
        self.timer.timeout.connect(self.poll_once)

        if self.modbus.connect():
            self.status.showMessage("Connected")
            self.timer.start()
        else:
            self.status.showMessage("Failed to connect to Modbus slave")

    @QtCore.pyqtSlot()
    def poll_once(self):
        data = self.modbus.read_all_registers()
        if not data:
            self.status.showMessage("Modbus read error (no data)")
            # Keep GUI running, just show N/A in tables
            for table in self.tables:
                table.update_values({})
            return

        self.status.showMessage(f"Last update OK ({len(data)} registers)")
        for table in self.tables:
            table.update_values(data)


def main():
    port = "/dev/ttySC0"   # change if needed
    slave_id = 1
    baudrate = 9600

    modbus = ModbusWrapper(port=port, slave_id=slave_id, baudrate=baudrate)

    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow(modbus)
    win.resize(1400, 800)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
