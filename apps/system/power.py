from __future__ import annotations

from pathlib import Path

from kit import changes, distro, run, ui

TARGETS = ["sleep.target", "suspend.target", "hibernate.target", "hybrid-sleep.target", "suspend-then-hibernate.target"]
LOGIND = Path("/etc/systemd/logind.conf.d")
LID = LOGIND / "99-astroverso-lid.conf"
KEYS = LOGIND / "99-astroverso-keys.conf"
BLANK = "astroverso-console-blank.service"
LID_TEXT = "[Login]\nHandleLidSwitch=ignore\nHandleLidSwitchExternalPower=ignore\nHandleLidSwitchDocked=ignore\n"
KEYS_TEXT = "[Login]\nHandleSuspendKey=ignore\nHandleSuspendKeyLongPress=ignore\nHandleHibernateKey=ignore\nHandleHibernateKeyLongPress=ignore\nIdleAction=ignore\n"
BLANK_TEXT = "\n".join([
    "[Unit]",
    "Description=Astroverso system: apaga a tela do console depois de 1 minuto sem uso",
    "After=getty@tty1.service",
    "",
    "[Service]",
    "Type=oneshot",
    "RemainAfterExit=yes",
    "ExecStart=/usr/bin/setterm --term linux --blank 1 --powerdown 1",
    "StandardOutput=tty",
    "TTYPath=/dev/tty1",
    "TTYReset=no",
    "TTYVHangup=no",
    "",
    "[Install]",
    "WantedBy=multi-user.target",
    "",
])


def _has(path: Path, text: str) -> bool:
    try:
        return path.read_text() == text
    except OSError:
        return False


def _logind(path: Path, text: str | None) -> None:
    changed = distro.file_put(path, text) if text is not None else distro.file_drop(path)
    if changed:
        distro.reload_service("systemd-logind")


def _mask() -> None:
    distro.units_mask(TARGETS)
    ui.ok("suspensão e hibernação desligadas")


def _unmask() -> None:
    distro.units_unmask(TARGETS)
    ui.ok("suspensão e hibernação de volta ao padrão")


def _lid_on() -> None:
    _logind(LID, LID_TEXT)
    ui.ok("tampa fechada ignorada: a máquina segue ligada")


def _lid_off() -> None:
    _logind(LID, None)
    ui.ok("tampa fechada de volta ao padrão (suspende)")


def _keys_on() -> None:
    _logind(KEYS, KEYS_TEXT)
    ui.ok("teclas de suspender e hibernar e a ociosidade ignoradas")


def _keys_off() -> None:
    _logind(KEYS, None)
    ui.ok("teclas de suspender e hibernar de volta ao padrão")


def _blank_on() -> None:
    distro.unit_install(BLANK, BLANK_TEXT)
    ui.ok("tela do console apaga depois de 1 minuto sem uso")


def _blank_off() -> None:
    distro.unit_remove(BLANK)
    reset = run.capture(["setterm", "--term", "linux", "--blank", "0", "--powerdown", "0"])
    if reset:
        run.cmd(["tee", "/dev/tty1"], sudo=True, input=reset, quiet=True)
    ui.ok("tela do console de volta ao padrão (sempre acesa)")


def items() -> list[changes.Change]:
    return [
        changes.Change(
            "power-sleep", "Desligar a suspensão e a hibernação",
            "O servidor precisa ficar ligado 24 horas para você entrar por SSH e para os serviços responderem. Com a "
            "suspensão e a hibernação desligadas (unidades mascaradas), nada põe a máquina para dormir: nem um comando, "
            "nem um programa, nem a ociosidade.",
            lambda: distro.units_masked(TARGETS), _mask, _unmask, danger=True,
        ),
        changes.Change(
            "power-lid", "Ignorar a tampa fechada",
            "Num notebook usado como servidor, a tampa fica fechada. Por padrão, fechar a tampa suspende a máquina; com "
            f"este ajuste ({LID}), ela segue ligada, na tomada ou na bateria.",
            lambda: _has(LID, LID_TEXT), _lid_on, _lid_off, danger=True,
        ),
        changes.Change(
            "power-keys", "Ignorar as teclas de suspender e hibernar",
            "Uma tecla de suspender esbarrada (ou a ociosidade, se alguém ligar isso um dia) não derruba o servidor. "
            f"O botão de ligar continua desligando a máquina normalmente ({KEYS}).",
            lambda: _has(KEYS, KEYS_TEXT), _keys_on, _keys_off,
        ),
        changes.Change(
            "power-blank", "Apagar a tela do console depois de 1 minuto sem uso",
            "No Fedora Server, a tela do console fica sempre acesa. De tampa fechada, ela esquenta e gasta à toa. Com "
            f"este ajuste (serviço {BLANK}), ela apaga depois de 1 minuto sem uso e acende só se alguém digitar no "
            "teclado da própria máquina.",
            lambda: distro.unit_enabled(BLANK), _blank_on, _blank_off,
        ),
    ]
