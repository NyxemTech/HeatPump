import asyncio
import logging
from pymodbus.client import AsyncModbusSerialClient
from pymodbus.exceptions import ModbusException

# === Setup Logging === #
logging.basicConfig(filename="modbus_async.log", level=logging.INFO, format="%(asctime)s - %(levelname)s - %(message)s")

# === Modbus RTU Configuration === #
MODBUS_PORT = "/dev/ttyAMA2"  # Adjust based on your setup
MODBUS_BAUDRATE = 2400
MODBUS_PARITY = "E"  # Even Parity
MODBUS_STOPBITS = 1
MODBUS_BYTESIZE = 8
MODBUS_TIMEOUT = 1  # Timeout in seconds
SLAVE_ID = 145  # Modbus Device Address
REGISTER_ADDRESS = 0x0004  # Water Temperature Register
REGISTER_COUNT = 2  # 2 Registers (4 Bytes)
RETRY_COUNT = 3  # Number of retries

# === Function: Read Water Temperature === #
async def read_water_temperature(client):
    """Reads water temperature from the heat meter using async Modbus RTU."""
    for attempt in range(RETRY_COUNT):
        try:
            print(f"📡 Sending Modbus Request: ID={hex(SLAVE_ID)}, Address={hex(REGISTER_ADDRESS)}, Count={REGISTER_COUNT}")
            response = await client.read_holding_registers(address=REGISTER_ADDRESS, count=REGISTER_COUNT, slave=SLAVE_ID)

            if response.isError():
                print(f"⚠️ Error reading Modbus register {hex(REGISTER_ADDRESS)}. Attempt {attempt+1}/{RETRY_COUNT}")
                logging.error(f"⚠️ Error reading Modbus register {hex(REGISTER_ADDRESS)}")
                await asyncio.sleep(1)  # Wait before retrying
            else:
                # Convert received registers to a 32-bit integer (IEEE-754 Floating Point)
                raw_value = (response.registers[0] << 16) | response.registers[1]
                temperature = raw_value / 100  # Convert to decimal system (5300 = 53.00°C)
                print(f"🌡️ Water Temperature: {temperature:.2f}°C")
                logging.info(f"🌡️ Water Temperature: {temperature:.2f}°C")
                return temperature

        except ModbusException as e:
            print(f"❌ Modbus Exception: {e}")
            logging.error(f"❌ Modbus Exception: {e}")
            await asyncio.sleep(1)

    print("⚠️ Failed to read water temperature after multiple attempts.")
    return None

# === Main Async Function === #
async def main():
    """Main async function to manage connection and Modbus tasks."""
    async with AsyncModbusSerialClient(
        port=MODBUS_PORT,
        baudrate=MODBUS_BAUDRATE,
        parity=MODBUS_PARITY,
        stopbits=MODBUS_STOPBITS,
        bytesize=MODBUS_BYTESIZE,
        timeout=MODBUS_TIMEOUT
    ) as client:
        await read_water_temperature(client)

# === Run Async Code Properly === #
if __name__ == "__main__":
    asyncio.run(main())  # Ensures an event loop is created and runs the async function