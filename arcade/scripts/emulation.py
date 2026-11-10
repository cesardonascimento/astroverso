import io
import os
import re
import sys
import urllib.request
import xml.etree.ElementTree as ET
import zipfile
from xml.sax.saxutils import quoteattr

BUILDBOT = "https://buildbot.libretro.com/nightly/linux/x86_64/latest"
WINDOWS_DRIVERS = {"wasapi", "xaudio", "dsound", "winmm", "xinput", "dinput", "raw", "winraw",
                   "d3d8", "d3d9", "d3d10", "d3d11", "d3d12", "gdi", "wgl"}
GENERATED = ".astro-sistemas"


def say(kind, text):
    print(f"{kind} {text}", flush=True)


def windows_value(value):
    return bool(re.match(r"^[A-Za-z]?:\\", value)) or "\\" in value


def settings(path, rom_dir, media_dir):
    lines = []
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            lines = f.read().splitlines()
    else:
        os.makedirs(os.path.dirname(path), exist_ok=True)
    if not lines or not lines[0].startswith("<?xml"):
        lines.insert(0, '<?xml version="1.0"?>')
    wanted = {"ROMDirectory": rom_dir, "MediaDirectory": media_dir}
    removed = []
    kept = []
    for line in lines:
        match = re.search(r'name="([^"]+)"\s+value="([^"]*)"', line)
        if match and match.group(1) in wanted:
            continue
        if match and windows_value(match.group(2)):
            removed.append(match.group(1))
            continue
        kept.append(line)
    for key, value in wanted.items():
        kept.append(f"<string name=\"{key}\" value={quoteattr(value)} />")
    with open(path, "w", encoding="utf-8") as f:
        f.write("\n".join(kept) + "\n")
    say("ok", f"es_settings.xml: ROMDirectory {rom_dir}, MediaDirectory {media_dir}")
    if removed:
        say("ok", f"es_settings.xml: removidos caminhos do Windows ({', '.join(removed)})")


def retroarch_cfg(path):
    if not os.path.exists(path):
        os.makedirs(os.path.dirname(path), exist_ok=True)
        with open(path, "w", encoding="utf-8") as f:
            f.write('video_fullscreen = "true"\n')
        say("ok", "retroarch.cfg criado (tela cheia; o resto vem do padrão do RetroArch)")
        return
    with open(path, encoding="utf-8", errors="replace") as f:
        lines = f.read().splitlines()
    kept = []
    removed = 0
    for line in lines:
        match = re.match(r'^\s*([A-Za-z0-9_]+)\s*=\s*"(.*)"\s*$', line)
        if match:
            key, value = match.groups()
            if windows_value(value) or (key.endswith("_driver") and value.lower() in WINDOWS_DRIVERS):
                removed += 1
                continue
        kept.append(line)
    if removed:
        with open(path, "w", encoding="utf-8") as f:
            f.write("\n".join(kept) + "\n")
        say("ok", f"retroarch.cfg: {removed} linha(s) do Windows removida(s) (caminhos e drivers voltam ao padrão do Linux)")
    else:
        say("ok", "retroarch.cfg sem caminhos nem drivers do Windows")


def bundled(path):
    return {system.findtext("name"): system for system in ET.parse(path).getroot().findall("system")}


def located(systems, rom_dirs):
    found = {}
    for rom_dir in rom_dirs:
        try:
            names = sorted(os.listdir(rom_dir))
        except OSError as error:
            say("warn", f"{rom_dir}: não foi possível ler ({error.strerror})")
            continue
        unknown = []
        for name in names:
            if not os.path.isdir(os.path.join(rom_dir, name)) or name.startswith((".", "$")):
                continue
            if name == "System Volume Information":
                continue
            if name not in systems:
                unknown.append(name)
            elif name in found:
                say("warn", f"{name} está em {found[name]} e em {rom_dir}: vale o primeiro")
            else:
                found[name] = rom_dir
        if unknown:
            say("info", f"{rom_dir}: pastas que não são sistemas do ES-DE: {', '.join(unknown)}")
    return found


def custom_systems(bundled_path, custom_dir, rom_dirs):
    systems = bundled(bundled_path)
    found = located(systems, rom_dirs)
    path = os.path.join(custom_dir, "es_systems.xml")
    marker = os.path.join(custom_dir, GENERATED)
    previous = set()
    if os.path.exists(marker):
        with open(marker, encoding="utf-8") as f:
            previous = set(f.read().split())
    kept = []
    if os.path.exists(path):
        for system in ET.parse(path).getroot().findall("system"):
            if system.findtext("name") not in previous:
                kept.append(system)
    manual = {system.findtext("name") for system in kept}
    generated = []
    for name, rom_dir in sorted(found.items()):
        if rom_dir == rom_dirs[0]:
            continue
        if name in manual:
            say("info", f"{name}: mantida a definição manual de custom_systems")
            continue
        system = ET.fromstring(ET.tostring(systems[name]))
        system.find("path").text = os.path.join(rom_dir, name)
        generated.append(system)
    os.makedirs(custom_dir, exist_ok=True)
    if kept or generated:
        root = ET.Element("systemList")
        root.extend(kept + generated)
        ET.indent(root, space="    ")
        with open(path, "w", encoding="utf-8") as f:
            f.write('<?xml version="1.0"?>\n' + ET.tostring(root, encoding="unicode") + "\n")
    elif os.path.exists(path):
        os.remove(path)
    with open(marker, "w", encoding="utf-8") as f:
        f.write("\n".join(system.findtext("name") for system in generated) + "\n")
    first = sorted(name for name, rom_dir in found.items() if rom_dir == rom_dirs[0])
    say("ok", f"{len(found)} sistema(s) com ROMs; em {rom_dirs[0]}: {', '.join(first) or 'nenhum'}")
    for system in generated:
        say("ok", f"{system.findtext('name')}: {system.findtext('path')}")


def cores(bundled_path, cores_dir, update, rom_dirs):
    systems = bundled(bundled_path)
    found = located(systems, rom_dirs)
    wanted = {}
    without = []
    for name in sorted(found):
        command = systems[name].find("command")
        match = re.search(r"%CORE_RETROARCH%/(\S+?)_libretro\.so", command.text or "")
        if match:
            wanted.setdefault(match.group(1), []).append(name)
        else:
            without.append(f"{name} ({command.get('label')})")
    os.makedirs(cores_dir, exist_ok=True)
    installed = failed = 0
    for core, names in sorted(wanted.items()):
        target = os.path.join(cores_dir, f"{core}_libretro.so")
        if os.path.exists(target) and update != "1":
            continue
        try:
            with urllib.request.urlopen(f"{BUILDBOT}/{core}_libretro.so.zip", timeout=120) as response:
                data = response.read()
            with zipfile.ZipFile(io.BytesIO(data)) as archive:
                member = next(item for item in archive.namelist() if item.endswith("_libretro.so"))
                with open(target + ".new", "wb") as f:
                    f.write(archive.read(member))
            os.replace(target + ".new", target)
            installed += 1
            say("ok", f"núcleo {core} ({', '.join(names)})")
        except Exception as error:
            failed += 1
            say("warn", f"núcleo {core} ({', '.join(names)}) não baixado: {error}")
    total = len(wanted)
    say("ok", f"núcleos do RetroArch: {total - failed} de {total} prontos ({installed} baixado(s) agora)")
    if without:
        say("info", f"sem núcleo do RetroArch por padrão (emulador próprio, fica para depois): {', '.join(without)}")


def main():
    command, args = sys.argv[1], sys.argv[2:]
    if command == "settings":
        settings(*args)
    elif command == "retroarch-cfg":
        retroarch_cfg(*args)
    elif command == "systems":
        custom_systems(args[0], args[1], args[2:])
    elif command == "cores":
        cores(args[0], args[1], args[2], args[3:])
    else:
        sys.exit(f"comando desconhecido: {command}")


main()
