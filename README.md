# PC Optimizer

Free, open-source Windows toolkit for gaming performance. It only changes standard Windows settings,
explains each change, and never claims to "speed up" your PC with tricks that do not work
(such as RAM "cleaning" or registry "cleaning").

## Features

English and Korean UI (follows the Windows language by default). Advanced options sit under "Advanced settings".

Windows 11 style (follows the Windows light/dark theme and accent color). Every setting shows an explanation when the
pointer rests on it.

| Page | What it does |
|---|---|
| Dashboard | This PC (model, board, BIOS, CPU, RAM slots, graphics driver age, live CPU/RAM/GPU/power), computer scan, and a widget grid (edit mode like iOS / iPad: drag the title to put a widget anywhere on the grid, drag the corner to resize, × to remove). Built-in widgets: clock & calendar, network, drive speed vs. a typical drive, free space, battery (health, power in/out, charger advice), game locations, FPS test, memory, GPUs. Downloadable: wallpaper, display, audio (device types, output switch, app volume, mic mute), mouse & keyboard |
| App management | Auto optimize (games at maximum performance, separate power modes for charger and battery, background apps in efficiency mode, services paused during games); every installed app with icon and size, grouped by drive or source; run, boost, mark as game, move to another drive, uninstall |
| AI optimization (download) | AI mode (one click), model switcher window with presets and per-model settings (context, CPU only, threads, RAM), Ollama settings (KV cache, context, parallel, VRAM reserve), several GPUs, model folder move, page file check, speed test, VRAM per app, model size estimate |
| AI assistant widget (download) | Pop-up when Claude Code asks for approval (Allow / Deny goes straight back) or any program asks you, API keys (encrypted, test, environment), quick chat (Ollama, Claude, OpenAI, Gemini), prompt builder with checks, project packer for vibe coding |
| CPU & Memory | Running apps: cores, priority, efficiency mode, RAM trim; page file with recommended size |
| Graphics & Cooling | GPU status, Windows graphics settings, driver 3D settings (NVIDIA via NVAPI, AMD via ADLX, Intel via the Intel Graphics Control Library), cooling policy, power mode, Ultimate Performance plan, temperatures and fan control |
| Overlay | In-game overlay (FPS, average / 1% low, FPS and frame-time graphs, CPU / GPU / per-core clock, usage, temperature, RAM, VRAM, ping, game time, clock, mic). Items are tiles you switch on or off and drag to reorder; corner presets, exact position, drag with the mouse, any item in its own box, size, box opacity (text stays opaque, 0 = no box), presets; shortcut of your choice (default Ctrl+Shift+O) |
| Diagnostics | Wi-Fi, ping, DNS, speed test; drive health, bad sectors (SMART), power-on time, speed, read-only surface scan; partitions (resize NTFS drives, new drive from free space); temperatures |
| Cleanup | Recycle Bin, hibernation file, component cleanup, Windows.old, unneeded files on any drive (tick several and remove at once), browser caches, Edge removal |
| System | Windows (Game Mode, memory integrity, game boot, background news off, services paused during games), startup apps, notifications and visual effects, browser policies, hardware report |
| About | Theme, background picture, tooltips, font (Pretendard download), language, updates |

The installer removes any earlier version first and keeps your settings.

### Fan control and CPU temperature

CPU and motherboard sensors need [PawnIO](https://pawnio.eu), a signed open-source driver (GPL-2.0, source:
https://github.com/namazso/PawnIO) that LibreHardwareMonitor and FanControl also use instead of WinRing0.
The app bundles the official installer and runs it only when you press "Install PawnIO".
Fans the app controls go to 100% above 90 °C and return to BIOS control when the app closes.
Most laptop fans are locked by the maker; use the maker's app for those.

### Game boot

Memory integrity is only read at boot, so "Game boot" restarts Windows with it off and asks you to turn it
back on (one more restart) after the game closes.

### Downloadable widgets

Extra widgets are fetched from `widgets/` in this repository. The app only loads a file whose SHA-256 matches the
list built into that app version (`core/addons.py`, updated by `tools_hash.py` during the build), so the files
on `main` must be committed exactly as built.

## Install

Download `PCOptimizer-Setup-x.y.z.exe` from [Releases](https://github.com/siconiz/PC-optimizer-Ultra/releases).
Each release lists a SHA-256 checksum.

New releases may show a Windows SmartScreen warning until the installer builds reputation.

Requires Windows 10 or 11 (64-bit). The app asks for administrator rights because it changes system settings.

## Safety

- Every change is a regular Windows setting. Turn a switch off to revert it.
  Uninstalling the app does **not** revert settings you changed.
- **Memory integrity** protects the kernel from malicious drivers. Turning it off can raise FPS in some
  games but lowers your security. The app asks for confirmation and reminds you to turn it back on.
- The cleaner never deletes automatically and only moves files to the Recycle Bin.

## Privacy

- No telemetry, accounts or ads.
- Network requests: the optional update check (GitHub Releases API), widget downloads you ask for (GitHub),
  and the tests you start on the Diagnostics page (ping 1.1.1.1, DNS servers, Cloudflare speed test).
  No information about you or your PC is sent.
- Settings are stored in `%APPDATA%\PCOptimizer\config.json` and removed on uninstall.

## Run from source

```
pip install -r requirements.txt
python main.py
```

## Build

```
pip install -r requirements.txt pyinstaller
python build.py
"C:\Program Files (x86)\NSIS\makensis.exe" /DVERSION=1.0.0 installer.nsi
```

`python build.py` creates the portable app in `dist\PCOptimizer`, and NSIS turns it into
`dist\PCOptimizer-Setup-1.0.0.exe` (supports silent install with `/S`).

Releases are built by GitHub Actions when a tag `v*` is pushed (`.github/workflows/release.yml`).
The tag must match `__version__` in `core/version.py`.

## Code signing policy

Release binaries are built from this repository by GitHub Actions.
Signing details will be published here once a signing service is set up.

## Third-party

Bundled in `tools/` (downloaded by the release workflow):
- [Intel PresentMon](https://github.com/GameTechDev/PresentMon) (MIT) for the FPS test
- [LibreHardwareMonitorLib](https://github.com/LibreHardwareMonitor/LibreHardwareMonitor) 0.9.6 (MPL-2.0) for sensors and fans, used through [pythonnet](https://github.com/pythonnet/pythonnet) (MIT)
- [PawnIO](https://github.com/namazso/PawnIO) installer (GPL-2.0), run only on request

Drive speed comparison: 7200 rpm HDD ~180 MB/s (Seagate BarraCuda datasheet), SATA SSD ~550 MB/s (Samsung 870 EVO:
560 MB/s, SATA 6 Gb/s limit), PCIe 3.0 NVMe ~3,500 MB/s (Samsung 970 EVO Plus). The test reads 8 MiB blocks one at a
time without the Windows cache.

Fonts: [Pretendard](https://github.com/orioncactus/pretendard) (SIL OFL 1.1) is an optional download.
Audio: [pycaw](https://github.com/AndreMiras/pycaw) (MIT). Switching the default audio device uses an undocumented
Windows interface (as EarTrumpet and SoundSwitch do) and falls back to Windows sound settings if it fails.
Graphics driver settings use the DLLs that come with each driver (nothing is bundled): NVIDIA `nvapi64.dll`
(setting IDs from [NVIDIA/nvapi](https://github.com/NVIDIA/nvapi)), AMD `amdadlx64.dll`
([ADLX SDK](https://github.com/GPUOpen-LibrariesAndSDKs/ADLX)), Intel `ControlLib.dll`
([Intel Graphics Control Library](https://github.com/intel/drivers.gpu.control-library)). Only the published function
names, IDs and structure layouts from their headers are used; no SDK code is copied.

## Support

If this project helps you, consider [sponsoring it on GitHub](https://github.com/sponsors/siconiz).

## License

[MIT](LICENSE)
