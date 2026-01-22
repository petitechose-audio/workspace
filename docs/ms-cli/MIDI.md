# MIDI

This project uses virtual MIDI ports depending on the platform.

## Linux

- Virtual ports: `snd-virmidi`
- Serial permissions (upload + bridge): dialout/uucp group or udev rules

Typical actions:

```bash
sudo modprobe snd-virmidi
lsmod | grep snd_virmidi
```

Udev rules (Teensy):

```bash
curl -fsSL https://www.pjrc.com/teensy/00-teensy.rules | sudo tee /etc/udev/rules.d/00-teensy.rules >/dev/null
sudo udevadm control --reload-rules && sudo udevadm trigger
```

Udev rules (PlatformIO, generic):

- https://docs.platformio.org/en/latest/core/installation/udev-rules.html

## macOS

- Enable IAC Driver via Audio MIDI Setup

## Windows

- Install loopMIDI for virtual ports

Use `ms doctor` to see guided hints for your platform.
