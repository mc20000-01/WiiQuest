# Wii Balance Board → Quest 3S controller bridge

Turns a Wii Fit Balance Board into a mapped stick/button input source for a
Quest 3S app you build. Two pieces, because the Quest's stock Android build
can't open the raw Bluetooth socket the board needs (see "Why two pieces?"
below):

```
[Balance Board] --Bluetooth--> [bridge/wbb_bridge.py on your Arch PC]
                                        |
                                        |  UDP (JSON), port 50123
                                        v
                          [WBB Quest Bridge app, on the Quest]
                          - shows live sensor values
                          - lets you map cells/lean to stick+buttons
                                        |
                                        |  UDP (JSON), loopback port 50124
                                        v
                          [Your own Unity/Godot Quest app]
                          (see unity/WBBReceiver.cs for a starting point)
```

## 1. Run the bridge on your PC

```
# From the repository root:
# one-time, so you don't need sudo every run:
sudo setcap cap_net_raw+eip $(readlink -f $(which python3))

python3 bridge/wbb_bridge.py <QUEST_IP_ADDRESS>
```

Find your Quest's IP under Settings → Wi-Fi → (network) → Advanced, or via
`adb shell ip addr show wlan0` if you have adb set up. Open the balance
board's battery cover and press the red sync button right before running the
script — it needs to be discoverable. Once connected, step on the board and
you should see it start streaming.

Your PC and the Quest need to be on the same Wi-Fi network.

## 2. Build the Quest app

Open `android/` in Android Studio (Giraffe or newer), let it sync, then
either:

- Build → Build Bundle(s)/APK(s) → Build APK(s), or
- `./gradlew assembleDebug` from the `android/` directory once you have the
  Android SDK installed.

Sideload the resulting APK with SideQuest or `adb install`. Launch it, and
it'll immediately start listening on UDP port 50123 for the bridge.

## 3. Map the board to a controller

The app shows live values for all 4 cells plus two derived "lean" axes
(left/right, forward/back — these are the two you'll usually want for a
stick). Use the spinners to assign:

- **Left stick X/Y** — pick `Lean left/right` and `Lean forward/back` for a
  natural weight-shift joystick.
- **Buttons A/B/X/Y** — pick any cell (e.g. `Top-left cell`) to make a corner
  act as a stomp-to-press button, with a weight threshold in kg.

Hit **Save mapping**. From then on, the app republishes your mapped
stick/button state as JSON over loopback UDP (default port 50124) — that's
what `unity/WBBReceiver.cs` reads.

## 4. Wire it into your own Quest app

Drop `unity/WBBReceiver.cs` into a Unity Quest project, attach it to any
GameObject, and read `StickX`, `StickY`, `ButtonA`, etc. from your own
scripts. If you're using Godot or raw OpenXR instead of Unity, the wire
format is trivial — a JSON line like:

```json
{"stickX": 0.42, "stickY": -0.10, "a": false, "b": false, "x": true, "y": false}
```

on `127.0.0.1:50124` — port it to whatever language you're using in a few
lines.

## Why two pieces, and not one Quest-only APK?

The board only speaks classic Bluetooth L2CAP (the same thing your original
`wiiboard.py` script uses). Android's public API for opening L2CAP sockets
(`createL2capChannel`) is documented as **LE-only** — it explicitly does not
support the classic BR/EDR transport the board uses. This is also why every
prior Android app for this board (FitScales, WiiScale, etc.) either stopped
working when Google locked down the Bluetooth stack, or needed a rooted
phone with a custom native build. There's also no OS-level API on stock
Quest for a sideloaded app to inject into the system-wide controller/OpenXR
input pipeline — so even with a working Bluetooth connection, "replace my
Touch controllers everywhere" isn't achievable without root. Routing the
Bluetooth connection through your Linux PC (where raw L2CAP just works) and
feeding your *own* Quest app over the network sidesteps both limits and is
the actually-reliable path.

## Files

- `bridge/wbb_bridge.py` — PC-side Bluetooth-to-UDP bridge (Linux/BlueZ).
- `android/` — Android Studio project for the Quest-side receiver + mapper.
- `unity/WBBReceiver.cs` — sample client for your own Unity Quest app.
# WiiQuest
