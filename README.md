# STM32 VS Code Configurator

[English](README.md) | [简体中文](README.zh-CN.md)

Generate VS Code **build, flash and debug** configurations for STM32 CMake projects. Keep your STM32CubeMX-generated project and ST-managed build environment, while using **Cortex-Debug + OpenOCD** with a selectable MCU and debug probe.

**One Python script. No third-party Python dependencies. No firmware or machine-specific configurations included.**

## What it does

- Detects the MCU and project name from a CubeMX `.ioc` file, or accepts an explicit chip/family and executable target.
- Offers interactive menus and non-interactive command-line options.
- Supports DAP-Link / CMSIS-DAP, ST-LINK and J-Link through OpenOCD over SWD.
- Locates OpenOCD, its configuration scripts, an Arm toolchain and optional ST device-pack SVD files.
- Uses CMake configure/build presets; F5 configures, builds, downloads and stops at `main()`.
- Adds a separate flash-and-run task, including a build dependency.
- Preserves unrelated JSON/JSONC entries, backs up modified files and avoids duplicate entries on repeated runs.
- Offers `--dry-run` previews without writing files.

> The generator itself does **not** build firmware, initialize a probe, erase flash or program a device. Those operations happen only when you run the generated VS Code tasks or debug configuration.

## Requirements

Install and configure these tools before running the generator:

| Component | Purpose |
| --- | --- |
| Python 3.9+ | Runs the generator using only the standard library |
| STM32CubeMX CMake project | Supplies `CMakeLists.txt`, CMake presets and usually a `.ioc` file |
| STM32CubeIDE for VS Code / ST build tooling | Manages the existing STM32 compiler and CMake environment |
| CMake Tools, `ms-vscode.cmake-tools` | Provides the generated `cmake` tasks |
| Cortex-Debug, `marus25.cortex-debug` | Provides the debug session |
| OpenOCD | Supplies the probe driver, target scripts and GDB server |
| Arm GNU tools | A `bin` directory containing `arm-none-eabi-gdb`, `arm-none-eabi-objdump` and `arm-none-eabi-nm` |

This utility does not install tools, extensions or USB drivers, and does not change global VS Code settings. Generated absolute tool paths are local to your machine; regenerate them after moving to another machine or updating the tools.

## Quick start

Download or clone this repository, then run the script **against your firmware project**, not against this utility's directory:

```sh
python3 /path/to/stm32-vscode-configurator/configure_debug.py --project /path/to/your/stm32-project
```

Select the MCU and probe in the menus. The default chip comes from `.ioc`; the default probe is CMSIS-DAP. Interactive prompts and diagnostic messages are currently in Chinese; all CLI option names are in English.

For a non-interactive setup using the detected chip and CMSIS-DAP:

```sh
python3 configure_debug.py --project /path/to/your/stm32-project --non-interactive
```

Or specify both selections explicitly:

```sh
python3 configure_debug.py --project /path/to/your/stm32-project --chip STM32G431RBT6 --probe dap
```

If you copy `configure_debug.py` into the firmware project root, simply run `python3 configure_debug.py` there. Without `--project`, the current working directory is the firmware project.

### Debug or flash

Open the **firmware project** in VS Code after generation:

1. Select **STM32: Debug (OpenOCD)** in Run and Debug, then press **F5**.
2. For flashing without a debugger, choose **Terminal → Run Task → Flash STM32 (OpenOCD)**.

Connect the correct SWD pins, a common ground and any probe-required target-voltage reference. Power the target correctly. The default software-reset configuration does not require an NRST connection; `--reset nrst` does.

## Generated files

```text
your-stm32-project/
└── .vscode/
    ├── launch.json       # Cortex-Debug launch configuration
    ├── tasks.json        # Configure, build and flash tasks
    ├── openocd.cfg       # Probe, SWD transport, MCU target and reset settings
    └── config-backups/   # Original files, when existing contents change
```

The generated task chain is:

```text
F5:          Configure preset → Build target → OpenOCD download → main()
Flash task:  Configure preset → Build target → Program + verify → Reset + exit
```

## MCU and probe selection

### Probes

| `--probe` | Probe | OpenOCD interface |
| --- | --- | --- |
| `cmsis-dap`, `dap`, `daplink` | DAP-Link / CMSIS-DAP | `interface/cmsis-dap.cfg` |
| `stlink` | ST-LINK | `interface/stlink-dap.cfg` |
| `jlink` | J-Link | `interface/jlink.cfg` |

All three use OpenOCD, not a vendor-specific GDB server. The ST-LINK configuration uses OpenOCD's direct SWD transport; the other two use `swd`.

### Default family mappings

STM32 **F0 / F1 / F2 / F3 / F4 / F7**, **G0 / G4**, **H7**, **L0 / L1 / L4 / L5**, **U5**, **WB / WL**.

Pass a family such as `STM32G4` or a full part number such as `STM32G431RBT6`. The script checks that the installed OpenOCD scripts contain the selected interface and target files.

**A family mapping is not a hardware-compatibility guarantee for every part.** Dual-core H7, WB/WL variants, security/TrustZone and other special configurations may require a custom target script, core selection and additional launch settings. Override the target script with `--target-cfg` when needed.

**Selecting another chip does not convert your firmware project.** First regenerate the correct startup files, linker script and compiler settings with CubeMX. The generator changes only debug/task configuration.

## Options and examples

Preview without making changes:

```sh
python3 configure_debug.py --project /path/to/project --non-interactive --dry-run
```

Use another probe, reduce the initial SWD speed, or enable a wired NRST reset:

```sh
python3 configure_debug.py --project /path/to/project --chip STM32F407VGT6 --probe stlink
python3 configure_debug.py --project /path/to/project --chip STM32F103C8T6 --probe jlink
python3 configure_debug.py --project /path/to/project --non-interactive --speed 1000
python3 configure_debug.py --project /path/to/project --non-interactive --reset nrst
```

Override tool locations and firmware layout:

```sh
python3 configure_debug.py --project /path/to/project --non-interactive \
  --openocd /path/to/bin/openocd \
  --scripts /path/to/share/openocd/scripts \
  --toolchain /path/to/arm-toolchain/bin \
  --svd /path/to/STM32G431.svd \
  --preset Debug \
  --target-name MyFirmware \
  --elf build/Debug/MyFirmware.elf
```

| Option | Default / behavior |
| --- | --- |
| `--project` | Current working directory |
| `--chip` | `.ioc` MCU, or interactive selection |
| `--probe` | Interactive selection; CMSIS-DAP with `--non-interactive` |
| `--preset` | Build preset `Debug`; follows its configure preset |
| `--target-name` | `.ioc` project name, then a literal CMake project name |
| `--elf` | `<preset binaryDir>/<target>.elf`; relative paths are project-relative |
| `--target-cfg` | Family mapping; accepts a script-relative or absolute path |
| `--openocd`, `--scripts` | Automatic lookup, or explicit override |
| `--toolchain`, `--gdb` | Automatic toolchain lookup; optional separate GDB override |
| `--svd` | Optional automatic ST pack lookup; explicit override supported |
| `--speed` | Initial speed in kHz, default `2000`; target reset handlers may adjust it |
| `--reset` | `software` by default, or `nrst` if the reset wire is connected |
| `--non-interactive` | Never prompts; defaults to detected chip and CMSIS-DAP |
| `--dry-run` | Prints proposed changes without writing files |

Run `python3 configure_debug.py --help` for the full CLI help. On Windows, use `py -3` if that is how Python is installed; the multiline examples above use POSIX shell syntax.

## Existing configurations and safety

- Other launch configurations, tasks and top-level JSON fields are retained.
- Generated names and Cortex-Debug/OpenOCD launches referencing `${workspaceFolder}/.vscode/openocd.cfg` are treated as generator-managed entries and replaced. The generator owns that `openocd.cfg` file.
- JSONC comments and trailing commas are accepted on input. Output is formatted JSON; comments are not retained. Original files are backed up first.
- Backups are stored in `.vscode/config-backups/<timestamp>/`. Identical output does not create another backup.
- Each changed file is replaced using a unique temporary file. This is per-file replacement, not a transaction across all three files; use the backups if a write is interrupted.
- The utility does not modify CubeMX sources, firmware, CMakeLists, presets or workspace settings.

## Known limits and troubleshooting

- **Presets:** requires named build/configure presets. Supports inheritance within `CMakePresets.json` and `CMakeUserPresets.json`; external `include` files are not recursively loaded. Only the source-directory and preset-name macros used by common CubeMX `binaryDir` values are expanded. Use `--elf` for complex output layouts.
- **Discovery:** automatic discovery is strongest for the tested macOS/Homebrew + ST bundles setup. Other platforms and installation layouts may require `--openocd`, `--scripts`, `--toolchain` and `--svd` overrides. Not a claim of hardware validation on every OS/probe/MCU.
- **No OpenOCD or target file:** install the required tool/scripts, update OpenOCD or pass the correct explicit paths. The generator does not install them for you.
- **No SVD:** generation continues without a peripheral-register view; provide `--svd` if desired.
- **No task provider or build failure:** verify CMake Tools and your existing STM32 build environment. Successful configuration generation does not validate the firmware build.
- **Probe connection failure:** check target power, wiring, probe availability, USB permissions and SWD speed. Close other tools that may own the probe.
- **Shared configurations:** generated tool paths identify the local installation. Review generated files and keep backup directories out of commits when sharing a firmware project.

## Upstream documentation

- [Cortex-Debug](https://github.com/Marus/cortex-debug)
- [OpenOCD debug-adapter configuration](https://openocd.org/doc/html/Debug-Adapter-Configuration.html)
- [CMake presets](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html)

This is an independent configuration utility, not an official ST, Arm, SEGGER or OpenOCD product.
