import serial

PORT = "/dev/ttySC0"   # or your USB, e.g. "/dev/ttyUSB0"
BAUD = 9600            # try 9600 first
ser = serial.Serial(PORT, BAUD, bytesize=8, parity='N', stopbits=1, timeout=0.5)

print("Listening on", PORT)
while True:
    data = ser.read(100)
    if data:
        print(data.hex(' '))
    else:
        print(".", end="", flush=True)