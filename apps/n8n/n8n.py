from __future__ import annotations

import json
import secrets
from pathlib import Path

from kit import config, container, run, ui

from . import modules

APP = "n8n"
VERSION = "2.47.5"
IMAGE = f"docker.io/n8nio/n8n:{VERSION}"
RUNNERS_IMAGE = f"docker.io/n8nio/runners:{VERSION}"
NAME = "astroverso-n8n"
RUNNERS = "astroverso-n8n-runners"
PORT = 5678
HOME = "/home/node/.n8n"
BCRYPT = "/usr/local/lib/node_modules/n8n/node_modules/bcryptjs"
HASH_SCRIPT = (
    'let d="";process.stdin.on("data",c=>d+=c).on("end",()=>console.log(require(process.argv[1]).hashSync(d,10)))'
)
INBOX = f"{HOME}/.astroverso-import.json"
USER = "1000"


def folder() -> Path:
    return config.state(APP)


def data() -> Path:
    return folder() / "data"


def hash_file() -> Path:
    return folder() / "owner_password_hash"


def secrets_file() -> Path:
    return folder() / "n8n.env"


def runners_file() -> Path:
    return folder() / "runners.env"


def host() -> str:
    return config.load(APP).get("HOST") or f"n8n.{config.saved_domain()}"


def prepare_secrets() -> None:
    current = config.read_env(secrets_file())
    if not current.get("N8N_ENCRYPTION_KEY"):
        current["N8N_ENCRYPTION_KEY"] = secrets.token_urlsafe(36)
        ui.ok("chave de criptografia do n8n gerada (protege as credenciais; vai junto no backup)")
    current.setdefault("N8N_RUNNERS_AUTH_TOKEN", secrets.token_urlsafe(36))
    config.write_env(secrets_file(), current)
    config.write_env(runners_file(), {"N8N_RUNNERS_AUTH_TOKEN": current["N8N_RUNNERS_AUTH_TOKEN"]})
    if not config.load(APP).get("HOOK_KEY"):
        config.save(APP, {"HOOK_KEY": secrets.token_urlsafe(36)})


def save_password(password: str) -> None:
    container.pull(IMAGE)
    digest = run.capture(["podman", "run", "--rm", "-i", "--entrypoint", "node", IMAGE, "-e", HASH_SCRIPT, BCRYPT], input=password).strip()
    if not digest.startswith("$2"):
        ui.fail("não foi possível gerar o hash da senha do administrador")
    temporary = hash_file().with_suffix(".tmp")
    temporary.write_text(digest)
    temporary.chmod(0o644)
    temporary.replace(hash_file())
    ui.ok("senha do administrador guardada só como hash (bcrypt)")


def environment() -> dict[str, str]:
    values = config.load(APP)
    zone = config.timezone()
    return {
        "N8N_HOST": host(),
        "N8N_PROTOCOL": "https",
        "N8N_PORT": str(PORT),
        "N8N_EDITOR_BASE_URL": f"https://{host()}/",
        "WEBHOOK_URL": f"https://{host()}/",
        "N8N_PROXY_HOPS": "1",
        "GENERIC_TIMEZONE": zone,
        "TZ": zone,
        "N8N_ENFORCE_SETTINGS_FILE_PERMISSIONS": "true",
        "N8N_INSTANCE_OWNER_MANAGED_BY_ENV": "true",
        "N8N_INSTANCE_OWNER_EMAIL": values.get("OWNER_EMAIL", ""),
        "N8N_INSTANCE_OWNER_FIRST_NAME": values.get("OWNER_FIRST_NAME", ""),
        "N8N_INSTANCE_OWNER_LAST_NAME": values.get("OWNER_LAST_NAME", ""),
        "N8N_INSTANCE_OWNER_PASSWORD_HASH_FILE": "/run/secrets/owner_password_hash",
        "N8N_DIAGNOSTICS_ENABLED": "false",
        "N8N_VERSION_NOTIFICATIONS_ENABLED": "false",
        "N8N_TEMPLATES_ENABLED": "false",
        "N8N_PERSONALIZATION_ENABLED": "false",
        "EXTERNAL_FRONTEND_HOOKS_URLS": "",
        "N8N_DIAGNOSTICS_CONFIG_FRONTEND": "",
        "N8N_DIAGNOSTICS_CONFIG_BACKEND": "",
        "N8N_BLOCK_ENV_ACCESS_IN_NODE": "true",
        "N8N_DEFAULT_BINARY_DATA_MODE": "filesystem",
        "EXECUTIONS_DATA_PRUNE": "true",
        "EXECUTIONS_DATA_MAX_AGE": "336",
        "N8N_RUNNERS_MODE": "external",
        "N8N_RUNNERS_BROKER_LISTEN_ADDRESS": "0.0.0.0",
        "N8N_NATIVE_PYTHON_RUNNER": "true",
    }


def main_spec() -> container.Container:
    return container.Container(
        name=NAME,
        image=IMAGE,
        description="Astroverso n8n: editor, agendamentos e execuções das rotinas",
        volumes=[container.Volume(data(), HOME, "Z,U"), container.Volume(hash_file(), "/run/secrets/owner_password_hash", "ro,Z")],
        environment=environment(),
        env_file=secrets_file(),
        health=f"wget -q -O /dev/null http://127.0.0.1:{PORT}/healthz",
        health_start="2m",
    )


def runners_spec() -> container.Container:
    return container.Container(
        name=RUNNERS,
        image=RUNNERS_IMAGE,
        description="Astroverso n8n: executor do código dos nós Code (JavaScript e Python), separado do n8n",
        environment={"N8N_RUNNERS_TASK_BROKER_URI": f"http://{NAME}:5679", "TZ": config.timezone()},
        env_file=runners_file(),
        requires=[NAME],
    )


def specs() -> list[container.Container]:
    return [main_spec(), runners_spec(), *[modules.spec(item) for item in modules.found()]]


def installed() -> bool:
    return container.active(NAME)


def start() -> None:
    data().mkdir(exist_ok=True, mode=0o700)
    container.prepare()
    container.start(main_spec(), timeout=300)
    container.start(runners_spec())
    modules.start_all()


def stop() -> None:
    for spec in reversed(specs()):
        container.remove(spec.name)


def cli(*args: str, input: str | None = None, timeout: float = 600) -> tuple[int, str]:
    return container.exec_output(NAME, ["n8n", *args], user=USER, input=input, timeout=timeout)


def import_file(kind: str, content: str, *extra: str) -> tuple[int, str]:
    code, output = container.exec_output(NAME, ["sh", "-c", f'umask 077; cat > "{INBOX}"'], user=USER, input=content)
    if code == 0:
        code, output = cli(f"import:{kind}", f"--input={INBOX}", *extra)
    container.exec_output(NAME, ["rm", "-f", INBOX], user=USER)
    failed = code != 0 or any(word in output.lower() for word in ("error", "failed"))
    return (code or 1, output) if failed else (0, output)


def _copy_out(source: Path, target: Path) -> None:
    run.cmd(["podman", "unshare", "cp", "-r", str(source), str(target)])
    run.cmd(["podman", "unshare", "rm", "-rf", "--", str(source)])


def export(target: Path) -> None:
    if not installed():
        ui.fail("o n8n precisa estar no ar para o backup (a exportação é feita por ele)")
    for name in ("backup", "workflows"):
        run.cmd(["podman", "unshare", "rm", "-rf", "--", str(data() / name)])
    code, output = cli("export:entities", f"--outputDir={HOME}/backup")
    if code:
        ui.fail(f"o n8n não exportou o banco (export:entities): {output.strip()[-300:]}")
    code, output = cli("export:workflow", "--backup", f"--output={HOME}/workflows/")
    if code and "No workflows found" not in output:
        ui.fail(f"o n8n não exportou as rotinas (export:workflow): {output.strip()[-300:]}")
    _copy_out(data() / "backup", target / "entities")
    if (data() / "workflows").exists():
        _copy_out(data() / "workflows", target / "workflows")
    else:
        (target / "workflows").mkdir()
    count = len(list((target / "workflows").glob("*.json")))
    ui.ok(f"banco do n8n exportado (rotinas com o histórico, credenciais, usuários) e {count} rotina(s) em arquivos separados")


def load_entities(source: Path) -> None:
    run.cmd(["podman", "unshare", "rm", "-rf", "--", str(data())])
    data().mkdir(mode=0o700)
    run.cmd(["cp", "-r", str(source), str(data() / "backup")])
    container.pull(IMAGE)
    ui.info("carregando o banco do backup num banco novo...")
    code, output = run.output(["podman", "run", "--rm", "-v", f"{data()}:{HOME}:Z,U", "--env-file", str(secrets_file()),
                               "--entrypoint", "n8n", IMAGE, "import:entities", f"--inputDir={HOME}/backup", "--truncateTables=true"])
    if code or "Error importing" in output:
        ui.prefixed("\n".join(line for line in output.splitlines() if "error" in line.lower() or "fail" in line.lower())[-1500:])
        ui.fail("o n8n não carregou o banco do backup")
    run.cmd(["podman", "unshare", "rm", "-rf", "--", str(data() / "backup")])
    ui.ok("rotinas, credenciais e usuários do backup carregados")


def workflows(folder: Path) -> list[dict]:
    found = []
    for path in sorted(folder.glob("*.json")):
        try:
            item = json.loads(path.read_text())
        except ValueError:
            continue
        if isinstance(item, dict) and item.get("name"):
            found.append(item)
    return sorted(found, key=lambda item: str(item["name"]).lower())
