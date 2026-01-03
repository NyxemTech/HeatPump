import sys
import time
import threading
from pymodbus.client import ModbusSerialClient
from PyQt5.QtWidgets import QApplication, QWidget, QVBoxLayout, QPushButton, QTableWidget, QTableWidgetItem, QLabel, QLineEdit
from PyQt5.QtCore import pyqtSignal, Qt

class ZP_RS485_Reader(QWidget):
    update_display_signal = pyqtSignal(dict)

    def __init__(self):
        super().__init__()
        self.client = ModbusSerialClient(
            port='/dev/ttyAMA3',
            baudrate=2400,
            stopbits=1,
            parity='E',
            bytesize=8,
            timeout=2
        )
        self.client.connect()

        self.registers = {
            0x00: "Forward Total Heat (kWh)",
            0x04: "Forward Total Flow (m³)",
            0x08: "Inlet Water Temperature (°C)",
            0x0C: "Outlet Water Temperature (°C)",
            0x10: "Temperature Difference (°C)",
            0x14: "Instant Flow Rate (m³/h)",
            0x18: "Instant Heat Rate (kW)",
            0x1C: "Meter Time Year",
            0x1E: "Meter Time Month-Day",
            0x20: "Meter Time Hour-Min",
            0x22: "Working Hours (h)",
            0x26: "Error Code"
        }

        self.init_ui()

        self.update_display_signal.connect(self.update_table)

        self.running = True
        self.thread = threading.Thread(target=self.read_loop)
        self.thread.start()

    def init_ui(self):
        self.setWindowTitle("ZP Heat Meter RS485 Reader")
        self.resize(1024, 600)

        layout = QVBoxLayout()

        self.status_label = QLabel("Status: Connecting...")
        layout.addWidget(self.status_label)

        self.table = QTableWidget()
        self.table.setColumnCount(3)
        self.table.setHorizontalHeaderLabels(["Address", "Name", "Value"])
        layout.addWidget(self.table)

        self.write_input = QLineEdit()
        self.write_input.setPlaceholderText("Write register: address,value (example: 0x10,1)")
        layout.addWidget(self.write_input)

        self.write_button = QPushButton("Write Register")
        self.write_button.clicked.connect(self.write_register)
        layout.addWidget(self.write_button)

        self.setLayout(layout)

    def read_loop(self):
        while self.running:
            values = {}
            try:
                for addr in self.registers.keys():
                    rr = self.client.read_holding_registers(address=addr, count=2, slave=145)
                    if rr.isError():
                        values[addr] = "Error"
                    else:
                        # Read two registers and convert to float32
                        raw = rr.registers
                        value = ((raw[0] << 16) + raw[1]) / 100 if addr < 0x1C else (raw[0] << 16) + raw[1]
                        values[addr] = value
                self.update_display_signal.emit(values)
                self.status_label.setText("Status: Connected")
            except Exception as e:
                self.status_label.setText(f"Status: Disconnected - {e}")
            time.sleep(5)

    def update_table(self, values):
        self.table.setRowCount(len(self.registers))
        for idx, (addr, name) in enumerate(self.registers.items()):
            self.table.setItem(idx, 0, QTableWidgetItem(f"0x{addr:04X}"))
            self.table.setItem(idx, 1, QTableWidgetItem(name))
            value = values.get(addr, "-")
            self.table.setItem(idx, 2, QTableWidgetItem(str(value)))

    def write_register(self):
        try:
            text = self.write_input.text()
            address_str, value_str = text.split(',')
            address = int(address_str.strip(), 0)
            value = int(value_str.strip(), 0)
            self.client.write_register(address=address, value=value, slave=144)
        except Exception as e:
            self.status_label.setText(f"Write Error: {e}")

    def closeEvent(self, event):
        self.running = False
        self.thread.join()
        self.client.close()
        event.accept()

if __name__ == "__main__":
    app = QApplication(sys.argv)
    reader = ZP_RS485_Reader()
    reader.show()
    sys.exit(app.exec_())