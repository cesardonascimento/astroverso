#!/usr/bin/python3 -I
import json
import re
import subprocess
import time

ATTEMPTS = 30


def log(message):
    print(f"[arcade] {message}", flush=True)


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
        log("nenhuma saída de som interna encontrada")
        return
    for node_id, name in sinks:
        try:
            subprocess.run(["wpctl", "set-mute", str(node_id), "1"], check=True, timeout=10)
            log(f"saída interna muda: {name}")
        except (OSError, subprocess.SubprocessError):
            log(f"não foi possível deixar muda a saída {name}")


main()
