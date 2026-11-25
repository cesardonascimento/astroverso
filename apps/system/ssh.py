from __future__ import annotations

import getpass
import json
import os
from pathlib import Path

from kit import changes, config, distro, docs, net, run, ui, validate

APP = "system"
PACKAGE = "openssh-server"
SERVICE = "sshd"
TAILSCALE = "100.64.0.0/10"
DROPIN = Path("/etc/ssh/sshd_config.d/10-astroverso.conf")
DOCS = Path(__file__).with_name("docs")
TYPES = ("ssh-ed25519", "ssh-rsa", "ecdsa-sha2-nistp256", "ecdsa-sha2-nistp384", "ecdsa-sha2-nistp521",
         "sk-ssh-ed25519@openssh.com", "sk-ecdsa-sha2-nistp256@openssh.com")
HEADER = "# Gerado pelo Astroverso (astroverso system → Chaves SSH autorizadas): edições à mão aqui são perdidas.\n"


def keys_file() -> Path:
    return config.state(APP) / "ssh-keys.json"


def authorized_file() -> Path:
    return Path.home() / ".ssh" / "authorized_keys"


def machine_key() -> Path:
    return Path.home() / ".ssh" / "id_ed25519"


def sources() -> list[str]:
    return [net.lan_network(), TAILSCALE]


def dropin_text() -> str:
    return f"AllowUsers {getpass.getuser()}\nPermitRootLogin no\n"


def _has(path: Path, text: str) -> bool:
    try:
        return path.read_text() == text
    except OSError:
        return False


def _server_on() -> None:
    distro.install([PACKAGE])
    distro.service_enable(SERVICE)


def _server_off() -> None:
    distro.service_disable(SERVICE)


def _limit_on() -> None:
    distro.firewall_limit("ssh", sources())


def _limit_off() -> None:
    distro.firewall_unlimit("ssh", sources())


def _dropin(text: str | None) -> None:
    previous = DROPIN.read_text() if DROPIN.exists() else None
    changed = distro.file_put(DROPIN, text) if text is not None else distro.file_drop(DROPIN)
    if not changed:
        return
    if not run.succeeds(["sshd", "-t"], sudo=True):
        if previous is None:
            distro.file_drop(DROPIN)
        else:
            distro.file_put(DROPIN, previous)
        ui.fail("o sshd recusou a configuração nova: a anterior foi mantida")
    if distro.service_active(SERVICE):
        distro.reload_service(SERVICE)


def _users_on() -> None:
    _dropin(dropin_text())
    ui.ok(f"SSH só para {getpass.getuser()}, sem o root")


def _users_off() -> None:
    _dropin(None)
    ui.ok("SSH de volta ao padrão de usuários da distribuição")


def items() -> list[changes.Change]:
    return [
        changes.Change(
            "ssh-server", "Ligar o servidor SSH",
            "O SSH é o acesso remoto ao terminal desta máquina, de qualquer PC da casa ou pelo Tailscale. Instala o "
            f"{PACKAGE} (se faltar) e liga o {SERVICE} agora e no boot.",
            lambda: distro.installed(PACKAGE) and distro.service_active(SERVICE), _server_on, _server_off, danger=True,
        ),
        changes.Change(
            "ssh-firewall", "Aceitar SSH só da rede de casa e do Tailscale",
            "Uma segunda camada de proteção: mesmo que a porta 22 seja aberta no roteador por engano, a internet não "
            f"chega ao SSH. O firewall aceita a porta só da rede {net.lan_network()} e do Tailscale ({TAILSCALE}).",
            lambda: distro.firewall_limited("ssh", sources()), _limit_on, _limit_off,
        ),
        changes.Change(
            "ssh-users", f"Deixar só {getpass.getuser()} entrar por SSH (sem o root)",
            f"Só a sua conta desta máquina ({getpass.getuser()}) entra por SSH, com chave ou senha; o root e outras "
            f"contas, não ({DROPIN}). A configuração é conferida pelo sshd antes de valer.",
            lambda: _has(DROPIN, dropin_text()), _users_on, _users_off,
        ),
    ]


def parse(line: str) -> tuple[str, str, str]:
    parts = line.strip().split()
    for index, part in enumerate(parts):
        if part in TYPES and index + 1 < len(parts):
            key = " ".join(parts[: index + 2])
            return key, f"{part} {parts[index + 1]}", " ".join(parts[index + 2:])
    raise ValueError("não é uma chave pública SSH (ex.: ssh-ed25519 AAAA… nome)")


def fingerprint(public: str) -> str:
    code, output = run.output(["ssh-keygen", "-l", "-f", "-"], input=public + "\n", timeout=10)
    parts = output.split()
    return parts[1] if code == 0 and len(parts) > 1 else ""


def keys() -> list[dict[str, str]]:
    try:
        saved = json.loads(keys_file().read_text())
    except (OSError, ValueError):
        return []
    return [item for item in saved if isinstance(item, dict) and item.get("name") and item.get("key")]


def _save(items: list[dict[str, str]]) -> None:
    temporary = keys_file().with_suffix(".tmp")
    temporary.write_text(json.dumps(items, indent=2) + "\n")
    temporary.chmod(0o600)
    temporary.replace(keys_file())
    folder = authorized_file().parent
    folder.mkdir(mode=0o700, exist_ok=True)
    content = HEADER + "".join(f"{item['key']} {item['name']}\n" for item in items)
    if _has(authorized_file(), content):
        return
    target = folder / ".authorized_keys.tmp"
    target.write_text(content)
    target.chmod(0o600)
    target.replace(authorized_file())
    run.succeeds(["restorecon", str(authorized_file())])
    ui.ok(f"{authorized_file()} atualizado ({len(items)} chave{'s' if len(items) != 1 else ''})")


def _validated(line: str) -> tuple[str, str]:
    key, public, comment = parse(line)
    if not fingerprint(public):
        raise ValueError("o ssh-keygen não reconheceu essa chave (copiada pela metade?)")
    return key, comment


def _import() -> None:
    if keys_file().exists():
        return
    try:
        lines = [line for line in authorized_file().read_text().splitlines() if line.strip() and not line.startswith("#")]
    except OSError:
        lines = []
    found = []
    for line in lines:
        try:
            found.append(_validated(line))
        except ValueError:
            ui.warn(f"linha do authorized_keys ignorada (não é uma chave): {line[:40]}…")
    chosen: list[int] = []
    if found:
        ui.note(
            "Estas chaves já entram nesta máquina por SSH. Daqui em diante, a lista é do Astroverso: marque as que "
            "continuam valendo e dê um nome a cada uma (o PC de onde ela vem)."
        )
        chosen = ui.checklist("Chaves que continuam autorizadas", [f"{comment or 'sem nome'}  {key[-24:]}" for key, comment in found],
                              selected=list(range(len(found)))) or []
    items: list[dict[str, str]] = []
    for index in chosen:
        key, comment = found[index]
        default = _safe_name(comment, index, {item["name"] for item in items})
        name = ui.ask(f"nome do PC da chave {comment or index + 1}", default=default, validate=_name_check({item["name"] for item in items}))
        items.append({"name": name, "key": key})
    _save(items)


def _safe_name(comment: str, index: int, taken: set[str]) -> str:
    base = comment.split("@")[-1].lower() if comment else ""
    try:
        name = validate.name(base)
    except ValueError:
        name = f"pc-{index + 1}"
    return name if name not in taken else f"{name}-{index + 1}"


def _name_check(taken: set[str]):
    def check(value: str) -> str:
        value = validate.name(value)
        if value in taken:
            raise ValueError(f"o nome {value} já está em uso")
        return value
    return check


def add_key() -> None:
    items = keys()
    ui.note(
        "No PC que vai entrar, mostre a chave pública com: cat ~/.ssh/id_ed25519.pub (se não existir, crie com "
        "ssh-keygen -t ed25519). Cole aqui a linha inteira, que começa com ssh-ed25519."
    )

    def check(value: str) -> str:
        key, _ = _validated(value)
        if any(item["key"] == key for item in items):
            raise ValueError("essa chave já está autorizada")
        return value.strip()

    line = ui.ask("chave pública", validate=check)
    key, comment = _validated(line)
    name = ui.ask("nome do PC", default=_safe_name(comment, len(items), {item["name"] for item in items}),
                  validate=_name_check({item["name"] for item in items}))
    _save(items + [{"name": name, "key": key}])
    ui.ok(f"{name} pode entrar por SSH")


def remove_keys() -> None:
    items = keys()
    if not items:
        ui.info("nenhuma chave autorizada")
        return
    if os.environ.get("SSH_CONNECTION"):
        ui.warn("você está conectado por SSH: se remover a chave deste PC, a próxima conexão vai pedir a senha")
    chosen = ui.checklist("Chaves para remover", [item["name"] for item in items], cancel=True)
    if not chosen:
        return
    _save([item for index, item in enumerate(items) if index not in chosen])


def manage_keys() -> None:
    while True:
        summary_keys()
        choice = ui.menu("Chaves SSH autorizadas", ["Adicionar uma chave", "Remover chaves", "Voltar"])
        if choice == 0:
            add_key()
        elif choice == 1:
            remove_keys()
        else:
            return


def github_ok() -> bool:
    if not machine_key().exists():
        return False
    _, output = run.output(["ssh", "-T", "-o", "BatchMode=yes", "-o", "StrictHostKeyChecking=accept-new",
                            "-o", "ConnectTimeout=10", "-i", str(machine_key()), "git@github.com"], timeout=30)
    return "successfully authenticated" in output


def github() -> None:
    if github_ok():
        ui.ok("o GitHub já aceita a chave desta máquina")
        return
    if not machine_key().exists():
        machine_key().parent.mkdir(mode=0o700, exist_ok=True)
        run.cmd(["ssh-keygen", "-q", "-t", "ed25519", "-N", "", "-C", f"{getpass.getuser()}@{net.hostname()}", "-f", str(machine_key())])
        ui.ok(f"chave desta máquina criada: {machine_key()}")
    ui.note("Cadastre esta chave pública no GitHub (Settings → SSH and GPG keys → New SSH key), com o nome desta máquina:")
    ui.info(machine_key().with_suffix(".pub").read_text().strip())
    ui.link("passo a passo", docs.link(DOCS / "github.md", "cadastrar-a-chave"))
    while ui.confirm("Já cadastrou?", default=True):
        if github_ok():
            ui.ok("o GitHub aceitou a chave desta máquina")
            return
        ui.warn("o GitHub ainda não aceita a chave: confira se colou a linha inteira")
    ui.warn("GitHub pendente: depois de cadastrar, use a ação Chave desta máquina para o GitHub")


def install(reuse: bool) -> None:
    _import()
    if reuse and machine_key().exists():
        return
    ui.note(
        "Esta máquina pode ter uma chave SSH própria para baixar e atualizar repositórios do GitHub (inclusive os "
        "privados) sem senha. Ela fica em ~/.ssh/id_ed25519 e você a cadastra uma vez na sua conta do GitHub."
    )
    if ui.confirm("Preparar a chave desta máquina para o GitHub?", default=True):
        github()


def summary_keys() -> None:
    items = keys()
    ui.section("Chaves SSH autorizadas")
    rows: list[list[str | ui.Cell]] = []
    for item in items:
        _, public, _ = parse(item["key"])
        rows.append([item["name"], public.split()[0], fingerprint(public) or ui.bad("inválida")])
    ui.table(rows or [[ui.off("nenhuma"), "-", "-"]], ["PC", "Tipo", "Impressão digital"])


def summary() -> None:
    summary_keys()
    ui.section("GitHub")
    ui.table([
        ["Chave desta máquina", str(machine_key()) if machine_key().exists() else ui.off("não criada")],
        ["Acesso ao GitHub", ui.good("aceita") if github_ok() else ui.pending("não aceita")],
    ])
