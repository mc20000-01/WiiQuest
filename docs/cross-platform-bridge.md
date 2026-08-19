# Cross-platform Balance Board bridge options

WiiQuest currently treats the Wii Balance Board as a Bluetooth device that is
connected by a desktop or single-board-computer bridge and republished as UDP
JSON for the Quest receiver. The bridge boundary is intentionally small: a
platform-specific process only needs to discover the board, read calibrated
mass values, and emit the same packet shape used by the Linux bridge.

## Supported and investigated bridge modes

### Linux: `LinuxBlueZBackend`

Linux is the currently supported host mode. The existing bridge uses BlueZ via
Python's `AF_BLUETOOTH` L2CAP sockets and scans with `bluetoothctl` when a MAC
address is not supplied. This is the reference implementation for packet
format, calibration flow, and runtime behavior.

Recommended use:

```bash
python3 bridge/wbb_bridge.py <quest_ip> [--port 50123] [--mac AA:BB:CC:DD:EE:FF]
```

Notes:

- Requires BlueZ and `bluetoothctl` for automatic discovery.
- Requires root or `cap_net_raw` on the Python interpreter to open raw
  Bluetooth sockets.
- The user must press the Balance Board's red SYNC button during discovery.
- Expected to be the most reliable direct-to-board desktop option because it
  uses the board's native classic Bluetooth L2CAP channels directly.

### Windows: native helper investigation

Windows support should be implemented as a small native helper process rather
than by extending the Python L2CAP implementation directly. The helper can keep
all Windows Bluetooth/HID details out of the Quest-facing protocol and expose
readings to the Python or app layer using one of these process boundaries:

- newline-delimited JSON on `stdout`, consumed by a Python wrapper;
- UDP packets matching the Linux bridge's JSON schema;
- a localhost TCP/WebSocket endpoint for diagnostics and richer tooling.

Candidate implementation routes:

1. Use Windows Bluetooth APIs to discover and connect to the board's classic
   Bluetooth services, then decode reports into the shared mass packet format.
2. Use Wiimote/HID libraries that already handle Nintendo controller discovery
   and report parsing, provided they can access Wii Balance Board extension
   data reliably on current Windows versions.
3. Evaluate a community Wii Balance Board library and wrap it in a minimal CLI
   that prints or serves calibrated sensor readings.

Reliability is expected to vary by Bluetooth adapter and driver stack. Windows
is a good candidate for a helper-based experimental mode, but it should not be
considered equivalent to the Linux BlueZ backend until discovery, reconnects,
and calibration are proven across multiple Windows releases and adapters.

### macOS: CoreBluetooth/IOBluetooth investigation

macOS support should also use a native helper process. The main investigation
question is whether current macOS Bluetooth frameworks expose enough classic
Bluetooth L2CAP/HID behavior for the Wii Balance Board without private APIs or
fragile pairing steps.

Candidate implementation routes:

1. Investigate IOBluetooth for classic Bluetooth device discovery and L2CAP/HID
   channel access.
2. Confirm whether CoreBluetooth is useful for this device class. Because the
   Balance Board is a classic Bluetooth accessory rather than Bluetooth Low
   Energy, CoreBluetooth may only help with nearby-device workflows if at all.
3. Wrap any working native implementation as a CLI or localhost service that
   emits the same JSON mass readings as the Linux bridge.

Expected reliability is unknown until a prototype validates discovery,
permissions, pairing behavior, and reconnects on supported macOS versions.

### Fallback: Linux SBC board-to-UDP bridge

For users on Windows, macOS, locked-down desktops, or unreliable Bluetooth
adapters, the recommended universal fallback is a small Linux single-board
computer such as a Raspberry Pi. The SBC runs the current Linux BlueZ bridge,
connects to the Balance Board over Bluetooth, and sends UDP packets to the
Quest over Wi-Fi.

This mode preserves one reliable Bluetooth implementation for all desktop
users. It also allows the desktop OS to be removed from the hardware path:
Windows and macOS users only need the Quest receiver and network connectivity,
while the SBC handles board discovery, calibration, and UDP publishing.

## Compatibility matrix

| OS / bridge host | Required permissions | Discovery method | Expected reliability |
| --- | --- | --- | --- |
| Linux desktop with `LinuxBlueZBackend` | Root or `cap_net_raw` for Python raw Bluetooth sockets; BlueZ installed | `bluetoothctl` scan while pressing the board's red SYNC button, or manual `--mac` | High; current reference path using native classic Bluetooth L2CAP |
| Windows native helper | Bluetooth permission/pairing as required by Windows; possible driver/library installation depending on helper | Native Windows Bluetooth device scan, HID/Wiimote library discovery, or helper-specific pairing flow | Medium to unknown; depends on adapter, driver stack, and helper maturity |
| macOS native helper | Bluetooth permission prompts; possible helper entitlement or user-approved pairing depending on implementation | IOBluetooth/CoreBluetooth investigation, native helper scan, or manual address/config entry | Unknown to medium; needs prototype validation for classic Bluetooth access and reconnect behavior |
| Linux SBC fallback, e.g. Raspberry Pi | Root or `cap_net_raw` on the SBC; BlueZ installed; Wi-Fi access to the Quest network | Same as Linux: `bluetoothctl` scan or manual MAC on the SBC | High once configured; isolates Bluetooth handling to the known Linux backend |

## Interoperability contract

Every bridge mode should converge on the same UDP payload so the Quest-side
receiver and Unity sample do not need OS-specific code:

```json
{"seq": 123, "t": 1737400000.123, "top_left": 12.3, "top_right": 11.9, "bottom_left": 30.1, "bottom_right": 29.8}
```

A platform helper may expose `stdout` or localhost first, but it should either
emit this UDP schema directly or be wrapped by a thin adapter that does.
