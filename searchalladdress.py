import csv
import time
import signal
from pymodbus.client import ModbusSerialClient

# Define parameters
baudrates = [2400] #, 4800, 9600, 14400, 19200, 38400, 57600, 115200]
parities = ['E'] #, 'O', 'N']
slave_ids = range(0, 255)
addresses = [
    0x00, 0x01, 0x02, 0x03, 0x04,
    0x10, 0x11, 0x12, 0x13,
    0x80, 0x81, 0x82, 0x83  ##128-131 in hex
]

# Setup graceful exit
stop_program = False

def signal_handler(sig, frame):
    global stop_program
    print("\nCtrl+C detected, stopping scan...")
    stop_program = True

signal.signal(signal.SIGINT, signal_handler)

# Open CSV for results
with open('find.csv', mode='w', newline='') as file:
    writer = csv.writer(file)
    writer.writerow(['Baudrate', 'Parity', 'SlaveID', 'Address', 'Value'])

    try_count = 0

    for slave_id in slave_ids:
        if stop_program:
            break
        print(f"Scanning Slave ID: {slave_id}")

        for baudrate in baudrates:
            if stop_program:
                break

            for parity in parities:
                if stop_program:
                    break

                print(f"  Trying baudrate {baudrate}, parity {parity}, slave {slave_id}")

                client = ModbusSerialClient(
                    port='/dev/ttySC0',
                    baudrate=baudrate,
                    timeout=1,
                    stopbits=1,
                    parity=parity,
                    bytesize=8
                )

                if not client.connect():
                    print("    Failed to connect.")
                    continue

                for address in addresses:
                    if stop_program:
                        break
                    try:
                        try_count += 1
                        print(f"    Trying address {hex(address)} (Try #{try_count})")
                        rr = client.read_holding_registers(address=address, count=1, slave=slave_id)
                        if rr and not rr.isError():
                            value = rr.registers[0]
                            print(f"    Found data! Address {hex(address)} = {value}")
                            writer.writerow([baudrate, parity, slave_id, hex(address), value])
                        else:
                            time.sleep(0.1)
                    except Exception as e:
                        print(f"    Exception: {e}")
                        time.sleep(0.1)

                client.close()

print("Scan finished!")
print(f"Total tries: {try_count}")
