import json
import re
import subprocess
import time

ATTEMPTS = 30


def say(kind, text):
    print(f"{kind} {text}", flush=True)


def internal_sinks():
    try:
        output = subprocess.run(["pw-dump"], capture_output=True, text=True, timeout=10).stdout
        nodes = json.loads(output or "[]")
    except (OSError, subprocess.SubprocessError, ValueError):
        return []
    sinks = []
    for node in nodes:
        props = (node.get("info") or {}).get("props") or {}
        if props.get("media.class") != "Audio/Sink" or props.get("device.api") != "alsa":
            continue
        name = props.get("node.name", "") + props.get("node.description", "")
        if re.search("hdmi|displayport", name.lower()):
            continue
        sinks.append((node["id"], props.get("node.description", props.get("node.name", ""))))
    return sinks


def main():
    sinks = []
    for _ in range(ATTEMPTS):
        sinks = internal_sinks()
        if sinks:
            break
        time.sleep(1)
    if not sinks:
        say("warn", "nenhuma saída de som interna encontrada; tire o mudo pelas Configurações do GNOME")
    for node_id, name in sinks:
        try:
            subprocess.run(["wpctl", "set-mute", str(node_id), "0"], check=True, timeout=10)
            say("ok", f"saída interna com som: {name}")
        except (OSError, subprocess.SubprocessError):
            say("warn", f"não foi possível tirar o mudo da saída {name}")
    try:
        subprocess.run(["wpctl", "clear-default"], check=True, timeout=10)
        say("ok", "saída de som padrão escolhida pela prioridade (HDMI quando plugado)")
    except (OSError, subprocess.SubprocessError):
        say("warn", "não foi possível limpar a saída de som padrão escolhida à mão")


main()
