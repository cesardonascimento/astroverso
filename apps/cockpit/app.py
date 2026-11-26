from __future__ import annotations

import shutil
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, distro, net, routes, run, ui, validate
from kit.app import Action

APP = "cockpit"
DESCRIPTION = "Painel web da máquina e dos containers (Cockpit) em https://<nome-da-máquina>.<domínio>"
ORDER = 70
PACKAGES = ["cockpit", "cockpit-podman", "cockpit-storaged", "cockpit-files"]
SOCKET = "cockpit.socket"
CONF = Path("/etc/cockpit/cockpit.conf")
PORT = 9090
TARGET = f"http://host.containers.internal:{PORT}"


def host() -> str:
    return config.load(APP).get("HOST") or f"{net.hostname()}.{config.saved_domain()}"


def conf_text(address: str) -> str:
    return "\n".join([
        "# Gerado pelo Astroverso (app cockpit): o Cockpit atrás do Caddy.",
        "[WebService]",
        f"Origins = https://{address} wss://{address}",
        "ProtocolHeader = X-Forwarded-Proto",
        "AllowUnencrypted = true",
        "",
    ])


def _conf_applied() -> bool:
    try:
        return CONF.read_text() == conf_text(host())
    except OSError:
        return False


def _conf_on() -> None:
    if distro.file_put(CONF, conf_text(host()), 0o644):
        run.succeeds(["systemctl", "try-restart", "cockpit.service"], sudo=True)
        ui.ok(f"Cockpit configurado para o endereço https://{host()}")


def _conf_off() -> None:
    if distro.file_drop(CONF):
        run.succeeds(["systemctl", "try-restart", "cockpit.service"], sudo=True)
        ui.ok("configuração do Cockpit para o Caddy apagada")


def _user_socket(on: bool) -> None:
    if on:
        run.cmd(["systemctl", "--user", "enable", "--now", "-q", "podman.socket"], quiet=True)
        ui.ok("containers do usuário visíveis no Cockpit (podman.socket)")
    else:
        run.succeeds(["systemctl", "--user", "disable", "--now", "-q", "podman.socket"])
        ui.ok("podman.socket do usuário desligado")


def items() -> list[changes.Change]:
    return [
        changes.Change(
            "socket", "Ligar o Cockpit (cockpit.socket)",
            f"O Cockpit sobe sob demanda quando alguém abre o painel (porta {PORT}). Sem ele, o painel não abre.",
            lambda: distro.service_active(SOCKET), lambda: distro.service_enable(SOCKET), lambda: distro.service_disable(SOCKET),
            danger=True,
        ),
        changes.Change(
            "proxy", f"Configurar o Cockpit para o endereço do Caddy ({CONF})",
            f"O {CONF} aceita o acesso por https://{host()} pelo Caddy (Origins, ProtocolHeader, AllowUnencrypted). "
            "Sem isso, o Cockpit recusa o login pelo endereço.",
            _conf_applied, _conf_on, _conf_off, danger=True,
        ),
        changes.Change(
            "firewall", f"Fechar a porta {PORT} do Cockpit para a rede (só pelo Caddy)",
            f"O painel só abre por https://{host()}, com cadeado. Se o Caddy cair, o caminho de volta é o SSH.",
            lambda: not distro.firewall_allowed("cockpit"), lambda: distro.firewall_close(["cockpit"]),
            lambda: distro.firewall_open(["cockpit"]),
        ),
        changes.Change(
            "podman", "Mostrar os containers do Astroverso no Cockpit (podman.socket do usuário)",
            "Liga o podman.socket do seu usuário, para a página Podman containers do Cockpit ver os containers rootless "
            "do Astroverso (logs, reiniciar, parar).",
            lambda: run.succeeds(["systemctl", "--user", "is-active", "-q", "podman.socket"]),
            lambda: _user_socket(True), lambda: _user_socket(False),
        ),
        kit_backup.change(APP),
    ]


def status() -> bool:
    return config.env_file(APP).exists() and distro.service_active(SOCKET)


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Cockpit: o painel da máquina")
    ui.note(
        "O Cockpit é o painel web desta máquina: uso de CPU e memória, logs, serviços, terminal, armazenamento, arquivos "
        "e os containers do Astroverso. O login é o usuário e a senha do sistema. Ele roda direto no sistema (não em "
        "container), porque administra a própria máquina."
    )
    run.sudo_prepare("instalar e configurar o Cockpit")
    values = config.load(APP)
    if not (again and values.get("HOST")):
        domain = config.domain()
        ui.note(f"O endereço do painel. O padrão usa o nome da máquina, para cada máquina da casa ter o seu: {net.hostname()}.{domain}.")
        config.save(APP, {"HOST": ui.ask("endereço do Cockpit", default=values.get("HOST") or f"{net.hostname()}.{domain}",
                                         validate=validate.domain)})
    distro.install(PACKAGES)
    changes.install(APP, items(), again)
    routes.publish(APP, [routes.Route(host(), TARGET)])
    ui.info(f"https://{host()} (login com o usuário e a senha do sistema)")
    summary()


def remove() -> None:
    ui.step("Cockpit")
    changes.undo_all(items())
    routes.withdraw(APP)
    ui.info(f"pacotes mantidos ({' '.join(PACKAGES)}): o Fedora Server já vem com o Cockpit")
    config.purge(APP)


def backup(folder: Path) -> None:
    shutil.copy2(config.env_file(APP), folder / ".env")


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    shutil.copy2(folder / ".env", config.env_file(APP))
    config.env_file(APP).chmod(0o600)
    install(reuse=True)


def summary() -> None:
    ui.step("Resumo do Cockpit")
    ui.section("Cockpit")
    ui.table([
        ["Endereço", f"https://{host()}"],
        ["Painel", ui.good("ligado (sob demanda)") if distro.service_active(SOCKET) else ui.bad("desligado")],
        ["Login", "usuário e senha do sistema"],
    ])
    ui.section("Mudanças no sistema")
    ui.table(changes.rows(items()), ["Mudança", "Situação"])


def manage() -> None:
    run.sudo_prepare("mudar a configuração do Cockpit")
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo do Cockpit", summary, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore)),
    ]
