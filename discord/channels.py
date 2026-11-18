import json
import sys
import urllib.error
import urllib.request

API = "https://discord.com/api/v10"
VIEW, SEND, EMBED, HISTORY = 1 << 10, 1 << 11, 1 << 14, 1 << 16
PUBLIC_THREADS, PRIVATE_THREADS, SEND_IN_THREADS = 1 << 35, 1 << 36, 1 << 38
READ_ONLY = SEND | PUBLIC_THREADS | PRIVATE_THREADS | SEND_IN_THREADS
BOT_ALLOW = VIEW | SEND | EMBED | HISTORY


def say(kind, text):
    print(f"{kind} {text}", flush=True)


def call(token, method, path, body=None):
    data = json.dumps(body).encode() if body is not None else None
    request = urllib.request.Request(f"{API}/{path}", data=data, method=method, headers={
        "Authorization": f"Bot {token}",
        "Content-Type": "application/json",
        "User-Agent": "astroverso (homelab, 1.0)",
    })
    try:
        with urllib.request.urlopen(request, timeout=20) as response:
            raw = response.read()
            return response.status, json.loads(raw) if raw else None
    except urllib.error.HTTPError as error:
        return error.code, None


def overwrites(guild, bot):
    return [
        {"id": guild, "type": 0, "allow": "0", "deny": str(READ_ONLY)},
        {"id": bot, "type": 1, "allow": str(BOT_ALLOW), "deny": "0"},
    ]


def main():
    token = sys.stdin.readline().strip()
    main_channel, names = sys.argv[1], sys.argv[2:]
    status, me = call(token, "GET", "users/@me")
    status2, base = call(token, "GET", f"channels/{main_channel}")
    if status != 200 or status2 != 200:
        say("warn", f"o Discord não respondeu (HTTP {status}/{status2}): os avisos ficam todos no canal principal")
        return
    guild, parent, bot = base["guild_id"], base.get("parent_id"), me["id"]
    status, channels = call(token, "GET", f"guilds/{guild}/channels")
    if status != 200:
        say("warn", f"não foi possível listar os canais do servidor (HTTP {status})")
        return
    found = {c["name"]: c for c in channels if c.get("type") == 0}
    denied = False
    for name in names:
        channel = found.get(name)
        if channel is None:
            body = {"name": name, "type": 0, "permission_overwrites": overwrites(guild, bot)}
            if parent:
                body["parent_id"] = parent
            status, channel = call(token, "POST", f"guilds/{guild}/channels", body)
            if status not in (200, 201):
                say("warn", f"não foi possível criar #{name} (HTTP {status})")
                denied = denied or status == 403
                continue
            say("ok", f"canal #{name} criado, só de leitura")
        else:
            failed = False
            for item in overwrites(guild, bot):
                status, _ = call(token, "PUT", f"channels/{channel['id']}/permissions/{item['id']}",
                                 {"type": item["type"], "allow": item["allow"], "deny": item["deny"]})
                failed = failed or status not in (200, 204)
                denied = denied or status == 403
            if failed:
                say("warn", f"#{name} encontrado, mas as permissões (só leitura) não foram aplicadas")
            else:
                say("ok", f"canal #{name} encontrado, só de leitura")
        say("canal", f"{name}={channel['id']}")
    if denied:
        say("denied", "-")


main()
