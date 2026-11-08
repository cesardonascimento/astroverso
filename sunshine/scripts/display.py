#!/usr/bin/python3 -I
import json
import os
import sys

from gi.repository import Gio, GLib

STATE = os.path.join(os.environ.get("XDG_RUNTIME_DIR", "/tmp"), "astro-sunshine-display.json")


def log(message):
    print(f"[sunshine] {message}", flush=True)


def proxy():
    return Gio.DBusProxy.new_for_bus_sync(
        Gio.BusType.SESSION, Gio.DBusProxyFlags.NONE, None,
        "org.gnome.Mutter.DisplayConfig", "/org/gnome/Mutter/DisplayConfig",
        "org.gnome.Mutter.DisplayConfig", None)


def current_state(display):
    serial, monitors, logical, _ = display.call_sync("GetCurrentState", None, Gio.DBusCallFlags.NONE, -1, None).unpack()
    if len(logical) != 1 or len(logical[0][5]) != 1:
        return serial, None, None
    x, y, scale, transform, _, connectors, _ = logical[0]
    connector = connectors[0][0]
    for spec, modes, _ in monitors:
        if spec[0] == connector:
            return serial, {"connector": connector, "x": x, "y": y, "scale": scale, "transform": transform}, modes
    return serial, None, None


def apply(display, serial, layout, mode, scale):
    config = [(layout["x"], layout["y"], scale, layout["transform"], True, [(layout["connector"], mode, {})])]
    display.call_sync(
        "ApplyMonitorsConfig",
        GLib.Variant("(uua(iiduba(ssa{sv}))a{sv})", (serial, 1, config, {})),
        Gio.DBusCallFlags.NONE, -1, None)


def fit_scale(mode, scale):
    return scale if scale in mode[5] else mode[4]


def do(display):
    width = int(os.environ.get("SUNSHINE_CLIENT_WIDTH", 0))
    height = int(os.environ.get("SUNSHINE_CLIENT_HEIGHT", 0))
    fps = float(os.environ.get("SUNSHINE_CLIENT_FPS", 60))
    serial, layout, modes = current_state(display)
    if layout is None:
        log("resolução da tela mantida: mais de um monitor ativo ou nenhum")
        return
    current = next(mode for mode in modes if mode[6].get("is-current"))
    matches = [mode for mode in modes if mode[1] == width and mode[2] == height]
    if not matches:
        log(f"a tela não aceita {width}x{height}; mantida em {current[0]} e o stream é redimensionado")
        return
    chosen = min(matches, key=lambda mode: abs(mode[3] - fps))
    if chosen[0] == current[0]:
        log(f"tela já em {current[0]}")
        return
    if not os.path.exists(STATE):
        with open(STATE, "w") as file:
            json.dump({"connector": layout["connector"], "mode": current[0], "scale": layout["scale"]}, file)
    apply(display, serial, layout, chosen[0], fit_scale(chosen, layout["scale"]))
    log(f"tela trocada de {current[0]} para {chosen[0]} (pedido do aparelho: {width}x{height}@{fps:g})")


def undo(display):
    if not os.path.exists(STATE):
        return
    with open(STATE) as file:
        saved = json.load(file)
    os.remove(STATE)
    serial, layout, modes = current_state(display)
    if layout is None or layout["connector"] != saved["connector"]:
        log("resolução original não restaurada: a configuração de telas mudou durante o stream")
        return
    original = next((mode for mode in modes if mode[0] == saved["mode"]), None)
    if original is None:
        log(f"resolução original {saved['mode']} não existe mais na tela")
        return
    apply(display, serial, layout, original[0], fit_scale(original, saved["scale"]))
    log(f"tela restaurada para {original[0]}")


def main():
    action = sys.argv[1] if len(sys.argv) > 1 else ""
    if action not in ("do", "undo"):
        log("uso: astro-sunshine-display do | undo")
        return
    try:
        display = proxy()
        do(display) if action == "do" else undo(display)
    except Exception as error:
        log(f"falha ao ajustar a resolução da tela, stream segue sem ajuste: {error}")


main()
