#!/usr/bin/env python3
# JSY-MK-354 reader (3-phase 4-wire)
# Requires: pip install pymodbus pyserial
import time
from pymodbus.client import ModbusSerialClient

# ----- Serial / Modbus config (adjust as needed) -----
PORT       = "/dev/ttyAMA2"    # e.g. "/dev/ttyAMA2" or "/dev/ttyUSB0"
BAUDRATE   = 9600              # default per manual
PARITY     = "N"
STOPBITS   = 1
BYTESIZE   = 8
TIMEOUT_S  = 1.0
UNIT_ID    = 1                 # default address per manual

POLL_SEC   = 3.0               # read interval

# ----- Helpers -----
def u32_from_hi_lo(hi: int, lo: int) -> int:
    """Combine two 16-bit registers (hi, lo) into one unsigned 32-bit."""
    return ((hi & 0xFFFF) << 16) | (lo & 0xFFFF)

def read_regs(client, addr: int, count: int, unit: int):
    """Read holding registers with graceful failure (returns list or None)."""
    try:
        rr = client.read_holding_registers(address=addr, count=count, slave=unit)
        if rr is None or rr.isError():
            return None
        return rr.registers
    except Exception:
        return None

def main():
    client = ModbusSerialClient(
        port=PORT,
        baudrate=BAUDRATE,
        parity=PARITY,
        stopbits=STOPBITS,
        bytesize=BYTESIZE,
        timeout=TIMEOUT_S,
    )
    if not client.connect():
        print(f"[ERROR] Cannot open {PORT} @ {BAUDRATE} 8{PARITY}{STOPBITS}")
        return
    print(f"[OK] Connected {PORT} @ {BAUDRATE} 8{PARITY}{STOPBITS}, unit={UNIT_ID}")

    try:
        while True:
            # ---- Block 1: 0x0100..0x0119 (26 regs): V/A/W per phase, totals, freq, PFs ----
            regs1 = read_regs(client, 0x0100, 26, UNIT_ID)
            if not regs1:
                print("[WARN] No data (block1). Skipping this cycle.")
                time.sleep(POLL_SEC)
                continue

            # Map (per manual Table 1)
            Va = regs1[0]  / 100.0    # 0x0100 V
            Vb = regs1[1]  / 100.0    # 0x0101 V
            Vc = regs1[2]  / 100.0    # 0x0102 V

            Ia = regs1[3]  / 100.0    # 0x0103 A
            Ib = regs1[4]  / 100.0    # 0x0104 A
            Ic = regs1[5]  / 100.0    # 0x0105 A

            Pa_w = regs1[6]           # 0x0106 W (phase A active power)
            Pb_w = regs1[7]           # 0x0107 W
            Pc_w = regs1[8]           # 0x0108 W
            Ptot_w = u32_from_hi_lo(regs1[9], regs1[10])   # 0x0109 hi, 0x010A lo

            # Reactive, apparent totals if you need them later:
            Qtot_var = u32_from_hi_lo(regs1[14], regs1[15])   # 0x010E..0x010F
            Stot_va  = u32_from_hi_lo(regs1[19], regs1[20])   # 0x0113..0x0114

            Freq_hz = regs1[21] / 100.0   # 0x0115
            PFa     = regs1[22] / 1000.0  # 0x0116
            PFb     = regs1[23] / 1000.0  # 0x0117
            PFc     = regs1[24] / 1000.0  # 0x0118
            PFtot   = regs1[25] / 1000.0  # 0x0119
            # (Scaling/addresses per datasheet.)  # :contentReference[oaicite:2]{index=2}

            # ---- Block 2: energies (pick what you need). Example: totals 0x0120..0x0121 ----
            regs2 = read_regs(client, 0x0120, 2, UNIT_ID)  # total active energy kWh hi/lo
            if regs2:
                Etot_wh = u32_from_hi_lo(regs2[0], regs2[1])   # raw *before* /100
                Etot_kwh = Etot_wh / 100.0                    # kWh
            else:
                Etot_kwh = None

            # Pretty print
            print(
                f"V: {Va:.2f}/{Vb:.2f}/{Vc:.2f} V | "
                f"I: {Ia:.2f}/{Ib:.2f}/{Ic:.2f} A | "
                f"P: A={Pa_w} W, B={Pb_w} W, C={Pc_w} W, Tot={Ptot_w} W "
                f"({Ptot_w/1000:.3f} kW) | PF: A={PFa:.3f}, B={PFb:.3f}, C={PFc:.3f}, Tot={PFtot:.3f} | "
                f"F={Freq_hz:.2f} Hz | "
                + (f"E_tot={Etot_kwh:.2f} kWh" if Etot_kwh is not None else "E_tot=?")
            )

            time.sleep(POLL_SEC)

    except KeyboardInterrupt:
        print("\n[STOP] Keyboard interrupt.")
    finally:
        try:
            client.close()
        except Exception:
            pass

if __name__ == "__main__":
    main()
