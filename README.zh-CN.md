# STM32 VS Code 配置生成器

[English](README.md) | [简体中文](README.zh-CN.md)

为 STM32 CMake 工程自动生成 VS Code **编译、烧录和调试**配置。保留 STM32CubeMX 生成的工程及 ST 插件管理的编译环境，通过 **Cortex-Debug + OpenOCD** 自由选择芯片和下载器。

**单个 Python 脚本，无第三方 Python 依赖，不包含课程固件或本机专属配置。**

## 功能特点

- 从 CubeMX `.ioc` 自动识别芯片和工程名，也可手动指定芯片系列、完整料号及构建目标。
- 支持交互式菜单和非交互命令行参数。
- 支持 DAP-Link / CMSIS-DAP、ST-LINK、J-Link，通过 OpenOCD 使用 SWD。
- 自动查找 OpenOCD、配置脚本、Arm 工具链和可选的 ST 设备包 SVD。
- 复用 CMake configure/build presets；F5 自动配置、编译、下载并暂停在 `main()`。
- 提供独立“编译后烧录并运行”任务。
- 保留无关 JSON/JSONC 配置，修改前备份，重复运行不添加重复项目。
- 支持 `--dry-run` 预览，不写入文件。

> 生成器本身**不会编译、初始化下载器、擦除或烧录芯片**。只有执行生成的 VS Code 任务或调试入口时，才会进行相应操作。

## 使用前提

请先安装并配置：

| 组件 | 用途 |
| --- | --- |
| Python 3.9+ | 运行脚本，仅使用标准库 |
| STM32CubeMX CMake 工程 | 提供 `CMakeLists.txt`、CMake presets，通常还包含 `.ioc` |
| STM32CubeIDE for VS Code / ST 编译工具 | 管理现有 STM32 编译器及 CMake 环境 |
| CMake Tools：`ms-vscode.cmake-tools` | 提供生成任务使用的 `cmake` 任务类型 |
| Cortex-Debug：`marus25.cortex-debug` | 提供调试功能 |
| OpenOCD | 提供下载器驱动、芯片脚本和 GDB Server |
| Arm GNU 工具链 | `bin` 目录包含 `arm-none-eabi-gdb`、`arm-none-eabi-objdump`、`arm-none-eabi-nm` |

脚本不会安装工具、扩展或 USB 驱动，也不会修改全局 VS Code 设置。生成的工具绝对路径对应当前机器；迁移机器或更新工具后，应重新运行生成器。

## 快速开始

下载或克隆本仓库，然后将脚本指向**实际的 STM32 固件工程**，而不是本工具所在目录：

```sh
python3 /path/to/stm32-vscode-configurator/configure_debug.py --project /path/to/your/stm32-project
```

按菜单编号选择芯片和下载器。芯片默认从 `.ioc` 识别，默认下载器为 CMSIS-DAP。当前交互提示和诊断信息为中文，所有命令行参数名为英文。

自动识别芯片并使用 CMSIS-DAP，不进行交互：

```sh
python3 configure_debug.py --project /path/to/your/stm32-project --non-interactive
```

也可以同时指定芯片和下载器：

```sh
python3 configure_debug.py --project /path/to/your/stm32-project --chip STM32G431RBT6 --probe dap
```

若把 `configure_debug.py` 复制到固件工程根目录，在该目录执行 `python3 configure_debug.py` 即可。未指定 `--project` 时，脚本将当前工作目录视为固件工程。

### 开始调试或烧录

生成后，在 VS Code 打开**固件工程**：

1. 在“运行和调试”中选择 **STM32: Debug (OpenOCD)**，按 **F5**。
2. 只烧录、不进入调试：选择 **终端 → 运行任务 → Flash STM32 (OpenOCD)**。

正确连接 SWD 信号线、公共地，以及下载器要求的目标电压参考，并给目标板供电。默认软件复位不需要连接 NRST；使用 `--reset nrst` 时必须连接复位线。

## 生成文件

```text
your-stm32-project/
└── .vscode/
    ├── launch.json       # Cortex-Debug 调试入口
    ├── tasks.json        # 配置、编译和烧录任务
    ├── openocd.cfg       # 下载器、SWD、目标芯片和复位设置
    └── config-backups/   # 现有文件发生变化时保存的原件
```

任务执行链：

```text
F5：      CMake 配置 → 编译目标 → OpenOCD 下载 → 暂停在 main()
烧录任务： CMake 配置 → 编译目标 → 烧录并校验 → 复位运行并退出
```

## 芯片与下载器

### 下载器

| `--probe` 参数 | 下载器 | OpenOCD 接口脚本 |
| --- | --- | --- |
| `cmsis-dap`、`dap`、`daplink` | DAP-Link / CMSIS-DAP | `interface/cmsis-dap.cfg` |
| `stlink` | ST-LINK | `interface/stlink-dap.cfg` |
| `jlink` | J-Link | `interface/jlink.cfg` |

三种下载器均使用 OpenOCD，而不是厂商专用 GDB Server。ST-LINK 使用 OpenOCD 的 direct SWD 传输；其余两种使用 `swd`。

### 内置默认芯片系列映射

STM32 **F0 / F1 / F2 / F3 / F4 / F7**、**G0 / G4**、**H7**、**L0 / L1 / L4 / L5**、**U5**、**WB / WL**。

可以输入 `STM32G4` 等系列名，或 `STM32G431RBT6` 等完整料号。生成器会检查本机 OpenOCD 中是否存在所选接口和目标脚本。

**系列映射不代表所有具体芯片都已通过硬件兼容性验证。** 双核 H7、WB/WL 特殊型号、安全启动/TrustZone 等场景可能需要自定义 target 脚本、选择内核及额外调试设置，可用 `--target-cfg` 覆盖目标脚本。

**选择不同芯片不会转换固件工程。** 更换芯片时，必须先用 CubeMX 生成正确的启动文件、链接脚本和编译设置；本工具只修改调试及任务配置。

## 参数与示例

仅预览，不写文件：

```sh
python3 configure_debug.py --project /path/to/project --non-interactive --dry-run
```

切换下载器、降低初始 SWD 速度或启用已连接的 NRST：

```sh
python3 configure_debug.py --project /path/to/project --chip STM32F407VGT6 --probe stlink
python3 configure_debug.py --project /path/to/project --chip STM32F103C8T6 --probe jlink
python3 configure_debug.py --project /path/to/project --non-interactive --speed 1000
python3 configure_debug.py --project /path/to/project --non-interactive --reset nrst
```

覆盖工具位置和固件输出布局：

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

| 参数 | 默认值或行为 |
| --- | --- |
| `--project` | 当前工作目录 |
| `--chip` | `.ioc` 中的芯片，或交互选择 |
| `--probe` | 交互选择；非交互模式默认 CMSIS-DAP |
| `--preset` | 构建 preset `Debug`，自动使用其关联的 configure preset |
| `--target-name` | 优先 `.ioc` 工程名，其次 CMake 中的字面量项目名 |
| `--elf` | `<preset binaryDir>/<target>.elf`；相对路径以工程目录为基准 |
| `--target-cfg` | 默认按芯片系列映射，可指定 scripts 相对路径或绝对路径 |
| `--openocd`、`--scripts` | 自动查找，或显式指定 |
| `--toolchain`、`--gdb` | 自动查找工具链，也可单独覆盖 GDB |
| `--svd` | 可选，从已安装 ST packs 自动匹配或显式指定 |
| `--speed` | 初始频率，单位 kHz，默认 `2000`；target 复位处理可能调整频率 |
| `--reset` | 默认 `software`；连接复位线时可选 `nrst` |
| `--non-interactive` | 不提问，默认使用识别的芯片和 CMSIS-DAP |
| `--dry-run` | 显示拟生成内容，不写入文件 |

运行 `python3 configure_debug.py --help` 查看完整帮助。Windows 安装方式不同的情况下，可使用 `py -3`；上面的多行命令采用 POSIX shell 语法。

## 现有配置与安全说明

- 保留其他调试入口、任务及 JSON 顶层字段。
- 同名生成项，以及引用 `${workspaceFolder}/.vscode/openocd.cfg` 的 Cortex-Debug/OpenOCD 调试入口，视为生成器管理的项目，会被替换；该 `openocd.cfg` 文件由生成器接管。
- 输入支持 JSONC 注释和尾随逗号；输出重新排版为 JSON，不保留注释。修改前保存原文件备份。
- 备份目录为 `.vscode/config-backups/<时间戳>/`；输出没有变化时，不创建新备份。
- 每个修改文件使用唯一临时文件替换，不会占用用户同名 `.tmp` 文件。这是逐文件替换，并非三个文件整体事务；意外中断后可使用备份恢复。
- 不修改 CubeMX 源码、固件、CMakeLists、presets 或工作区 settings。

## 已知限制与故障排查

- **Presets：**要求存在具名构建和配置 preset。支持 `CMakePresets.json` 与 `CMakeUserPresets.json` 内的继承，不递归读取外部 `include`。仅展开常见 CubeMX `binaryDir` 使用的源目录和 preset 名宏；复杂输出布局请用 `--elf`。
- **工具发现：**自动检测主要针对已检查的 macOS/Homebrew + ST bundles 环境。其他系统及安装布局可能需要显式指定工具路径；不代表所有系统、下载器、芯片均已做硬件测试。
- **缺少 OpenOCD 或目标脚本：**安装所需工具/脚本、更新 OpenOCD，或指定正确路径。生成器不会代为安装。
- **未匹配 SVD：**仍可生成配置，只省略外设寄存器视图；需要时使用 `--svd`。
- **任务类型缺失或编译失败：**检查 CMake Tools 及现有 STM32 构建环境。成功生成配置不等于固件已编译通过。
- **下载器连接失败：**检查目标电源、接线、下载器状态、USB 权限及 SWD 速度，关闭可能占用下载器的其他工具。
- **共享配置：**生成的工具路径对应本机安装位置；共享固件工程时，应检查生成文件并避免提交备份目录。

## 上游文档

- [Cortex-Debug](https://github.com/Marus/cortex-debug)
- [OpenOCD 下载器配置](https://openocd.org/doc/html/Debug-Adapter-Configuration.html)
- [CMake presets](https://cmake.org/cmake/help/latest/manual/cmake-presets.7.html)

本项目为独立配置工具，并非 ST、Arm、SEGGER 或 OpenOCD 官方产品。
