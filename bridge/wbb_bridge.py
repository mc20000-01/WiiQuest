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
from abc import ABC, abstractmethod


class WiiboardProtocol:
    """Wii Balance Board protocol helpers and packet decoder."""

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

    def __init__(self):
        self.calibration = [[1e4] * 4 for _ in range(3)]
        self.calibration_requested = False

    @staticmethod
    def b2i(data):
        return int.from_bytes(data, "big")

    def init_commands(self):
        self.calibration_requested = True
        return [
            (self.COMMAND_READ_REGISTER, b"\x04\xA4\x00\x24\x00\x18"),
            (self.COMMAND_REGISTER, b"\x04\xA4\x00\x40\x00"),
            (self.COMMAND_REQUEST_STATUS, b"\x00"),
            (self.COMMAND_LIGHT, b"\x00"),
        ]

    def reporting_command(self):
        return (
            self.COMMAND_REPORTING,
            self.CONTINUOUS_REPORTING,
            bytes([self.EXTENSION_8BYTES]),
        )

    def light_command(self, on):
        return self.COMMAND_LIGHT, b"\x10" if on else b"\x00"

    def calc_mass(self, raw, pos):
        cal = self.calibration
        if raw < cal[0][pos]:
            return 0.0
        if raw < cal[1][pos]:
            return 17 * ((raw - cal[0][pos]) / float(cal[1][pos] - cal[0][pos]))
        return 17 + 17 * ((raw - cal[1][pos]) / float(cal[2][pos] - cal[1][pos]))

    def get_mass(self, payload):
        return {
            "top_right": self.calc_mass(self.b2i(payload[0:2]), self.TOP_RIGHT),
            "bottom_right": self.calc_mass(self.b2i(payload[2:4]), self.BOTTOM_RIGHT),
            "top_left": self.calc_mass(self.b2i(payload[4:6]), self.TOP_LEFT),
            "bottom_left": self.calc_mass(self.b2i(payload[6:8]), self.BOTTOM_LEFT),
        }

    def _parse_calibration_values(self, data):
        return [self.b2i(data[j : j + 2]) for j in (0, 2, 4, 6)]

    def parse_calibration_packet(self, pkt):
        length = pkt[4] // 16 + 1
        payload = pkt[7 : 7 + length]
        if length == 16:
            self.calibration = [
                self._parse_calibration_values(payload[0:8]),
                self._parse_calibration_values(payload[8:16]),
                [1e4] * 4,
            ]
        elif length < 16:
            self.calibration[2] = self._parse_calibration_values(payload[0:8])
            self.calibration_requested = False
            return self.calibration
        return None

    def decode_packet(self, pkt):
        """Return protocol events decoded from a raw data-channel packet."""
        if len(pkt) < 2:
            return []

        input_type = pkt[1]
        if input_type == self.INPUT_STATUS:
            return [{"type": "status"}]
        if input_type == self.INPUT_READ_DATA and self.calibration_requested:
            calibration = self.parse_calibration_packet(pkt)
            if calibration is not None:
                return [{"type": "calibrated", "calibration": calibration}]
        if input_type == self.EXTENSION_8BYTES:
            return [{"type": "mass", "mass": self.get_mass(pkt[4:12])}]
        return []


class UdpPublisher:
    """Formats Wii Balance Board readings as JSON and publishes them over UDP."""

    def __init__(self, target_ip, target_port):
        self.target = (target_ip, target_port)
        self.seq = 0
        self.udp = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)

    def format_packet(self, mass):
        self.seq += 1
        return json.dumps({"seq": self.seq, "t": time.time(), **mass})

    def publish(self, mass):
        msg = self.format_packet(mass)
        self.udp.sendto(msg.encode(), self.target)

    def close(self):
        try:
            self.udp.close()
        except OSError:
            pass


class BluetoothBackend(ABC):
    """Interface for Balance Board Bluetooth transport implementations."""

    @abstractmethod
    def discover(self):
        pass

    @abstractmethod
    def connect(self, mac):
        pass

    @abstractmethod
    def send_control(self, data):
        pass

    @abstractmethod
    def recv_data(self):
        pass

    @abstractmethod
    def close(self):
        pass


class LinuxBlueZBackend(BluetoothBackend):
    """Linux/BlueZ L2CAP socket backend."""

    def __init__(self, timeout=8):
        self.timeout = timeout
        self.control = None
        self.data = None

    def discover(self):
        """Best-effort scan for a Balance Board using bluetoothctl."""
        print(f"Scanning for '{WiiboardProtocol.BLUETOOTH_NAME}' for {self.timeout}s — "
              "press the red sync button on the board now...")
        try:
            subprocess.run(
                ["bluetoothctl", "--timeout", str(self.timeout), "scan", "on"],
                capture_output=True, text=True,
            )
            out = subprocess.run(
                ["bluetoothctl", "devices"], capture_output=True, text=True
            ).stdout
        except FileNotFoundError:
            print("bluetoothctl not found. Install bluez-utils, or pass --mac directly.")
            return None
        for line in out.splitlines():
            if WiiboardProtocol.BLUETOOTH_NAME in line:
                parts = line.split()
                if len(parts) >= 2:
                    return parts[1]
        return None

    def connect(self, mac):
        self.control = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
        )
        self.data = socket.socket(
            socket.AF_BLUETOOTH, socket.SOCK_SEQPACKET, socket.BTPROTO_L2CAP
        )
        self.control.connect((mac, WiiboardProtocol.PSM_CONTROL))
        self.data.connect((mac, WiiboardProtocol.PSM_DATA))

    def send_control(self, data):
        self.control.send(b"\x52" + data)

    def recv_data(self):
        return self.data.recv(64)

    def close(self):
        for s in (self.control, self.data):
            if s is None:
                continue
            try:
                s.close()
            except OSError:
                pass


class WiiboardBridge:
    def __init__(self, mac_address, publisher, backend, protocol=None):
        self.mac = mac_address
        self.publisher = publisher
        self.backend = backend
        self.protocol = protocol or WiiboardProtocol()

    def connect(self):
        print(f"Connecting to {self.mac} ...")
        self.backend.connect(self.mac)
        print("Connected. Requesting calibration data...")
        for command in self.protocol.init_commands():
            self.send(*command)

    def send(self, *parts):
        self.backend.send_control(b"".join(parts))

    def reporting(self):
        self.send(*self.protocol.reporting_command())

    def light(self, on):
        self.send(*self.protocol.light_command(on))

    def loop(self):
        self.connect()
        print(f"Streaming to {self.publisher.target[0]}:{self.publisher.target[1]} — step on the board.")
        while True:
            for event in self.protocol.decode_packet(self.backend.recv_data()):
                if event["type"] == "status":
                    self.reporting()
                    self.light(True)
                elif event["type"] == "calibrated":
                    print("Board calibrated:", event["calibration"])
                elif event["type"] == "mass":
                    self.publisher.publish(event["mass"])

    def close(self):
        self.backend.close()
        self.publisher.close()


def build_backend(name):
    if name == "linux-bluez":
        return LinuxBlueZBackend()
    raise ValueError(f"Unsupported backend: {name}")


def main():
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("quest_ip", help="IP address of your Quest 3S on the local network")
    ap.add_argument("--port", type=int, default=50123, help="UDP port the Quest app listens on")
    ap.add_argument("--mac", help="Balance board MAC address (skips discovery)")
    ap.add_argument(
        "--backend",
        choices=("linux-bluez",),
        default="linux-bluez",
        help="Bluetooth backend to use",
    )
    args = ap.parse_args()

    backend = build_backend(args.backend)
    mac = args.mac or backend.discover()
    if not mac:
        print("No balance board found. Press the red sync button under the "
              "battery cover and try again, or pass --mac AA:BB:CC:DD:EE:FF")
        sys.exit(1)

    bridge = WiiboardBridge(mac, UdpPublisher(args.quest_ip, args.port), backend)
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
