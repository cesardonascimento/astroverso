from __future__ import annotations

import shutil
from pathlib import Path

from kit import changes, config, distro, docs, ui, validate, vault
from kit.app import Action

APP = "vault"
DESCRIPTION = "Os backups dos apps desta máquina: criptografados, um por dia, numa pasta do Nextcloud"
ORDER = 40
DOCS = Path(__file__).with_name("docs")


def status() -> bool:
    return vault.configured()


def items() -> list[changes.Change]:
    return [vault.change(APP)]


def _url(value: str) -> str:
    text = value.strip().rstrip("/")
    if not text.startswith("https://") or len(text) <= len("https://"):
        raise ValueError("um endereço com https://, como https://nextcloud.<domínio>")
    return text


def _key(current: dict[str, str]) -> str:
    if current.get("VAULT_KEY"):
        return current["VAULT_KEY"]
    ui.note(
        "A senha dos backups criptografa cada arquivo antes de ele sair da máquina. Guarde no seu gerenciador de senhas: "
        "sem ela, ninguém abre os backups, nem você. Use a mesma em todas as máquinas, se quiser."
    )
    return ui.secret("senha dos backups")


def _connect(current: dict[str, str]) -> None:
    ui.note(
        "Os backups vão para uma pasta dentro do Nextcloud, pelo WebDAV, com uma senha de app só para isso: o Nextcloud "
        "recebe cada arquivo como se você o enviasse, com lixeira e versões."
    )
    ui.link("criar a senha de app no Nextcloud", docs.link(DOCS / "nextcloud.md"))
    domain = config.saved_domain()
    url = ui.ask("endereço do Nextcloud", default=current.get("VAULT_URL") or (f"https://nextcloud.{domain}" if domain else None),
                 validate=_url)
    user = ui.ask("usuário do Nextcloud", default=current.get("VAULT_USER") or None, validate=validate.name)
    folder = ui.ask("pasta dos backups no Nextcloud", default=current.get("VAULT_FOLDER") or "/Backups", validate=vault.clean_folder)
    for _ in range(3):
        password = ui.secret("senha de app do Nextcloud", confirm=False)
        attempt = dict(zip(vault.KEYS, (url, user, password, folder, "-")))
        problem = vault.verify(attempt)
        if not problem:
            ui.ok(f"conectado ao Nextcloud como {user}: os backups vão para {folder}")
            vault.save(url, user, password, folder, _key(current))
            return
        ui.warn(problem)
    ui.fail("o Nextcloud não aceitou: confira o endereço, o usuário e a senha de app, e instale de novo")


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("Backups")
    ui.note(
        "Cada app guarda todo dia a própria configuração (respostas, senhas, bancos) num arquivo criptografado e o envia "
        f"para uma pasta do Nextcloud, um por dia, guardados por {vault.KEEP_DAYS} dias. Para recuperar, use Restaurar uma "
        "versão no app."
    )
    distro.install(["gnupg2", "zstd"])
    config.save(APP, {})
    current = vault.settings()
    if again and vault.configured() and not vault.verify(current):
        ui.ok(f"os backups continuam indo para {current['VAULT_FOLDER']} no Nextcloud")
    else:
        _connect(current)
    changes.install(APP, items(), again)
    ui.info("os apps desta máquina ganham a pergunta do backup diário na próxima instalação deles (ou em Mudanças no sistema)")
    summary()


def remove() -> None:
    ui.step("Backups")
    changes.undo_all(items())
    vault.forget()
    config.purge(APP)
    ui.info("os backups que já estão no Nextcloud ficaram lá")


def backup(folder: Path) -> None:
    shutil.copy2(config.env_file(APP), folder / ".env")


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    shutil.copy2(folder / ".env", config.env_file(APP))


def test_send() -> None:
    if not vault.configured():
        ui.fail("o vault ainda não está configurado: instale o app")
    problem = vault.verify(vault.settings())
    if problem:
        ui.fail(problem)
    vault.run_backup(APP, backup, "teste", notify=False)


def change_key() -> None:
    if not vault.configured():
        ui.fail("o vault ainda não está configurado: instale o app")
    ui.warn("os backups que já estão no Nextcloud continuam abrindo só com a senha antiga: guarde as duas")
    values = vault.settings()
    vault.save(values["VAULT_URL"], values["VAULT_USER"], values["VAULT_PASSWORD"], values["VAULT_FOLDER"], ui.secret("nova senha dos backups"))
    ui.ok("senha dos backups trocada: vale a partir do próximo backup")


def summary() -> None:
    ui.step("Resumo dos backups")
    values = vault.settings()
    if not vault.configured():
        ui.table([["Vault", ui.pending("não configurado")]])
        return
    problem = vault.verify(values)
    ui.table([
        ["Nextcloud", values["VAULT_URL"]],
        ["Usuário", values["VAULT_USER"]],
        ["Pasta desta máquina", vault.machine_folder(values)],
        ["Situação", ui.bad(problem) if problem else ui.good("respondendo")],
        ["Guardados por", f"{vault.KEEP_DAYS} dias"],
    ])


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    return [
        Action("summary", "Resumo dos backups", summary, remote=True),
        Action("changes", "Mudanças no sistema", manage),
        Action("test", "Testar o envio", test_send, remote=True),
        Action("key", "Trocar a senha dos backups", change_key),
        Action("backup-now", "Fazer backup agora", lambda: vault.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: vault.restore(APP, backup, restore)),
    ]
