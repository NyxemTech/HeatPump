import sys
import time

from PyQt5.QtWidgets import (
    QApplication, QMainWindow, QWidget, QVBoxLayout, QHBoxLayout,
    QTableWidget, QTableWidgetItem, QPushButton, QLabel, QLineEdit,
    QSpinBox, QMessageBox, QGroupBox, QFormLayout, QComboBox
)
from PyQt5.QtCore import QTimer, Qt

from pymodbus.client import ModbusSerialClient
from pymodbus.pdu import ExceptionResponse
from pymodbus.exceptions import ModbusIOException


# ----------------- Register map (adapt to your device) -----------------
REGISTERS = [
    {"addr": 0, "name": "Power", "desc": "0=Off,1=On", "min": 0, "max": 1, "writable": True},
    {"addr": 1, "name": "Mode", "desc": "0=Cool,1=Heat,2=Vent", "min": 0, "max": 3, "writable": True},
    {"addr": 2, "name": "Fan speed set", "desc": "1–5", "min": 1, "max": 5, "writable": True},
    {"addr": 3, "name": "Fan mode", "desc": "0=Manual,1=Auto", "min": 0, "max": 1, "writable": True},
    {"addr": 4, "name": "Set temp", "desc": "5–55 °C", "min": 5, "max": 55, "writable": True},
    {"addr": 5, "name": "Low limit", "desc": "5–55", "min": 5, "max": 55, "writable": True},
    {"addr": 6, "name": "High limit", "desc": "5–55", "min": 5, "max": 55, "writable": True},
    {"addr": 7, "name": "Antifreeze", "desc": "0/1", "min": 0, "max": 1, "writable": True},
    {"addr": 8, "name": "Anti cold wind", "desc": "0–50", "min": 0, "max": 50, "writable": True},
    {"addr": 9, "name": "Stop strategy", "desc": "0/1/2", "min": 0, "max": 2, "writable": True},
    {"addr": 10, "name": "Offset", "desc": "0–18", "min": 0, "max": 18, "writable": True},
    {"addr": 11, "name": "Child lock", "desc": "0/1", "min": 0, "max": 1, "writable": True},
    {"addr": 12, "name": "Hysteresis", "desc": "1–5", "min": 1, "max": 5, "writable": True},
    {"addr": 13, "name": "Power-on", "desc": "0/1/2", "min": 0, "max": 2, "writable": True},
    {"addr": 14, "name": "RS485 ID", "desc": "0–99", "min": 0, "max": 99, "writable": True},

    {"addr": 15, "name": "Fan1", "desc": "0–2000", "min": 0, "max": 2000, "writable": True},
    {"addr": 16, "name": "Fan2", "desc": "0–2000", "min": 0, "max": 2000, "writable": True},
    {"addr": 17, "name": "Fan3", "desc": "0–2000", "min": 0, "max": 2000, "writable": True},
    {"addr": 18, "name": "Fan4", "desc": "0–2000", "min": 0, "max": 2000, "writable": True},
    {"addr": 19, "name": "Fan5", "desc": "0–2000", "min": 0, "max": 2000, "writable": True},

    {"addr": 20, "name": "Ambient T", "desc": "°C", "min": 0, "max": 90, "writable": False},
    {"addr": 21, "name": "Pipe T", "desc": "°C", "min": 0, "max": 90, "writable": False},
    {"addr": 22, "name": "Real RPM", "desc": "", "min": 0, "max": 2000, "writable": False},
    {"addr": 23, "name": "Demand RPM", "desc": "", "min": 0, "max": 2000, "writable": False},
    {"addr": 24, "name": "Status bits", "desc": "", "min": 0, "max": 65535, "writable": False},
    {"addr": 25, "name": "Gear", "desc": "0–5", "min": 0, "max": 5, "writable": False},
]

REG_BY_ADDR = {r["addr"]: r for r in REGISTERS}


# ----------------- Modbus wrapper -----------------
class ModbusWrapper:
    def __init__(self, port="/dev/ttySC0", slave_id=1, baudrate=9600):
        self.port = port
        self.slave_id = slave_id
        self.baudrate = baudrate
        self.client = None

    def connect(self):
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

    def close(self):
        if self.client:
            self.client.close()
            self.client = None

    def read_all_registers(self):
        if not self.client:
            raise RuntimeError("Client not connected")

        rr = self.client.read_holding_registers(
            address=0,          # start address
            count=26,           # 0..25
            slave=self.slave_id
        )
        if not rr or rr.isError():
            raise RuntimeError(f"Read error: {rr}")

        return {i: v for i, v in enumerate(rr.registers)}

    def write_register(self, addr, value):
        if not self.client:
            raise RuntimeError("Client not connected")

        rq = self.client.write_register(
            address=addr,
            value=value,
            slave=self.slave_id
        )
        if not rq or rq.isError():
            raise RuntimeError(f"Write error: {rq}")


# ----------------- GUI -----------------
class MainWindow(QMainWindow):
    def __init__(self):
        super().__init__()
        self.setWindowTitle("Ventilo RS485 Monitor + Writer")
        self.modbus = ModbusWrapper()

        central = QWidget()
        self.setCentralWidget(central)
        layout = QVBoxLayout(central)

        # --- Top bar ---
        top = QHBoxLayout()
        layout.addLayout(top)

        top.addWidget(QLabel("Port:"))
        self.port = QLineEdit("/dev/ttySC0")
        top.addWidget(self.port)

        top.addWidget(QLabel("Slave ID:"))
        self.slave = QSpinBox()
        self.slave.setRange(0, 255)
        self.slave.setValue(1)
        top.addWidget(self.slave)

        self.btn_connect = QPushButton("Connect")
        self.btn_connect.clicked.connect(self.connect_clicked)
        top.addWidget(self.btn_connect)

        self.btn_disconnect = QPushButton("Disconnect")
        self.btn_disconnect.setEnabled(False)
        self.btn_disconnect.clicked.connect(self.disconnect_clicked)
        top.addWidget(self.btn_disconnect)

        self.btn_scan = QPushButton("Scan IDs 0–255")
        self.btn_scan.clicked.connect(self.scan_ids)
        top.addWidget(self.btn_scan)

        self.status = QLabel("Disconnected")
        top.addWidget(self.status)

        # --- Table ---
        self.table = QTableWidget(len(REGISTERS), 6)
        self.table.setHorizontalHeaderLabels(
            ["Addr", "Name", "Desc", "Min", "Max", "Value"]
        )
        self.table.verticalHeader().setVisible(False)
        layout.addWidget(self.table)
        self.fill_table()

        # --- Writer panel ---
        box = QGroupBox("Write Register")
        form = QFormLayout(box)
        layout.addWidget(box)

        self.cmb = QComboBox()
        for r in REGISTERS:
            self.cmb.addItem(f"{r['addr']:02d} - {r['name']}", r["addr"])
        self.cmb.currentIndexChanged.connect(self.select_reg)
        form.addRow("Register:", self.cmb)

        self.addr_edit = QSpinBox()
        self.addr_edit.setRange(0, 125)
        self.addr_edit.valueChanged.connect(self.select_addr)
        form.addRow("Address:", self.addr_edit)

        self.lbl_curr = QLabel("-")
        form.addRow("Current value:", self.lbl_curr)

        self.val_edit = QSpinBox()
        self.val_edit.setRange(0, 65535)
        form.addRow("New value:", self.val_edit)

        self.lbl_range = QLabel("-")
        form.addRow("Allowed range:", self.lbl_range)

        self.btn_write = QPushButton("Write")
        self.btn_write.clicked.connect(self.write_reg)
        form.addRow(self.btn_write)

        # Poll timer
        self.timer = QTimer()
        self.timer.setInterval(1000)
        self.timer.timeout.connect(self.poll)

        # Initialize writer UI
        self.select_reg(0)

    # ----------------- Table setup -----------------
    def fill_table(self):
        for i, r in enumerate(REGISTERS):
            for col, val in enumerate([
                r["addr"], r["name"], r["desc"], r["min"], r["max"], "-"
            ]):
                self.table.setItem(i, col, QTableWidgetItem(str(val)))
        self.table.resizeColumnsToContents()

    # ----------------- Connect / Disconnect -----------------
    def connect_clicked(self):
        self.modbus.port = self.port.text().strip()
        self.modbus.slave_id = self.slave.value()

        ok = self.modbus.connect()
        if ok:
            self.status.setText(f"Connected ID {self.modbus.slave_id}")
            self.timer.start()
            self.btn_connect.setEnabled(False)
            self.btn_disconnect.setEnabled(True)
            self.btn_scan.setEnabled(False)
        else:
            QMessageBox.warning(self, "Error", "Could not connect to port.")

    def disconnect_clicked(self):
        self.timer.stop()
        self.modbus.close()
        self.btn_connect.setEnabled(True)
        self.btn_disconnect.setEnabled(False)
        self.btn_scan.setEnabled(True)
        self.status.setText("Disconnected")

    # ----------------- Poll loop -----------------
    def poll(self):
        try:
            values = self.modbus.read_all_registers()
        except Exception as e:
            self.status.setText(f"Read error: {e}")
            return

        for i, r in enumerate(REGISTERS):
            vitem = self.table.item(i, 5)
            vitem.setText(str(values.get(r["addr"], "-")))

        self.status.setText("OK")
        addr = self.addr_edit.value()
        if addr in values:
            self.lbl_curr.setText(str(values[addr]))

    # ----------------- Scan IDs 0–255 -----------------
    def scan_ids(self):
        port = self.port.text().strip()
        self.status.setText("Scanning IDs 0–255...")
        QApplication.processEvents()

        client = ModbusSerialClient(
            port=port,
            baudrate=9600,      # adjust if your device uses another one
            parity="N",
            stopbits=1,
            bytesize=8,
            timeout=1.0,
        )

        if not client.connect():
            QMessageBox.warning(self, "Error", "Cannot open port.")
            return

        self.btn_scan.setEnabled(False)
        self.btn_connect.setEnabled(False)

        found = None
        for sid in range(0, 256):
            self.status.setText(f"Checking ID {sid}...")
            QApplication.processEvents()

            try:
                rr = client.read_holding_registers(
                    address=0,
                    count=1,
                    slave=sid
                )

                if rr is None:
                    pass
                elif isinstance(rr, ExceptionResponse):
                    print(f"ID {sid}: exception response (device exists): {rr}")
                    found = sid
                    break
                elif isinstance(rr, ModbusIOException):
                    pass
                else:
                    if not rr.isError():
                        print(f"ID {sid}: ok, value={rr.registers[0]}")
                        found = sid
                        break

            except Exception as e:
                print(f"Error probing ID {sid}: {e}")

            time.sleep(0.05)

        client.close()
        self.btn_scan.setEnabled(True)
        self.btn_connect.setEnabled(True)

        if found is None:
            self.status.setText("No device found")
            QMessageBox.information(self, "Scan", "No device found on IDs 0–255.")
        else:
            self.slave.setValue(found)
            self.status.setText(f"Found ID {found}")
            self.connect_clicked()

    # ----------------- Writer panel -----------------
    def select_reg(self, index):
        addr = self.cmb.currentData()
        self.addr_edit.setValue(addr)
        self.update_range(addr)

    def select_addr(self, addr):
        for i, r in enumerate(REGISTERS):
            if r["addr"] == addr:
                self.cmb.setCurrentIndex(i)
                break
        self.update_range(addr)

    def update_range(self, addr):
        r = REG_BY_ADDR.get(addr)
        if not r:
            self.lbl_range.setText("0–65535 (generic)")
            self.val_edit.setRange(0, 65535)
            self.btn_write.setEnabled(True)
            return

        self.val_edit.setRange(r["min"], r["max"])
        self.lbl_range.setText(f"{r['min']} – {r['max']}")
        self.btn_write.setEnabled(r["writable"])

    def write_reg(self):
        addr = self.addr_edit.value()
        value = self.val_edit.value()
        try:
            self.modbus.write_register(addr, value)
            QMessageBox.information(self, "OK", f"Written {value} to {addr}")
        except Exception as e:
            QMessageBox.warning(self, "Error", str(e))


# ----------------- Run app -----------------
def main():
    app = QApplication(sys.argv)
    win = MainWindow()
    win.resize(900, 600)
    win.show()
    sys.exit(app.exec_())


if __name__ == "__main__":
    main()
