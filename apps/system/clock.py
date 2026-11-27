from __future__ import annotations

from kit import changes, distro
from kit.watch import Problem

APP = "system"


def items() -> list[changes.Change]:
    return [changes.Change(
        "clock", "Acertar o relógio pela internet (NTP)",
        "Liga o acerto automático do relógio (no Fedora, o chronyd): a hora da máquina fica certa sozinha, e o relógio do "
        "hardware passa a guardar UTC. Com a hora errada, os backups ganham a data errada, a sincronização com a nuvem "
        "decide errado qual arquivo é o mais novo e os timers rodam fora do horário.",
        distro.time_sync_active, distro.time_sync_on, distro.time_sync_off,
    )]


def collect() -> dict[str, Problem]:
    found: dict[str, Problem] = {}
    if distro.time_sync_active() and not distro.time_synced():
        found["clock"] = Problem("aviso", "Relógio fora de sincronia",
                                 "O acerto pela internet está ligado, mas o relógio ainda não sincronizou. Veja: timedatectl e chronyc tracking.", "clock")
    return found
