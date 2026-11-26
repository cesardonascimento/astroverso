from __future__ import annotations

from kit import changes, distro
from kit.watch import Problem

APP = "system"


def items() -> list[changes.Change]:
    return [changes.Change(
        "updates", "Atualizar o sistema sozinho, todo dia de madrugada (sem reiniciar)",
        "Instala o atualizador automático da distribuição (no Fedora, o dnf5-automatic) e o configura para aplicar as "
        "atualizações todo dia, por volta das 6h, sem nunca reiniciar a máquina. Quando uma atualização pedir reinício "
        "(kernel, systemd...), a verificação de hora em hora avisa no Discord, e você reinicia quando quiser (pelo "
        "Cockpit, por exemplo).",
        distro.auto_updates_active, distro.auto_updates_on, distro.auto_updates_off,
    )]


def collect() -> dict[str, Problem]:
    found: dict[str, Problem] = {}
    if not distro.auto_updates_active():
        return found
    result, started = distro.auto_updates_last()
    if started and result and result != "success":
        found["updates"] = Problem("erro", "A atualização automática do sistema falhou",
                                   f"Última tentativa: {started} ({result}). Veja: journalctl -u dnf5-automatic", "updates")
    if distro.reboot_pending():
        found["reboot"] = Problem("aviso", "Reinício pendente depois das atualizações",
                                  "O sistema atualizou algo que só vale depois de reiniciar (kernel, systemd...). Reinicie quando puder.", "reboot")
    return found
