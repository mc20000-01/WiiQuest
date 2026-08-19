# Wii Balance Board → Quest 3S controller bridge

Turns a Wii Fit Balance Board into a mapped stick/button input source for a
Quest 3S app you build. The PC-side Python bridge is now safe to run on
Windows, Linux, and macOS:

- **Linux** can use the real Balance Board through BlueZ/PyBluez classic
  Bluetooth L2CAP.
- **Windows/macOS** can run the same Python command in automatic demo mode so
  friends can test the Quest app and UDP wiring even though those OSes do not
  expose the board's classic L2CAP socket to normal Python.

```
[Balance Board] --Bluetooth--> [bridge/wbb_bridge.py on Linux]
                                        |
                                        |  UDP JSON, port 50123
                                        v
                          [WBB Quest Bridge app, on the Quest]
                          - shows live sensor values
                          - lets you map cells/lean to stick+buttons
                                        |
                                        |  UDP JSON, loopback port 50124
                                        v
                          [Your own Unity/Godot Quest app]
```

## Quick start

### 1. Run the Python bridge

```bash
python3 bridge/wbb_bridge.py <QUEST_IP_ADDRESS>
```

The bridge targets 60 Hz by default for low latency without wasting CPU. You
can tune it with `--hz 90` or `--hz 30`.

Useful options:

```bash
# Force hardware-free test data on any OS.
python3 bridge/wbb_bridge.py <QUEST_IP_ADDRESS> --demo

# Linux: skip Bluetooth discovery when you know the board MAC address.
python3 bridge/wbb_bridge.py <QUEST_IP_ADDRESS> --address XX:XX:XX:XX:XX:XX

# Use another UDP port.
python3 bridge/wbb_bridge.py <QUEST_IP_ADDRESS> --port 50123
```

Find your Quest's IP under Settings → Wi-Fi → your network → Advanced, or with
`adb shell ip -o -4 addr show wlan0` if you have adb set up.

### 2. Linux real-board setup

Linux real-board mode needs BlueZ/PyBluez and raw Bluetooth permissions:

```bash
python3 -m pip install -r requirements.txt
sudo setcap cap_net_raw+eip "$(readlink -f "$(command -v python3)")"
```

Open the Balance Board battery cover and press the red sync button right before
starting the bridge. If discovery is flaky, pass `--address` with the board's
Bluetooth MAC address.

### 3. Build the Quest APK on Linux

`build.sh` wraps the Gradle build and copies the newest APK to `dist/`:

```bash
./build.sh
```

By default it expects the Android project in `android/` and builds Debug. You
can override both:

```bash
ANDROID_DIR=/path/to/android/project BUILD_TYPE=Release ./build.sh
```

### 4. Install the APK and start streaming

`run.sh` installs the APK over adb, optionally launches the app, detects the
Quest IP, and then starts the Python bridge:

```bash
# Install dist/WiiQuest-Debug.apk, then start the Python bridge.
./run.sh

# Install a custom APK and launch a known package first.
APK=/path/to/app-debug.apk PACKAGE=com.example.wiiquest ./run.sh

# Pass bridge args after --, for example force demo mode.
./run.sh -- --demo
```

If IP detection fails, set it manually:

```bash
QUEST_IP=192.168.1.42 ./run.sh
```

## UDP frame format

The Python bridge sends compact JSON lines to `<QUEST_IP>:50123`:

```json
{"tl":18.2,"tr":17.9,"bl":16.7,"br":16.4,"lean_x":-0.01,"lean_y":0.04,"total_kg":69.2,"connected":true,"source":"wii-balance-board","ts":1787136000.0}
```

- `tl`, `tr`, `bl`, `br`: top-left, top-right, bottom-left, bottom-right cell
  weights in approximate kilograms.
- `lean_x`: -1 left to +1 right.
- `lean_y`: -1 back to +1 front.
- `connected`: `true` for real hardware, `false` for demo data.

## Why not a Quest-only APK?

The board speaks classic Bluetooth L2CAP. Android's public L2CAP APIs are for
Bluetooth LE channels, not the classic BR/EDR transport the board uses. Quest
also does not provide a stock, sideloaded-app API for system-wide controller or
OpenXR input injection. Routing the Balance Board through a Linux PC and sending
UDP to your own Quest app is the reliable path.

## Files

- `bridge/wbb_bridge.py` — cross-platform Python UDP bridge with Linux
  real-board mode and all-OS demo mode.
- `build.sh` — Linux helper to build a Gradle Android APK and copy it to
  `dist/WiiQuest-<BUILD_TYPE>.apk`.
- `run.sh` — adb install helper that starts the Python bridge after installing
  the APK.
- `requirements.txt` — optional Linux dependency for real Balance Board
  Bluetooth support.
