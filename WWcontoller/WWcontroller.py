import sys
from dataclasses import dataclass
from typing import Dict, List, Optional

from PyQt5 import QtCore, QtWidgets
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusIOException


# ---------------------------
#  Register definitions
# ---------------------------

@dataclass
class RegisterDef:
    addr: int
    name: str
    rw: str      # "R" or "RW"
    group: str   # logical group
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


# Fast poll: sensors + outputs + faults + inverter + control + hysteresis+reserved nearby
def is_fast_reg(reg: RegisterDef) -> bool:
    return (
        0x0000 <= reg.addr <= 0x000E or   # sensors
        0x0016 <= reg.addr <= 0x0018 or   # outputs
        0x0019 <= reg.addr <= 0x0023 or   # faults + inverter flags
        0x0036 <= reg.addr <= 0x0039 or   # control flags + mode
        0x0040 <= reg.addr <= 0x0043      # hysteresis + reserved
    )


STATUS_REGS: List[RegisterDef] = [r for r in REGS if is_fast_reg(r)]
CONFIG_REGS: List[RegisterDef] = [r for r in REGS if not is_fast_reg(r)]

# 0x0000..0x0043 (68 regs) fast
FAST_START = 0x0000
FAST_COUNT = 0x0044  # 68 decimal

# 0x0044..0x00A1 (94 regs) slow/config
CONFIG_START = 0x0044
CONFIG_COUNT = (0x00A1 - 0x0044 + 1)  # 94 regs


# ---------------------------
#  Modbus wrapper
# ---------------------------

class ModbusWrapper:
    def __init__(self, port="/dev/ttySC0", slave_id=1, baudrate=9600):
        self.port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.client: Optional[ModbusSerialClient] = None

    def connect(self) -> bool:
        if self.client:
            self.client.close()

        # Short timeout + 0 retries so UI doesn’t freeze if no answer
        try:
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=0.3,
                retries=0,
            )
        except TypeError:
            # Older pymodbus without retries param
            self.client = ModbusSerialClient(
                port=self.port,
                baudrate=self.baudrate,
                parity="N",
                stopbits=1,
                bytesize=8,
                timeout=0.3,
            )
        return self.client.connect()

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def _read_range(self, start: int, count: int) -> Optional[List[int]]:
        """
        Read a consecutive range of holding registers.
        Returns list of ints or None on any error.
        """
        if not self.client:
            return None

        rr = None
        try:
            # New pymodbus 3.x: address as positional, count/slave as kw
            rr = self.client.read_holding_registers(
                start,
                count=count,
                slave=self.slave_id,
            )
        except TypeError:
            # Older style with unit=
            try:
                rr = self.client.read_holding_registers(
                    address=start,
                    count=count,
                    unit=self.slave_id,
                )
            except Exception:
                return None
        except ModbusIOException:
            return None
        except Exception:
            return None

        if rr is None or rr.isError():
            return None
        return rr.registers

    def read_fast_status(self) -> Dict[int, int]:
        """
        Read 'fast' block: 0x0000..0x0043
        """
        regs = self._read_range(FAST_START, FAST_COUNT)
        if regs is None:
            return {}
        return {FAST_START + i: v for i, v in enumerate(regs)}

    def read_config_registers(self) -> Dict[int, int]:
        """
        Read 'config' block: 0x0044..0x00A1
        """
        regs = self._read_range(CONFIG_START, CONFIG_COUNT)
        if regs is None:
            return {}
        return {CONFIG_START + i: v for i, v in enumerate(regs)}

    def write_register(self, address: int, value: int) -> bool:
        """
        Write a single holding register. Returns False on error.
        """
        if not self.client:
            return False

        rq = None
        try:
            rq = self.client.write_register(
                address,
                value,
                slave=self.slave_id,
            )
        except TypeError:
            try:
                rq = self.client.write_register(
                    address=address,
                    value=value,
                    unit=self.slave_id,
                )
            except Exception:
                return False
        except ModbusIOException:
            return False
        except Exception:
            return False

        return (rq is not None) and (not rq.isError())


# ---------------------------
#  GUI tables
# ---------------------------

class RegisterTable(QtWidgets.QTableWidget):
    COL_ADDR = 0
    COL_NAME = 1
    COL_RW = 2
    COL_GROUP = 3
    COL_RAW = 4
    COL_VALUE = 5
    COL_UNIT = 6
    COL_NOTE = 7

    def __init__(self, regs: List[RegisterDef], parent=None):
        super().__init__(parent)
        self.regs = regs
        self.setColumnCount(8)
        self.setHorizontalHeaderLabels([
            "Addr", "Name", "R/W", "Group", "Raw", "Value", "Unit", "Note"
        ])
        self.setRowCount(len(regs))
        self._setup_rows()
        self.verticalHeader().setVisible(False)
        self.horizontalHeader().setSectionResizeMode(QtWidgets.QHeaderView.ResizeToContents)

    def _setup_rows(self):
        for row, reg in enumerate(self.regs):
            def _item(text: str) -> QtWidgets.QTableWidgetItem:
                it = QtWidgets.QTableWidgetItem(text)
                it.setFlags(QtCore.Qt.ItemIsSelectable | QtCore.Qt.ItemIsEnabled)
                return it

            self.setItem(row, self.COL_ADDR, _item(f"0x{reg.addr:04X}"))
            self.setItem(row, self.COL_NAME, _item(reg.name))
            self.setItem(row, self.COL_RW, _item(reg.rw))
            self.setItem(row, self.COL_GROUP, _item(reg.group))
            self.setItem(row, self.COL_RAW, _item(""))
            self.setItem(row, self.COL_VALUE, _item(""))
            self.setItem(row, self.COL_UNIT, _item(reg.unit))
            self.setItem(row, self.COL_NOTE, _item(reg.note))

    def update_values(self, data: Dict[int, int]):
        for row, reg in enumerate(self.regs):
            raw_val = data.get(reg.addr)
            raw_item = self.item(row, self.COL_RAW)
            val_item = self.item(row, self.COL_VALUE)

            if raw_val is None:
                raw_item.setText("N/A")
                val_item.setText("N/A")
            else:
                raw_item.setText(str(raw_val))
                if reg.scale is not None:
                    real_val = raw_val * reg.scale
                    val_item.setText(f"{real_val:.1f}")
                else:
                    val_item.setText(str(raw_val))


# ---------------------------
#  Main window
# ---------------------------

class MainWindow(QtWidgets.QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Heatpump RS485 Monitor & Writer")

        self.modbus = ModbusWrapper()
        self.last_data: Dict[int, int] = {}

        central = QtWidgets.QWidget()
        self.setCentralWidget(central)
        main_layout = QtWidgets.QVBoxLayout(central)

        # --- Top bar (port, slave, connect) ---
        top = QtWidgets.QHBoxLayout()
        main_layout.addLayout(top)

        top.addWidget(QtWidgets.QLabel("Port:"))
        self.port_edit = QtWidgets.QLineEdit("/dev/ttySC0")
        top.addWidget(self.port_edit)

        top.addWidget(QtWidgets.QLabel("Slave ID:"))
        self.slave_spin = QtWidgets.QSpinBox()
        self.slave_spin.setRange(0, 247)
        self.slave_spin.setValue(1)
        top.addWidget(self.slave_spin)

        self.btn_connect = QtWidgets.QPushButton("Connect")
        self.btn_connect.clicked.connect(self.connect_clicked)
        top.addWidget(self.btn_connect)

        self.btn_disconnect = QtWidgets.QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self.disconnect_clicked)
        top.addWidget(self.btn_disconnect)

        self.status_label = QtWidgets.QLabel("Disconnected")
        top.addWidget(self.status_label)

        top.addStretch()

        # --- Tabs: Status + Config ---
        self.tabs = QtWidgets.QTabWidget()
        main_layout.addWidget(self.tabs)

        self.status_table = RegisterTable(sorted(STATUS_REGS, key=lambda r: r.addr))
        self.config_table = RegisterTable(sorted(REGS, key=lambda r: r.addr))

        self.tabs.addTab(self.status_table, "Status (1s)")
        self.tabs.addTab(self.config_table, "Config (3s on tab)")

        self.tabs.currentChanged.connect(self.on_tab_changed)

        # --- Writer panel (bottom) ---
        writer_box = QtWidgets.QGroupBox("Write register")
        writer_layout = QtWidgets.QFormLayout(writer_box)
        main_layout.addWidget(writer_box)

        self.reg_combo = QtWidgets.QComboBox()
        for reg in sorted(REGS, key=lambda r: r.addr):
            self.reg_combo.addItem(f"0x{reg.addr:04X} - {reg.name}", reg.addr)
        self.reg_combo.currentIndexChanged.connect(self.on_reg_combo_changed)
        writer_layout.addRow("Register:", self.reg_combo)

        self.addr_spin = QtWidgets.QSpinBox()
        self.addr_spin.setRange(0, 0x00A1)
        self.addr_spin.valueChanged.connect(self.on_addr_spin_changed)
        writer_layout.addRow("Address:", self.addr_spin)

        self.current_value_label = QtWidgets.QLabel("N/A")
        writer_layout.addRow("Current value:", self.current_value_label)

        self.value_spin = QtWidgets.QSpinBox()
        self.value_spin.setRange(0, 65535)
        writer_layout.addRow("New value:", self.value_spin)

        self.info_label = QtWidgets.QLabel("")
        writer_layout.addRow("Info:", self.info_label)

        self.btn_write = QtWidgets.QPushButton("Write")
        self.btn_write.clicked.connect(self.write_clicked)
        writer_layout.addRow(self.btn_write)

        # Poll timers
        self.fast_timer = QtCore.QTimer(self)
        self.fast_timer.setInterval(1000)  # 1s
        self.fast_timer.timeout.connect(self.poll_fast)

        self.config_timer = QtCore.QTimer(self)
        self.config_timer.setInterval(3000)  # 3s
        self.config_timer.timeout.connect(self.poll_config)

        # Initialize writer combo -> addr/info
        self.on_reg_combo_changed(0)

    # ----------------- Connection handling -----------------

    def connect_clicked(self):
        self.modbus.port = self.port_edit.text().strip()
        self.modbus.slave_id = self.slave_spin.value()

        if self.modbus.connect():
            self.status_label.setText(f"Connected (ID {self.modbus.slave_id})")
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.last_data.clear()
            self.fast_timer.start()

            # If config tab currently visible, start its timer too
            if self.tabs.currentWidget() is self.config_table:
                self.config_timer.start()
        else:
            QtWidgets.QMessageBox.warning(self, "Error", "Could not open serial port")
            self.status_label.setText("Disconnected")

    def disconnect_clicked(self):
        self.fast_timer.stop()
        self.config_timer.stop()
        self.modbus.close()
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.status_label.setText("Disconnected")

    # ----------------- Tab change -----------------

    def on_tab_changed(self, index: int):
        widget = self.tabs.widget(index)
        if widget is self.config_table and self.btn_disconnect.isEnabled():
            # Connected and switched to config -> start slow timer
            self.config_timer.start()
        else:
            # Any other tab -> stop slow timer
            self.config_timer.stop()

    # ----------------- Polling -----------------

    def poll_fast(self):
        data = self.modbus.read_fast_status()
        if not data:
            self.status_label.setText("Fast poll: no response")
            # still update tables with what we have (will show N/A)
            self.status_table.update_values(self.last_data)
            if self.tabs.currentWidget() is self.config_table:
                self.config_table.update_values(self.last_data)
            return

        self.last_data.update(data)
        self.status_table.update_values(self.last_data)
        if self.tabs.currentWidget() is self.config_table:
            self.config_table.update_values(self.last_data)

        self.status_label.setText(f"Fast poll OK ({len(self.last_data)} regs)")

        # update writer current value display for selected address
        self.update_writer_current_value()

    def poll_config(self):
        # Only active when config tab visible (controlled by on_tab_changed)
        data = self.modbus.read_config_registers()
        if not data:
            self.status_label.setText("Config poll: no response")
            self.config_table.update_values(self.last_data)
            return

        self.last_data.update(data)
        self.config_table.update_values(self.last_data)
        # also refresh status table in case overlapping regs
        self.status_table.update_values(self.last_data)

        self.status_label.setText("Config poll OK")

        self.update_writer_current_value()

    # ----------------- Writer panel logic -----------------

    def on_reg_combo_changed(self, index: int):
        addr = self.reg_combo.currentData()
        if addr is None:
            return
        self.addr_spin.blockSignals(True)
        self.addr_spin.setValue(addr)
        self.addr_spin.blockSignals(False)
        self.update_writer_info(addr)
        self.update_writer_current_value()

    def on_addr_spin_changed(self, value: int):
        # Sync combo if this address exists in table
        for i in range(self.reg_combo.count()):
            if self.reg_combo.itemData(i) == value:
                self.reg_combo.blockSignals(True)
                self.reg_combo.setCurrentIndex(i)
                self.reg_combo.blockSignals(False)
                break
        self.update_writer_info(value)
        self.update_writer_current_value()

    def update_writer_info(self, addr: int):
        reg = REG_BY_ADDR.get(addr)
        if reg is None:
            self.info_label.setText("Unknown register (0..65535 allowed)")
            self.btn_write.setEnabled(True)
            return

        info = f"{reg.name} | {reg.rw}"
        if reg.note:
            info += f" | {reg.note}"
        self.info_label.setText(info)
        self.btn_write.setEnabled(reg.rw == "RW")

    def update_writer_current_value(self):
        addr = self.addr_spin.value()
        val = self.last_data.get(addr)
        if val is None:
            self.current_value_label.setText("N/A")
        else:
            self.current_value_label.setText(str(val))

    def write_clicked(self):
        addr = self.addr_spin.value()
        value = self.value_spin.value()
        ok = self.modbus.write_register(addr, value)
        if ok:
            QtWidgets.QMessageBox.information(self, "Write", f"Wrote {value} to 0x{addr:04X}")
            # Next poll will refresh the display
        else:
            QtWidgets.QMessageBox.warning(self, "Write", f"Failed to write 0x{value:04X} to 0x{addr:04X}")


def main():
    app = QtWidgets.QApplication(sys.argv)
    win = MainWindow()
    win.resize(1100, 700)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
