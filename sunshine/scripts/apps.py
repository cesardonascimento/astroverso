import json
import os
import sys

DEFAULTS = {"Low Res Desktop", "Steam Big Picture"}


def main():
    path = sys.argv[1]
    data = {"env": {"PATH": "$(PATH):$(HOME)/.local/bin"}, "apps": []}
    if os.path.exists(path):
        with open(path, encoding="utf-8") as f:
            data = json.load(f)
    before = json.dumps(data, sort_keys=True)
    apps = [app for app in data.get("apps", []) if app.get("name") not in DEFAULTS]
    if not any(app.get("name") == "Desktop" for app in apps):
        apps.insert(0, {"name": "Desktop", "image-path": "desktop.png"})
    data["apps"] = apps
    names = ", ".join(app.get("name", "?") for app in apps)
    if json.dumps(data, sort_keys=True) == before:
        print(f"ok apps do Sunshine já configurados ({names})")
        return
    os.makedirs(os.path.dirname(path), exist_ok=True)
    with open(path + ".new", "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
        f.write("\n")
    os.replace(path + ".new", path)
    print(f"ok apps do Sunshine: {names}")


main()
