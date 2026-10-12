#!/usr/bin/env python3
import argparse
import json
import os
from pathlib import Path
import re
import shutil
import sys
import tempfile
from datetime import datetime


TARGETS = {
    "STM32F0": "stm32f0x.cfg",
    "STM32F1": "stm32f1x.cfg",
    "STM32F2": "stm32f2x.cfg",
    "STM32F3": "stm32f3x.cfg",
    "STM32F4": "stm32f4x.cfg",
    "STM32F7": "stm32f7x.cfg",
    "STM32G0": "stm32g0x.cfg",
    "STM32G4": "stm32g4x.cfg",
    "STM32H7": "stm32h7x.cfg",
    "STM32L0": "stm32l0.cfg",
    "STM32L1": "stm32l1.cfg",
    "STM32L4": "stm32l4x.cfg",
    "STM32L5": "stm32l5x.cfg",
    "STM32U5": "stm32u5x.cfg",
    "STM32WB": "stm32wbx.cfg",
    "STM32WL": "stm32wlx.cfg",
}
PROBES = {
    "cmsis-dap": ("DAP-Link / CMSIS-DAP", "interface/cmsis-dap.cfg", "swd"),
    "stlink": ("ST-LINK", "interface/stlink-dap.cfg", "dapdirect_swd"),
    "jlink": ("J-Link (OpenOCD)", "interface/jlink.cfg", "swd"),
}
LAUNCH_NAME = "STM32: Debug (OpenOCD)"
FLASH_LABEL = "Flash STM32 (OpenOCD)"


def read_json(path, default=None):
    if not path.exists() and default is not None:
        return default
    text = path.read_text(encoding="utf-8-sig")
    text = re.sub(
        r'"(?:\\.|[^"\\])*"|//[^\n]*|/\*[\s\S]*?\*/',
        lambda match: match[0] if match[0].startswith('"') else " ",
        text,
    )
    text = re.sub(
        r'("(?:\\.|[^"\\])*")|,\s*(?=[}\]])',
        lambda match: match[1] or "",
        text,
    )
    document = json.loads(text)
    if not isinstance(document, dict):
        raise ValueError(f"{path} 必须是 JSON 对象")
    return document


def choose(title, choices, default=0):
    print(f"\n{title}")
    for index, label in enumerate(choices, 1):
        suffix = " [默认]" if index - 1 == default else ""
        print(f"  {index}. {label}{suffix}")
    while True:
        answer = input(f"请选择 [回车={default + 1}]: ").strip()
        if not answer:
            return default
        if answer.isdecimal() and 1 <= int(answer) <= len(choices):
            return int(answer) - 1
        print("请输入列表中的编号。")


def detect_project(project):
    candidates = sorted(project.glob("*.ioc"))
    preferred = project / f"{project.name}.ioc"
    if preferred in candidates:
        candidates = [preferred]
    if len(candidates) > 1:
        raise ValueError("目录中有多个 .ioc，请将 --project 指向单个工程目录")
    values = {}
    if candidates:
        for line in candidates[0].read_text(encoding="utf-8-sig").splitlines():
            key, separator, value = line.partition("=")
            if separator:
                values[key] = value.strip()
    chip = values.get("Mcu.CPN") or values.get("Mcu.UserName")
    target = values.get("ProjectManager.ProjectName")
    if not target:
        cmake = (project / "CMakeLists.txt").read_text(encoding="utf-8")
        match = re.search(
            r'(?:set\(\s*CMAKE_PROJECT_NAME\s+|project\(\s*)"?([\w.-]+)',
            cmake,
            re.IGNORECASE,
        )
        if match:
            target = match[1]
    return chip, target


def select_chip(args, detected):
    if args.chip:
        chip = args.chip
    elif args.non_interactive:
        chip = detected
    else:
        families = list(TARGETS)
        labels = ([f"自动识别：{detected}"] if detected else []) + families + ["手动输入芯片型号"]
        selected = choose("选择目标芯片（仅生成调试配置，不修改 CubeMX 工程）", labels)
        if detected and selected == 0:
            chip = detected
        else:
            selected -= int(bool(detected))
            chip = families[selected] if selected < len(families) else input("芯片型号: ").strip()
    if not chip:
        raise ValueError("未识别到芯片，请使用 --chip STM32G431RBT6")
    chip = chip.upper().strip()
    if not re.fullmatch(r"STM32[A-Z0-9]+", chip):
        raise ValueError("芯片名称应为 STM32 系列或型号，例如 STM32G4 / STM32G431RBT6")
    return chip


def executable_path(value):
    expanded = os.path.expandvars(os.path.expanduser(str(value)))
    found = shutil.which(expanded)
    if found:
        return Path(found).absolute()
    raise ValueError(f"找不到可执行工具：{value}")


def version_key(path):
    return tuple(int(number) for number in re.findall(r"\d+", str(path)))


def bundle_roots():
    home = Path.home()
    roots = [
        home / "Library/Application Support/stm32cube/bundles",
        home / ".local/share/stm32cube/bundles",
        home / "AppData/Local/stm32cube/bundles",
    ]
    if os.environ.get("CUBE_BUNDLE_PATH"):
        roots.insert(0, Path(os.environ["CUBE_BUNDLE_PATH"]).expanduser())
    return roots


def detect_toolchain(project, override):
    if override:
        candidates = [Path(os.path.expandvars(override)).expanduser().absolute()]
    else:
        candidates = []
        cache = project / "build/Debug/CMakeCache.txt"
        if cache.exists():
            match = re.search(r"^CMAKE_C_COMPILER_AR:FILEPATH=(.+)$", cache.read_text(), re.MULTILINE)
            if match:
                candidates.append(Path(match[1]).parent)
        for root in bundle_roots():
            candidates.extend(sorted(root.glob("gnu-tools-for-stm32/*/bin"), key=version_key, reverse=True))
        compiler = shutil.which("arm-none-eabi-gcc")
        if compiler:
            candidates.append(Path(compiler).parent)
    suffix = ".exe" if os.name == "nt" else ""
    for candidate in candidates:
        if all((candidate / f"arm-none-eabi-{tool}{suffix}").is_file() for tool in ("gdb", "objdump", "nm")):
            return candidate.absolute()
    raise ValueError("未找到包含 gdb/objdump/nm 的工具链，请使用 --toolchain /path/to/bin")


def detect_scripts(openocd, override):
    if override:
        candidates = [Path(os.path.expandvars(override)).expanduser().absolute()]
    else:
        candidates = []
        if os.environ.get("OPENOCD_SCRIPTS"):
            candidates.append(Path(os.environ["OPENOCD_SCRIPTS"]).expanduser())
        for executable in (openocd, openocd.resolve()):
            candidates.extend((executable.parent.parent / "share/openocd/scripts", executable.parent / "scripts"))
        candidates.extend((Path("/opt/homebrew/share/openocd/scripts"), Path("/usr/share/openocd/scripts")))
    for candidate in candidates:
        if (candidate / "interface").is_dir() and (candidate / "target").is_dir():
            return candidate.absolute()
    raise ValueError("未找到 OpenOCD scripts 目录，请使用 --scripts /path/to/openocd/scripts")


def detect_svd(chip, override):
    if override:
        path = Path(os.path.expandvars(override)).expanduser().absolute()
        if not path.is_file():
            raise ValueError(f"SVD 不存在：{path}")
        return path
    if len(chip) < 9:
        return None
    for root in bundle_roots():
        packs = root.parent / "packs/STMicroelectronics"
        candidates = [path for path in packs.glob("*/**/*.svd") if chip.startswith(path.stem.upper())]
        if candidates:
            return max(candidates, key=lambda path: (len(path.stem), version_key(path)))
    return None


def inherited_preset(presets, name, active=()):
    if name in active:
        raise ValueError(f"CMake preset 循环继承：{name}")
    current = next((preset for preset in presets if preset.get("name") == name), None)
    if current is None:
        raise ValueError(f"找不到 CMake preset：{name}")
    parents = current.get("inherits", [])
    if isinstance(parents, str):
        parents = [parents]
    merged = {}
    for parent in reversed(parents):
        merged.update(inherited_preset(presets, parent, (*active, name)))
    merged.update(current)
    return merged


def find_elf(args, project, target):
    documents = [read_json(project / "CMakePresets.json")]
    user_presets = project / "CMakeUserPresets.json"
    if user_presets.exists():
        documents.append(read_json(user_presets))
    build_presets = [preset for document in documents for preset in document.get("buildPresets", [])]
    configure_presets = [preset for document in documents for preset in document.get("configurePresets", [])]
    build = inherited_preset(build_presets, args.preset)
    configure_name = build.get("configurePreset")
    if not configure_name:
        raise ValueError(f"构建 preset {args.preset} 未指定 configurePreset")
    configure = inherited_preset(configure_presets, configure_name)
    if args.elf:
        elf = args.elf.replace("${workspaceFolder}", str(project))
    else:
        binary_dir = configure.get("binaryDir")
        if not binary_dir:
            raise ValueError("preset 未指定 binaryDir，请用 --elf 指定固件路径")
        substitutions = {
            "${sourceDir}": project.as_posix(),
            "${sourceParentDir}": project.parent.as_posix(),
            "${sourceDirName}": project.name,
            "${presetName}": configure_name,
        }
        unresolved = binary_dir
        for variable in substitutions:
            unresolved = unresolved.replace(variable, "")
        if re.search(r"\$(?:[A-Za-z_]+)?\{", unresolved):
            raise ValueError("binaryDir 含未支持的宏，请用 --elf 指定固件路径")
        for variable, value in substitutions.items():
            binary_dir = binary_dir.replace(variable, value)
        elf = str(Path(binary_dir) / f"{target}.elf")
    path = Path(elf).expanduser()
    if not path.is_absolute():
        path = project / path
    return path.absolute(), configure_name


def vscode_path(path, project):
    try:
        return "${workspaceFolder}/" + path.relative_to(project).as_posix()
    except ValueError:
        return path.as_posix()


def tcl_quote(value):
    return '"' + re.sub(r'([\\"$\[\]])', r"\\\1", value) + '"'


def replace_entries(document, key, entries, legacy_launch=False):
    existing = document.setdefault(key, [])
    if not isinstance(existing, list) or any(not isinstance(item, dict) for item in existing):
        raise ValueError(f"{key} 必须是对象数组，原文件未修改")
    identifier = "name" if key == "configurations" else "label"
    names = {item[identifier] for item in entries}
    retained = []
    for item in existing:
        managed = item.get(identifier) in names
        if legacy_launch:
            managed = managed or (
                item.get("type") == "cortex-debug"
                and item.get("servertype") == "openocd"
                and "${workspaceFolder}/.vscode/openocd.cfg" in item.get("configFiles", [])
            )
        if not managed:
            retained.append(item)
    document[key] = retained + entries
    document.setdefault("version", "0.2.0" if key == "configurations" else "2.0.0")
    return document


def write_files(project, contents, dry_run):
    changes = {path: text for path, text in contents.items() if not path.exists() or path.read_text(encoding="utf-8") != text}
    if not changes:
        print("配置未变化，无需写入。")
        return
    if dry_run:
        for path, text in changes.items():
            print(f"\n--- {path} ---\n{text}")
        print("预览完成，未写入任何文件。")
        return
    backup = project / ".vscode/config-backups" / datetime.now().strftime("%Y%m%d-%H%M%S-%f")
    originals = [path for path in changes if path.exists()]
    if originals:
        backup.mkdir(parents=True)
        for path in originals:
            shutil.copy2(path, backup / path.name)
        print(f"原配置已备份：{backup}")
    for path, text in changes.items():
        path.parent.mkdir(parents=True, exist_ok=True)
        temporary = None
        try:
            with tempfile.NamedTemporaryFile(
                mode="w", encoding="utf-8", dir=path.parent,
                prefix=f".{path.name}.", suffix=".tmp", delete=False,
            ) as handle:
                temporary = Path(handle.name)
                handle.write(text)
            temporary.replace(path)
        finally:
            if temporary is not None and temporary.exists():
                temporary.unlink()
        print(f"已生成：{path}")


def parser():
    arguments = argparse.ArgumentParser(description="生成 STM32 CMake + Cortex-Debug + OpenOCD 编译/调试/烧录配置")
    arguments.add_argument("--project", type=Path, default=Path.cwd(), help="工程目录，默认当前目录")
    arguments.add_argument("--chip", help="芯片型号或系列，例如 STM32G431RBT6 / STM32F4")
    arguments.add_argument("--probe", choices=[*PROBES, "dap", "daplink"], help="下载器，dap/daplink 是 cmsis-dap 的别名")
    arguments.add_argument("--preset", default="Debug", help="CMake 构建 preset，默认 Debug")
    arguments.add_argument("--target-name", help="CMake 可执行目标名称，默认从 .ioc / CMakeLists.txt 识别")
    arguments.add_argument("--elf", help="固件路径，默认根据 preset binaryDir 和目标名称推导")
    arguments.add_argument("--target-cfg", help="覆盖 OpenOCD target 脚本，例如 target/stm32g4x.cfg")
    arguments.add_argument("--openocd", help="OpenOCD 可执行文件，默认从 PATH 自动查找")
    arguments.add_argument("--scripts", help="OpenOCD scripts 目录")
    arguments.add_argument("--toolchain", help="包含 arm-none-eabi-gdb/objdump/nm 的 bin 目录")
    arguments.add_argument("--gdb", help="覆盖 GDB 路径")
    arguments.add_argument("--svd", help="SVD 文件路径，默认从已安装 ST packs 查找，可省略")
    arguments.add_argument("--speed", type=int, default=2000, help="初始 SWD 频率，单位 kHz，默认 2000；目标脚本可能在复位时调整频率")
    arguments.add_argument("--reset", choices=["software", "nrst"], default="software", help="software 无需 NRST；nrst 要求接好复位线")
    arguments.add_argument("--non-interactive", action="store_true", help="不提问，默认使用检测到的芯片和 CMSIS-DAP")
    arguments.add_argument("--dry-run", action="store_true", help="只预览，不写文件")
    return arguments


def main():
    args = parser().parse_args()
    project = args.project.expanduser().resolve()
    if not (project / "CMakeLists.txt").is_file():
        raise ValueError(f"不是 CMake 工程目录：{project}")
    if args.speed <= 0:
        raise ValueError("--speed 必须大于 0")
    if not args.non_interactive and not sys.stdin.isatty() and (not args.chip or not args.probe):
        raise ValueError("非交互终端请添加 --non-interactive，或同时指定 --chip 和 --probe")
    detected, detected_target = detect_project(project)
    chip = select_chip(args, detected)
    probe = args.probe
    if not probe:
        probe = "cmsis-dap" if args.non_interactive else list(PROBES)[choose("选择下载器（统一使用 OpenOCD / SWD）", [value[0] for value in PROBES.values()])]
    if probe in ("dap", "daplink"):
        probe = "cmsis-dap"
    target = args.target_name or detected_target
    if not target:
        raise ValueError("未识别到 CMake 可执行目标，请使用 --target-name 指定")
    family = next((name for name in TARGETS if chip.startswith(name)), None)
    target_cfg = args.target_cfg or (f"target/{TARGETS[family]}" if family else None)
    if not target_cfg:
        raise ValueError(f"未内置 {chip} 的映射，请使用 --target-cfg target/xxx.cfg")
    openocd = executable_path(args.openocd or "openocd")
    scripts = detect_scripts(openocd, args.scripts)
    toolchain = detect_toolchain(project, args.toolchain)
    suffix = ".exe" if os.name == "nt" else ""
    gdb = executable_path(args.gdb or str(toolchain / f"arm-none-eabi-gdb{suffix}"))
    label, interface_cfg, transport = PROBES[probe]
    for filename in (interface_cfg, target_cfg):
        if not (scripts / filename).is_file():
            raise ValueError(f"OpenOCD 脚本不存在：{scripts / filename}；请更新 OpenOCD 或指定 --scripts / --target-cfg")
    elf, configure_name = find_elf(args, project, target)
    try:
        flash_elf = elf.relative_to(project).as_posix()
    except ValueError:
        flash_elf = elf.as_posix()
    svd = detect_svd(chip, args.svd)
    preset = args.preset
    configure_label = f"Configure {preset}"
    build_label = f"Build {preset}"
    configuration = {
        "name": LAUNCH_NAME,
        "type": "cortex-debug",
        "request": "launch",
        "cwd": "${workspaceFolder}",
        "executable": vscode_path(elf, project),
        "preLaunchTask": build_label,
        "servertype": "openocd",
        "serverpath": openocd.as_posix(),
        "armToolchainPath": toolchain.as_posix(),
        "gdbPath": gdb.as_posix(),
        "searchDir": [scripts.as_posix()],
        "configFiles": ["${workspaceFolder}/.vscode/openocd.cfg"],
        "runToEntryPoint": "main",
    }
    if svd:
        configuration["svdFile"] = svd.as_posix()
    vscode = project / ".vscode"
    launch = read_json(vscode / "launch.json", {"version": "0.2.0", "configurations": []})
    tasks = read_json(vscode / "tasks.json", {"version": "2.0.0", "tasks": []})
    existing_tasks = tasks.get("tasks", [])
    if not isinstance(existing_tasks, list) or any(not isinstance(task, dict) for task in existing_tasks):
        raise ValueError("tasks 必须是对象数组，原文件未修改")
    other_default = any(
        task.get("label") != build_label
        and isinstance(task.get("group"), dict)
        and task["group"].get("kind") == "build"
        and task["group"].get("isDefault")
        for task in existing_tasks
    )
    generated_tasks = [
        {"label": configure_label, "type": "cmake", "command": "configure", "preset": configure_name, "problemMatcher": []},
        {
            "label": build_label,
            "type": "cmake",
            "command": "build",
            "preset": preset,
            "targets": [target],
            "dependsOn": configure_label,
            "dependsOrder": "sequence",
            "group": {"kind": "build", "isDefault": not other_default},
            "problemMatcher": ["$gcc"],
        },
        {
            "label": FLASH_LABEL,
            "type": "process",
            "command": openocd.as_posix(),
            "args": [
                "-s", scripts.as_posix(),
                "-f", "${workspaceFolder}/.vscode/openocd.cfg",
                "-c", f"program {tcl_quote(flash_elf)} verify reset exit",
            ],
            "options": {"cwd": "${workspaceFolder}"},
            "dependsOn": build_label,
            "dependsOrder": "sequence",
            "problemMatcher": [],
        },
    ]
    reset = "none" if args.reset == "software" else "srst_only srst_nogate"
    cfg = (
        f"source [find {tcl_quote(interface_cfg)}]\n"
        f"transport select {transport}\n"
        f"source [find {tcl_quote(target_cfg)}]\n\n"
        f"adapter speed {args.speed}\n"
        f"reset_config {reset}\n"
    )
    launch = replace_entries(launch, "configurations", [configuration], legacy_launch=True)
    tasks = replace_entries(tasks, "tasks", generated_tasks)
    contents = {
        vscode / "launch.json": json.dumps(launch, ensure_ascii=False, indent=4) + "\n",
        vscode / "tasks.json": json.dumps(tasks, ensure_ascii=False, indent=4) + "\n",
        vscode / "openocd.cfg": cfg,
    }
    print(f"\n工程：{project}\n芯片：{chip}\n下载器：{label}\n目标脚本：{target_cfg}\n固件：{elf}")
    if detected and not detected.upper().startswith(chip) and not chip.startswith(detected.upper()):
        print(f"警告：.ioc 中的芯片是 {detected}，脚本不会修改芯片、链接脚本或编译选项。")
    if chip.startswith(("STM32H7", "STM32WB", "STM32WL")):
        print("提示：双核/特殊型号请核对 OpenOCD target 脚本和核选择，必要时使用 --target-cfg。")
    if not svd:
        print("提示：未匹配到 SVD，省略外设寄存器视图配置；可用 --svd 手动指定。")
    write_files(project, contents, args.dry_run)
    print(f"\nVS Code F5：{LAUNCH_NAME}\n仅烧录任务：{FLASH_LABEL}")
    print("脚本只生成配置，不编译、不连接下载器、不擦除或烧录芯片。")
    return 0


if __name__ == "__main__":
    try:
        sys.exit(main())
    except (OSError, ValueError, KeyError, TypeError) as error:
        print(f"错误：{error}", file=sys.stderr)
        sys.exit(1)
    except (EOFError, KeyboardInterrupt):
        print("\n已取消。", file=sys.stderr)
        sys.exit(130)
