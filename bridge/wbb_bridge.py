#!/usr/bin/env python3
"""
bridge/wbb_bridge.py — Wii Balance Board -> UDP bridge (Linux / BlueZ)

Connects to a Wii Fit Balance Board over raw Bluetooth L2CAP (the same
protocol your board already speaks — PSM 0x11 control / 0x13 data) using
Python's built-in AF_BLUETOOTH socket support (no pybluez dependency,
Linux only). Streams each mass reading as a UDP/JSON packet to your
Quest headset so a receiver app on the headset can turn it into
controller input.

Requirements:
  - Linux with BlueZ (you're on Arch, so this is native).
  - Run as root, OR grant the interpreter raw-socket capability once:
        sudo setcap cap_net_raw+eip $(readlink -f $(which python3))
  - The board must be awake: open the battery cover, press the red
    SYNC button. The light will blink while it's discoverable.

Usage:
  python3 bridge/wbb_bridge.py <quest_ip> [--port 50123] [--mac AA:BB:CC:DD:EE:FF]

If --mac is omitted, the script tries to discover the board via
`bluetoothctl` (press the red sync button right before running it).

Packet format (UDP, one JSON object per line):
  {"seq": 123, "t": 1737400000.123,
   "top_left": 12.3, "top_right": 11.9,
   "bottom_left": 30.1, "bottom_right": 29.8}
"""
import argparse
import json
import socket
import subprocess
import sys
import time

BLUETOOTH_NAME = "Nintendo RVL-WBC-01"
PSM_CONTROL = 0x11
PSM_DATA = 0x13

COMMAND_LIGHT = b"\x11"
COMMAND_REPORTING = b"\x12"
COMMAND_REQUEST_STATUS = b"\x15"
COMMAND_REGISTER = b"\x16"
COMMAND_READ_REGISTER = b"\x17"
INPUT_STATUS = 0x20
INPUT_READ_DATA = 0x21
EXTENSION_8BYTES = 0x32
CONTINUOUS_REPORTING = b"\x04"

TOP_RIGHT, BOTTOM_RIGHT, TOP_LEFT, BOTTOM_LEFT = 0, 1, 2, 3


def b2i(b):
    return int.from_bytes(b, "big")


def discover(timeout=8):
    """Best-effort scan for a Balance Board using bluetoothctl. Press the
    red sync button under the battery cover right before calling this."""
    print(f"Scanning for '{BLUETOOTH_NAME}' for {timeout}s — "
          f"press the red sync button on the board now...")
    try:
        subprocess.run(
            ["bluetoothctl", "--timeout", str(timeout), "scan", "on"],
            capture_output=True, text=True,
        )
        out = subprocess.run(
            ["bluetoothctl", "devices"], capture_output=True, text=True
        ).stdout
    except FileNotFoundError:
        print("bluetoothctl not found. Install bluez-utils, or pass --mac directly.")
        return None
    for line in out.splitlines():
        if BLUETOOTH_NAME in line:
            # line format: "Device AA:BB:CC:DD:EE:FF Nintendo RVL-WBC-01"
            parts = line.split()
            if len(parts) >= 2:
                return parts[1]
    return None


class WiiboardBridge:
    def __init__(self, mac_address, target_ip, target_port):
        self.mac = mac_address
        self.calibration = [[1e4] * 4] * 3
        self.calibration_requested = False

        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        self.target = (target_ip, target_port)

        self.control = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
        )
        self.data = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
        )

    def connect(self):
        print(f"Connecting to {self.mac} ...")
        self.control.connect((self.mac, PSM_CONTROL))
        self.data.connect((self.mac, PSM_DATA))
        print("Connected. Requesting calibration data...")
        self.send(COMMAND_READ_REGISTER, b"\x04\xA4\x00\x24\x00\x18")
        self.calibration_requested = True
        self.send(COMMAND_REGISTER, b"\x04\xA4\x00\x40\x00")
        self.status()
        self.light(False)

    def send(self, *parts):
        self.control.send(b"\x52" + b"".join(parts))

    def reporting(self):
        self.send(COMMAND_REPORTING, CONTINUOUS_REPORTING, EXTENSION_8BYTES)

    def light(self, on):
        self.send(COMMAND_LIGHT, b"\x10" if on else b"\x00")

    def status(self):
        self.send(COMMAND_REQUEST_STATUS, b"\x00")

    def calc_mass(self, raw, pos):
        cal = self.calibration
        if raw < cal[0][pos]:
            return 0.0
        elif raw < cal[1][pos]:
            return 17 * ((raw - cal[0][pos]) / float(cal[1][pos] - cal[0][pos]))
        else:
            return 17 + 17 * ((raw - cal[1][pos]) / float(cal[2][pos] - cal[1][pos]))

    def get_mass(self, payload):
        return {
            "top_right": self.calc_mass(b2i(payload[0:2]), TOP_RIGHT),
            "bottom_right": self.calc_mass(b2i(payload[2:4]), BOTTOM_RIGHT),
            "top_left": self.calc_mass(b2i(payload[4:6]), TOP_LEFT),
            "bottom_left": self.calc_mass(b2i(payload[6:8]), BOTTOM_LEFT),
        }

    def loop(self):
        self.connect()
        seq = 0
        print(f"Streaming to {self.target[0]}:{self.target[1]} — step on the board.")
        while True:
            pkt = self.data.recv(64)
            if len(pkt) < 2:
                continue
            input_type = pkt[1]
            if input_type == INPUT_STATUS:
                # Must re-set reporting mode after every status report
                self.reporting()
                self.light(True)
            elif input_type == INPUT_READ_DATA:
                if self.calibration_requested:
                    length = pkt[4] // 16 + 1
                    payload = pkt[7 : 7 + length]
                    cal = lambda d: [b2i(d[j : j + 2]) for j in (0, 2, 4, 6)]
                    if length == 16:  # first calibration packet
                        self.calibration = [cal(payload[0:8]), cal(payload[8:16]), [1e4] * 4]
                    elif length < 16:  # second calibration packet
                        self.calibration[2] = cal(payload[0:8])
                        self.calibration_requested = False
                        print("Board calibrated:", self.calibration)
            elif input_type == EXTENSION_8BYTES:
                mass = self.get_mass(pkt[4:12])
                seq += 1
                msg = json.dumps({"seq": seq, "t": time.time(), **mass})
                self.udp.sendto(msg.encode(), self.target)

    def close(self):
        for s in (self.control, self.data, self.udp):
            try:
                s.close()
            except OSError:
                pass


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("quest_ip", help="IP address of your Quest 3S on the local network")
    ap.add_argument("--port", type=int, default=50123, help="UDP port the Quest app listens on")
    ap.add_argument("--mac", help="Balance board MAC address (skips discovery)")
    args = ap.parse_args()

    mac = args.mac or discover()
    if not mac:
        print("No balance board found. Press the red sync button under the "
              "battery cover and try again, or pass --mac AA:BB:CC:DD:EE:FF")
        sys.exit(1)

    bridge = WiiboardBridge(mac, args.quest_ip, args.port)
    try:
        bridge.loop()
    except KeyboardInterrupt:
        print("\nStopping.")
    except PermissionError:
        print("Permission denied opening a raw Bluetooth socket.\n"
              "Run as root, or once: sudo setcap cap_net_raw+eip "
              f"{sys.executable}")
    finally:
        bridge.close()


if __name__ == "__main__":
    main()
