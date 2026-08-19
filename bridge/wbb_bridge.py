#!/usr/bin/env python3
"""Cross-platform Wii Balance Board UDP bridge.

Linux can talk to the board through BlueZ/PyBluez L2CAP. Windows and macOS do
not expose the classic Bluetooth L2CAP socket this board needs to normal Python,
so this script still runs there in demo mode for testing the Quest app/network.
"""
from __future__ import annotations

import argparse
import json
import math
import os
import platform
import random
import socket
import sys
import time
from dataclasses import dataclass, asdict
from typing import Optional

DEFAULT_PORT = 50123
DISCOVER_TIMEOUT = 8


@dataclass(slots=True)
class BoardFrame:
    tl: float
    tr: float
    bl: float
    br: float
    lean_x: float
    lean_y: float
    total_kg: float
    connected: bool
    source: str
    ts: float


def _normalise(numerator: float, denominator: float) -> float:
    if abs(denominator) < 0.001:
        return 0.0
    return max(-1.0, min(1.0, numerator / denominator))


def frame_from_cells(tl: float, tr: float, bl: float, br: float, *, connected: bool, source: str) -> BoardFrame:
    total = max(0.0, tl + tr + bl + br)
    left = tl + bl
    right = tr + br
    front = tl + tr
    back = bl + br
    return BoardFrame(
        tl=round(tl, 3),
        tr=round(tr, 3),
        bl=round(bl, 3),
        br=round(br, 3),
        lean_x=round(_normalise(right - left, total), 4),
        lean_y=round(_normalise(front - back, total), 4),
        total_kg=round(total, 3),
        connected=connected,
        source=source,
        ts=time.time(),
    )


class DemoBoard:
    """Fast fake board stream that works on every OS for app testing."""

    def __init__(self) -> None:
        self.started = time.monotonic()

    def read_frame(self) -> BoardFrame:
        t = time.monotonic() - self.started
        total = 52.0 + math.sin(t * 0.8) * 8.0
        lean_x = math.sin(t * 1.4) * 0.55
        lean_y = math.cos(t * 1.1) * 0.45
        left = total * (1.0 - lean_x) / 2.0
        right = total - left
        front = total * (1.0 + lean_y) / 2.0
        back = total - front
        tl = (left + front) / 2.0 + random.uniform(-0.15, 0.15)
        tr = (right + front) / 2.0 + random.uniform(-0.15, 0.15)
        bl = (left + back) / 2.0 + random.uniform(-0.15, 0.15)
        br = (right + back) / 2.0 + random.uniform(-0.15, 0.15)
        return frame_from_cells(tl, tr, bl, br, connected=False, source="demo")


class LinuxWiiBalanceBoard:
    """Minimal BlueZ/PyBluez reader for the Wii Balance Board on Linux."""

    CONTROL_PSM = 0x11
    DATA_PSM = 0x13

    def __init__(self, address: str, timeout: float) -> None:
        if platform.system() != "Linux":
            raise RuntimeError("Real Wii Balance Board Bluetooth mode is Linux/BlueZ only; use --demo elsewhere.")
        try:
            import bluetooth  # type: ignore
        except ImportError as exc:
            raise RuntimeError("Install PyBluez on Linux first: python3 -m pip install pybluez") from exc
        self.bluetooth = bluetooth
        self.address = address or self._discover(timeout)
        self.control: Optional[socket.socket] = None
        self.data: Optional[socket.socket] = None
        self.zero = [0, 0, 0, 0]

    def _discover(self, timeout: float) -> str:
        print("Press the red SYNC button on the Balance Board now...", flush=True)
        devices = self.bluetooth.discover_devices(duration=int(timeout), lookup_names=True)
        for addr, name in devices:
            if "balance" in name.lower() or "nintendo" in name.lower():
                print(f"Found {name} at {addr}", flush=True)
                return addr
        raise RuntimeError("Could not find a Balance Board. Pass --address XX:XX:XX:XX:XX:XX if discovery fails.")

    def connect(self) -> None:
        l2cap = self.bluetooth.L2CAP
        self.control = self.bluetooth.BluetoothSocket(l2cap)
        self.data = self.bluetooth.BluetoothSocket(l2cap)
        self.control.connect((self.address, self.CONTROL_PSM))
        self.data.connect((self.address, self.DATA_PSM))
        self.data.settimeout(1.0)
        self._send(0x12, bytes([0x00, 0x32]))  # data reporting mode: extension bytes
        time.sleep(0.05)
        print(f"Connected to Wii Balance Board at {self.address}", flush=True)

    def _send(self, report: int, payload: bytes) -> None:
        if self.control is None:
            raise RuntimeError("Board is not connected")
        self.control.send(bytes([0x52, report]) + payload)

    def read_frame(self) -> BoardFrame:
        if self.data is None:
            self.connect()
        assert self.data is not None
        packet = self.data.recv(32)
        # Extension reports normally contain four big-endian 16-bit sensor values
        # near the end of the packet. This keeps parsing lightweight and tolerant
        # across common report variants.
        if len(packet) < 11:
            raise RuntimeError(f"Short Balance Board packet: {packet!r}")
        raw = [int.from_bytes(packet[i : i + 2], "big") for i in range(len(packet) - 8, len(packet), 2)]
        cells = [max(0.0, (value - base) / 100.0) for value, base in zip(raw, self.zero)]
        return frame_from_cells(cells[0], cells[1], cells[2], cells[3], connected=True, source="wii-balance-board")


def make_board(args: argparse.Namespace):
    if args.demo or platform.system() != "Linux":
        if not args.demo:
            print(f"{platform.system()} cannot use real board L2CAP from Python; starting demo stream.", file=sys.stderr)
        return DemoBoard()
    return LinuxWiiBalanceBoard(args.address, args.discover_timeout)


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Stream Wii Balance Board frames to a Quest/Android app over UDP.")
    parser.add_argument("quest_ip", help="Quest/Android device IP address")
    parser.add_argument("--port", type=int, default=int(os.environ.get("WIIQUEST_PORT", DEFAULT_PORT)))
    parser.add_argument("--hz", type=float, default=float(os.environ.get("WIIQUEST_HZ", 60)), help="Send rate; 60 is low-latency and light on CPU")
    parser.add_argument("--address", default=os.environ.get("WIIQUEST_BOARD_ADDRESS", ""), help="Bluetooth MAC address for Linux real-board mode")
    parser.add_argument("--discover-timeout", type=float, default=DISCOVER_TIMEOUT)
    parser.add_argument("--demo", action="store_true", help="Run without Bluetooth hardware; works on Windows, Linux, and macOS")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    delay = 1.0 / max(1.0, args.hz)
    sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
    target = (args.quest_ip, args.port)
    board = make_board(args)
    print(f"Streaming UDP JSON to {target[0]}:{target[1]} at {1 / delay:.0f} Hz", flush=True)
    while True:
        start = time.perf_counter()
        frame = board.read_frame()
        sock.sendto((json.dumps(asdict(frame), separators=(",", ":")) + "\n").encode("utf-8"), target)
        elapsed = time.perf_counter() - start
        if elapsed < delay:
            time.sleep(delay - elapsed)


if __name__ == "__main__":
    try:
        raise SystemExit(main())
    except KeyboardInterrupt:
        print("\nStopped.")
