#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
XHT Heat Meter RS-485 auto-scanner for /dev/ttyAMA3 (Modbus RTU)

- Tries baud rates: 2400 and 9600 (override with --bauds).
- Tries slave IDs: 0..254 (override with --addr-start/--addr-end).
- Auto-detects whether your client uses 'slave=' or 'unit=' (pymodbus 3.x vs 2.x).
- Uses RTU framer on 3.x when available; safe on 2.x (no framer kw).
- Filters client kwargs against ModbusSerialClient.__init__ signature to avoid
  "unexpected keyword" errors.

Install:
  pip install -U "pymodbus>=3,<4" pyserial
  # or, if you prefer v2:
  pip install -U "pymodbus<3" pyserial
"""

import argparse
import time
import inspect
from datetime import datetime

import pymodbus
from pymodbus.client import ModbusSerialClient
from pymodbus.exceptions import ModbusException

# -------- RTU framer detection (covering multiple 3.x layouts) --------
HAVE_FRAMER = False
FRAMER_ARG = None
try:
    from pymodbus import FramerType  # 3.5+
    FRAMER_ARG = FramerType.RTU
    HAVE_FRAMER = True
except Exception:
    try:
        from pymodbus.framer.rtu_framer import ModbusRtuFramer as _RTU
        FRAMER_ARG = _RTU
        HAVE_FRAMER = True
    except Exception:
        try:
            from pymodbus.framer.rtu import ModbusRtuFramer as _RTU
            FRAMER_ARG = _RTU
            HAVE_FRAMER = True
        except Exception:
            HAVE_FRAMER = False
            FRAMER_ARG = None

# Will be set at runtime after client creation
UNIT_KW = "unit"  # or "slave" on pymodbus 3.x


def _detect_unit_kw(client):
    """Return 'slave' if client methods want slave=; else 'unit'."""
    try:
        sig = inspect.signature(client.read_holding_registers)
        if "slave" in sig.parameters:
            return "slave"
    except Exception:
        pass
    return "unit"


# -------------------- helpers --------------------

def u32_from_regs(regs, swap_words=False):
    """Combine two 16-bit registers into unsigned 32-bit. swap_words=True flips word order."""
    if len(regs) != 2:
        raise ValueError("Need exactly 2 registers for u32")
    hi, lo = (regs[0] & 0xFFFF, regs[1] & 0xFFFF)
    if swap_words:
        hi, lo = lo, hi
    return (hi << 16) | lo


def _kw(unit):
    """Build the correct keyword dict for unit/slave."""
    return {UNIT_KW: unit}


def read_u32(client, unit, addr, swap_words=False):
    rr = client.read_holding_registers(address=addr, count=2, **_kw(unit))
    if hasattr(rr, "isError") and rr.isError():
        raise ModbusException(rr)
    return u32_from_regs(rr.registers, swap_words=swap_words)


def read_u16(client, unit, addr):
    rr = client.read_holding_registers(address=addr, count=1, **_kw(unit))
    if hasattr(rr, "isError") and rr.isError():
        raise ModbusException(rr)
    return rr.registers[0] & 0xFFFF


def read_time_5x16(client, unit, addr=0x0013):
    """Device time: Year, Month, Day, Hour, Minute (5×u16)."""
    rr = client.read_holding_registers(address=addr, count=5, **_kw(unit))
    if hasattr(rr, "isError") and rr.isError():
        raise ModbusException(rr)
    y, m, d, hh, mm = rr.registers
    try:
        return datetime(year=y, month=m, day=d, hour=hh, minute=mm)
    except ValueError:
        return None  # invalid/unset device time


def decode_faults(code_low_byte):
    """
    Fault bits (low byte):
      bit7: Empty pipe / air in pipe
      bit5: Return temp sensor fault
      bit4: Inlet temp sensor fault
      bit2: Battery undervoltage
    """
    faults = []
    if code_low_byte & (1 << 7):
        faults.append("Empty pipe / air in pipe")
    if code_low_byte & (1 << 5):
        faults.append("Return-temp sensor fault")
    if code_low_byte & (1 << 4):
        faults.append("Inlet-temp sensor fault")
    if code_low_byte & (1 << 2):
        faults.append("Battery undervoltage")
    return faults


def decode_comm_params(val_u16):
    """
    Comm param byte (low byte):
      high nibble = parity (1=None, 2=Even, 3=Odd)
      low  nibble = baud   (1=300, 2=600, 3=1200, 4=2400, 5=4800, 6=9600)
    """
    parity_map = {1: "None", 2: "Even", 3: "Odd"}
    baud_map = {1: 300, 2: 600, 3: 1200, 4: 2400, 5: 4800, 6: 9600}
    b = val_u16 & 0xFF
    parity_code = (b >> 4) & 0xF
    baud_code = b & 0xF
    return {
        "raw": val_u16,
        "parity": parity_map.get(parity_code, f"Unknown({parity_code})"),
        "baud": baud_map.get(baud_code, f"Unknown({baud_code})"),
    }


def read_all(client, unit, large_energy=False, swap32=False):
    """
    Read & scale the main block (addresses per XHT Modbus sheet):
      0x0000..1  Energy (small: 1/100 kWh; large: 1/100 MWh)
      0x0004..5  Inlet temp (1/100 °C)
      0x0006..7  Return temp (1/100 °C)
      0x0008..9  |ΔT| (1/100 °C)
      0x000A..B  Total flow (1/100 m³)
      0x000C..D  Flow rate (1/10000 m³/h)
      0x000E..F  Power (1/100 kW)
      0x0010     Fault code (u16; low byte contains bits)
      0x0011     Working hours (h)
      0x0013..17 Device time (Y,M,D,H,Min)
      0x0607     Device address
      0x0608     Comm params (parity/baud nibble)
    """
    sw = bool(swap32)

    # 32-bit quantities
    energy_raw = read_u32(client, unit, 0x0000, swap_words=sw)
    inlet_raw  = read_u32(client, unit, 0x0004, swap_words=sw)
    return_raw = read_u32(client, unit, 0x0006, swap_words=sw)
    dT_raw     = read_u32(client, unit, 0x0008, swap_words=sw)
    qsum_raw   = read_u32(client, unit, 0x000A, swap_words=sw)
    qdot_raw   = read_u32(client, unit, 0x000C, swap_words=sw)
    p_raw      = read_u32(client, unit, 0x000E, swap_words=sw)

    # 16-bit values
    fault_u16  = read_u16(client, unit, 0x0010)
    hours      = read_u16(client, unit, 0x0011)
    now_dt     = read_time_5x16(client, unit, 0x0013)
    addr_reg   = read_u16(client, unit, 0x0607)
    comm_reg   = read_u16(client, unit, 0x0608)

    # Scaling
    data = {}
    if large_energy:
        data["energy_MWh"] = energy_raw / 100.0
    else:
        data["energy_kWh"] = energy_raw / 100.0

    data["inlet_temp_C"]   = inlet_raw  / 100.0
    data["return_temp_C"]  = return_raw / 100.0
    data["deltaT_C"]       = dT_raw     / 100.0
    data["flow_total_m3"]  = qsum_raw   / 100.0
    data["flow_m3_per_h"]  = qdot_raw   / 10000.0
    data["power_kW"]       = p_raw      / 100.0
    data["work_hours_h"]   = hours

    # Faults
    low_byte = fault_u16 & 0xFF
    data["fault_code_u16"] = fault_u16
    data["faults"] = decode_faults(low_byte)

    # Address & comm params
    data["device_address"] = addr_reg
    data["comm_params"] = decode_comm_params(comm_reg)

    # Device time (if valid)
    data["device_time"] = now_dt.isoformat() if now_dt else None

    return data


# -------------------- scanning logic --------------------

def _filter_kwargs_for_ctor(kwargs):
    """Strip keys not accepted by ModbusSerialClient.__init__ to avoid TypeError."""
    try:
        sig = inspect.signature(ModbusSerialClient.__init__)
        allowed = set(sig.parameters.keys())
        allowed.discard("self")
        return {k: v for k, v in kwargs.items() if k in allowed}
    except Exception:
        return kwargs  # best effort


def make_client(port, baud, parity, bytesize, stopbits, timeout):
    # common kwargs
    kwargs = dict(
        port=port,
        baudrate=baud,
        bytesize=bytesize,
        parity=parity,    # "E" default
        stopbits=stopbits,
        timeout=timeout,
    )
    if HAVE_FRAMER and FRAMER_ARG is not None:
        kwargs["framer"] = FRAMER_ARG

    # remove any keys that your installed pymodbus doesn't accept
    kwargs = _filter_kwargs_for_ctor(kwargs)
    return ModbusSerialClient(**kwargs)


def probe_one(client, addr, swap32=False):
    """
    Minimal, fast probe that reads inlet temperature (0x0004..5).
    Returns (ok, celsius_float) where ok=True if the read looks sane.
    """
    try:
        rr = client.read_holding_registers(address=0x0004, count=2, **_kw(addr))
        # Some versions return None on comms failure
        if rr is None or (hasattr(rr, "isError") and rr.isError()):
            return (False, None)
        raw = u32_from_regs(rr.registers, swap_words=swap32)
        temp_c = raw / 100.0
        if -20.0 <= temp_c <= 130.0:
            return (True, temp_c)
        return (False, temp_c)
    except Exception:
        return (False, None)


def scan_and_read(args):
    print(f"pymodbus version: {getattr(pymodbus, '__version__', 'unknown')}")
    if HAVE_FRAMER and FRAMER_ARG is not None:
        print("Using RTU framer (3.x path).")
    else:
        print("No framer kw (2.x path, defaults to RTU).")

    bauds = [int(b.strip()) for b in args.bauds.split(",") if b.strip()]
    found = None  # (baud, addr)

    for baud in bauds:
        print(f"\n--- Trying baud {baud} {args.bytesize}{args.parity}{args.stopbits} ---")
        client = make_client(args.port, baud, args.parity, args.bytesize, args.stopbits, args.timeout)
        try:
            if not client.connect():
                print(f"  ! Could not open {args.port} at {baud}")
                continue

            # detect unit/slave keyword for this client
            global UNIT_KW
            UNIT_KW = _detect_unit_kw(client)
            print(f"  Using '{UNIT_KW}=' keyword.")

            # scan address range
            for addr in range(args.addr_start, args.addr_end + 1):
                ok, temp_c = probe_one(client, addr, swap32=args.swap32)
                if ok:
                    print(f"  >>> Found device at addr {addr} (baud {baud}) — inlet temp ~ {temp_c:.2f} °C")
                    found = (baud, addr)
                    break
                # light progress feedback every 16 addresses
                if (addr - args.addr_start) % 16 == 0 and addr != args.addr_start:
                    print(f"    ... up to addr {addr} no response")

            if found:
                data = read_all(client, found[1], large_energy=args.large_energy, swap32=args.swap32)
                ts = time.strftime("%Y-%m-%d %H:%M:%S")
                print(f"\n[{ts}] XHT Heat Meter ({UNIT_KW} {found[1]}, baud {found[0]})")
                for k, v in data.items():
                    print(f"  {k}: {v}")
                return 0
        finally:
            try:
                client.close()
            except Exception:
                pass

    print("\nNo device responded on the requested scan range/settings.")
    print("Tips: check A/B wiring, common GND, disable console on /dev/ttyAMA3, and try --swap32 or another parity (e.g. --parity N).")
    return 1


# -------------------- main --------------------

def main():
    ap = argparse.ArgumentParser(description="Auto-scan XHT Heat Meter (RS-485 on /dev/ttyAMA3)")
    ap.add_argument("--port", default="/dev/ttyAMA3,/dev/ttyAMA2")
    ap.add_argument("--bauds", default="2400,9600", help="Comma-separated baud list to try")
    ap.add_argument("--parity", default="E", choices=["N", "E", "O"], help="Serial parity (default E)")
    ap.add_argument("--stopbits", type=int, default=1)
    ap.add_argument("--bytesize", type=int, default=8)
    ap.add_argument("--timeout", type=float, default=0.4, help="Serial timeout (s) during scan")
    ap.add_argument("--addr-start", type=int, default=0, help="First slave address to try (inclusive)")
    ap.add_argument("--addr-end", type=int, default=254, help="Last slave address to try (inclusive)")
    ap.add_argument("--large-energy", action="store_true", help="Interpret energy as MWh (large-caliber meters)")
    ap.add_argument("--swap32", action="store_true", help="Swap 32-bit word order if values look wrong")
    args = ap.parse_args()

    exit(scan_and_read(args))


if __name__ == "__main__":
    main()
