from __future__ import annotations

import secrets
import shutil
import time
from datetime import datetime
from pathlib import Path

from kit import backup as kit_backup
from kit import changes, config, container, docs, mail, mailboxes, net, run, ui, units, validate, watch
from kit.app import Action

from . import cloudflare, mailbox

APP = "mail"
DESCRIPTION = "E-mail do Astroverso: caixa de entrada para automações (lida no Nextcloud Mail) e envio para qualquer app"
ORDER = 80
DOCS = Path(__file__).with_name("docs")
MODES = ("server", "client")
FETCH = "astroverso-mail-fetch"
CALENDAR = ("*-*-* 08..19:00/5:00", "*-*-* 20:00:00")
BUTTONS = (("Resumo do e-mail", "mail:summary"), ("Buscar agora", "mail:fetch"))
COMMAND = Path(__file__).resolve().parents[2] / "astroverso"


def values() -> dict[str, str]:
    return config.load(APP)


def mode() -> str:
    return values().get("MODE", "") if config.env_file(APP).exists() else ""


def status() -> bool:
    return mailbox.installed() if mode() == "server" else mode() == "client" and mail.configured()


def _fetch_units() -> dict[str, str]:
    return {
        f"{FETCH}.timer": "\n".join([
            "[Unit]",
            "Description=Astroverso mail: confere a campainha de 5 em 5 minutos, das 08:00 às 20:00",
            "",
            "[Timer]",
            *[f"OnCalendar={item}" for item in CALENDAR],
            "",
            "[Install]",
            "WantedBy=timers.target",
            "",
        ]),
        f"{FETCH}.service": "\n".join([
            "[Unit]",
            "Description=Astroverso mail: busca os e-mails na Cloudflare",
            "After=network-online.target",
            "",
            "[Service]",
            "Type=oneshot",
            f"ExecStart={COMMAND} mail action fetch-scheduled",
            "",
        ]),
    }


def items() -> list[changes.Change]:
    return [
        changes.Change(
            "fetch", "Buscar os e-mails de 5 em 5 minutos, das 08:00 às 20:00",
            f"Um timer do usuário ({FETCH}.timer) confere se chegou e-mail na Cloudflare e o traz para a caixa. Ele só "
            "lista os e-mails quando a campainha do Worker tocou (o plano gratuito limita as listagens). Fora desse "
            "horário, os e-mails esperam na Cloudflare e chegam às 08:00.",
            lambda: units.active(f"{FETCH}.timer"),
            lambda: units.install(_fetch_units(), [f"{FETCH}.timer"]),
            lambda: units.remove([f"{FETCH}.timer", f"{FETCH}.service"]),
            danger=True,
        ),
        watch.change(
            APP, "Verificar o e-mail de hora em hora e avisar no Discord",
            f"Um timer do usuário ({watch.name(APP)}.timer) confere a cada hora a busca dos e-mails, os que estão "
            "parados na Cloudflare, o token e a Quarentena, e avisa no Discord quando algo muda.",
            "o e-mail",
        ),
        kit_backup.change(APP),
    ]


def _domains(value: str) -> str:
    found = []
    for item in value.replace(";", ",").split(","):
        item = item.strip().lstrip("@").lower()
        if item:
            found.append(validate.domain(item))
    if not found:
        raise ValueError("informe ao menos um domínio, como gmail.com")
    return ",".join(dict.fromkeys(found))


def _token(reuse: bool, address: str) -> None:
    saved = values().get("CLOUDFLARE_API_TOKEN", "")
    domain = address.split("@", 1)[1]
    if reuse and saved and cloudflare.verify(saved):
        try:
            zone_id, account, zone_name = cloudflare.zone(saved, domain)
        except cloudflare.CloudflareError as problem:
            ui.warn(str(problem))
        else:
            config.save(APP, {"ZONE_ID": zone_id, "ACCOUNT_ID": account, "ZONE_NAME": zone_name})
            ui.ok("token da Cloudflare salvo continua válido")
            return
    ui.note(
        f"O app mail cria e mantém sozinho, na sua conta da Cloudflare, o Email Routing de {domain}, o Worker que "
        "recebe e envia os e-mails e o KV onde eles esperam. Para isso, precisa de um token próprio, com sete "
        "permissões (o do Caddy não serve)."
    )
    ui.link("passo a passo", docs.link(DOCS / "cloudflare.md", "criar-o-token"))
    while True:
        token = ui.secret("token da Cloudflare do app mail", confirm=False)
        if not cloudflare.verify(token):
            ui.warn("a Cloudflare não aceitou esse token (copiado pela metade, apagado ou desativado?)")
            continue
        try:
            zone_id, account, zone_name = cloudflare.zone(token, domain)
        except cloudflare.CloudflareError as problem:
            ui.warn(str(problem))
            continue
        break
    config.save(APP, {"CLOUDFLARE_API_TOKEN": token, "ZONE_ID": zone_id, "ACCOUNT_ID": account, "ZONE_NAME": zone_name})
    ui.ok(f"token conferido, com acesso à zona {zone_name}")


def _routing(address: str) -> None:
    current = values()
    token, zone_id, zone_name = current["CLOUDFLARE_API_TOKEN"], current["ZONE_ID"], current["ZONE_NAME"]
    domain = address.split("@", 1)[1]
    found = cloudflare.mx(token, zone_id, domain)
    if any("mx.cloudflare.net" in item for item in found):
        ui.ok(f"Email Routing ativo em {domain}")
        return
    if found:
        ui.error(f"{domain} já recebe e-mail por {', '.join(found)}")
        ui.link("por que isso importa", docs.link(DOCS / "cloudflare.md", "email-routing"))
        ui.fail("ativar o Email Routing desviaria esse e-mail: use um endereço num domínio sem outro e-mail")
    ui.info(f"ativando o Email Routing em {domain} (a Cloudflare cria e trava os registros MX e SPF)...")
    cloudflare.routing_enable(token, zone_id, domain, zone_name)
    if not cloudflare.wait_mx(token, zone_id, domain):
        ui.fail("o Email Routing foi pedido, mas os MX da Cloudflare não apareceram em 2 minutos: rode a instalação de novo")
    ui.ok(f"Email Routing ativo em {domain}")


def publish_worker() -> None:
    current = values()
    cloudflare.worker_publish(current["CLOUDFLARE_API_TOKEN"], current["ACCOUNT_ID"], current["KV_ID"],
                              current.get("ALLOWED_DOMAINS", ""), current["MAIL_ADDRESS"], current["SEND_KEY"])
    ui.ok(f"Worker {cloudflare.WORKER} publicado (domínios autorizados: {current.get('ALLOWED_DOMAINS', '')})")


def _cloudflare(address: str) -> None:
    ui.step("Cloudflare")
    _routing(address)
    current = values()
    token, account = current["CLOUDFLARE_API_TOKEN"], current["ACCOUNT_ID"]
    kv, created = cloudflare.kv_ensure(token, account)
    ui.ok(f"KV {cloudflare.KV_TITLE} {'criado' if created else 'já existe'} (guarda cada e-mail até a caixa buscar)")
    config.save(APP, {"KV_ID": kv, "SEND_KEY": current.get("SEND_KEY") or secrets.token_urlsafe(36)})
    publish_worker()
    url = cloudflare.workers_dev(token, account)
    config.save(APP, {"SEND_URL": url})
    ui.ok(f"envio de e-mails em {url}/enviar (só com a chave)")
    cloudflare.rule_ensure(token, current["ZONE_ID"], address)
    ui.ok(f"regra do Email Routing: {address} → Worker {cloudflare.WORKER}")


def _ask(reuse: bool) -> str:
    current = values()
    if reuse and current.get("MAIL_ADDRESS") and current.get("ALLOWED_DOMAINS"):
        return current["MAIL_ADDRESS"]
    domain = config.domain()
    ui.note(
        "O endereço que recebe os e-mails. Use um domínio que não tenha outro e-mail (o do Astroverso serve): a "
        "Cloudflare passa a receber todo e-mail dele."
    )
    address = ui.ask("endereço da caixa", default=current.get("MAIL_ADDRESS") or f"inbox@{domain}", validate=validate.email)
    ui.note(
        "Só e-mails desses domínios, com remetente comprovado (SPF ou DMARC), vão para a entrada. O resto vai para a "
        "pasta Quarentena. Coloque o domínio do e-mail que vai encaminhar para a caixa (ex.: gmail.com)."
    )
    allowed = ui.ask("domínios autorizados, separados por vírgula", default=current.get("ALLOWED_DOMAINS") or "", validate=_domains)
    config.save(APP, {"MAIL_ADDRESS": address, "ALLOWED_DOMAINS": allowed})
    return address


def _server(reuse: bool) -> None:
    address = _ask(reuse)
    _token(reuse, address)
    _cloudflare(address)
    ui.step("Caixa de e-mail")
    container.prepare()
    mailbox.prepare()
    mailbox.start()
    ui.ok(f"caixa {address} no ar (IMAP só na rede dos containers)")
    changes.install(APP, items(), reuse)
    mailbox.publish(address)
    current = values()
    mail.save(current["SEND_URL"], current["SEND_KEY"])
    fetch_now()
    if not any(item.get("verified") for item in cloudflare.addresses(current["CLOUDFLARE_API_TOKEN"], current["ACCOUNT_ID"])):
        ui.note("Os e-mails do Astroverso só chegam a destinatários confirmados na Cloudflare. Ainda não há nenhum.")
        ui.link("como funciona", docs.link(DOCS / "cloudflare.md", "destinatários"))
        if ui.confirm("Cadastrar um destinatário agora?", default=True):
            recipients()
    ui.note(
        f"Falta um passo seu: no seu e-mail de sempre, um filtro que encaminhe para {address} os e-mails que as "
        "automações devem ler (contas, boletos...)."
    )
    ui.link("passo a passo (Gmail e Outlook)", docs.link(DOCS / "encaminhamento.md"))


def _client(reuse: bool) -> None:
    if reuse and mail.configured():
        try:
            mail.check()
        except mail.MailError as problem:
            ui.warn(f"a configuração salva não funciona mais ({problem}): responda de novo")
        else:
            ui.ok("esta máquina continua enviando e-mails")
            return
    ui.note("Na máquina com a caixa, use a ação Mostrar o endereço e a chave de envio do app mail e cole os dois aqui.")
    while True:
        url = ui.ask("endereço de envio (https://astroverso-mail.<conta>.workers.dev)", validate=_url)
        key = ui.secret("chave de envio", confirm=False)
        try:
            mail.check(url, key)
            break
        except mail.MailError as problem:
            ui.warn(f"o Worker não aceitou: {problem}")
    mail.save(url, key)
    config.save(APP, {"MODE": "client"})
    ui.ok("esta máquina envia e-mails pelo Worker do Astroverso")


def _url(value: str) -> str:
    value = value.strip().rstrip("/")
    if not value.startswith("https://") or " " in value or len(value) < 12:
        raise ValueError("endereço com https://")
    return value


def install(reuse: bool | None = None) -> None:
    again = config.reuse(APP) if reuse is None else reuse
    ui.step("E-mail do Astroverso")
    ui.note(
        "Uma caixa de e-mail só de entrada para as automações (contas, boletos...), lida também no Nextcloud Mail, e "
        "o envio de e-mails para qualquer app do Astroverso, pela Cloudflare. Nenhuma porta fica aberta para a "
        "internet. Uma máquina tem a caixa; as outras só enviam."
    )
    chosen = mode() if again and mode() in MODES else ""
    if not chosen:
        chosen = MODES[ui.menu("Esta máquina", ["Tem a caixa de e-mail (a primeira máquina com o app)", "Só envia e-mails pela caixa de outra máquina"])]
    config.save(APP, {"MODE": chosen})
    if chosen == "server":
        _server(again)
    else:
        _client(again)
    summary()


def fetch_now() -> None:
    mailbox.fetch(values(), force=True)


def fetch_scheduled() -> None:
    mailbox.fetch(values(), force=False)


def recipients() -> None:
    current = values()
    token, account = current["CLOUDFLARE_API_TOKEN"], current["ACCOUNT_ID"]
    while True:
        found = cloudflare.addresses(token, account)
        ui.section("Destinatários de e-mail")
        ui.table([[item.get("email", ""), ui.good("confirmado") if item.get("verified") else ui.pending("aguardando confirmação")]
                  for item in found] or [[ui.off("nenhum"), "-"]], ["E-mail", "Situação"])
        choice = ui.menu("Destinatários", ["Adicionar destinatário", "Remover destinatários", "Voltar"])
        if choice == 0:
            target = ui.ask("e-mail do destinatário", validate=validate.email)
            cloudflare.address_add(token, account, target)
            ui.ok(f"{target} cadastrado: a Cloudflare mandou um e-mail com o link de confirmação")
        elif choice == 1 and found:
            chosen = ui.checklist("Quais remover?", [item.get("email", "") for item in found], cancel=True) or []
            for index in chosen:
                cloudflare.address_remove(token, account, str(found[index].get("id") or found[index].get("tag")))
                ui.ok(f"{found[index].get('email')} removido")
        else:
            return


def domains() -> None:
    while True:
        current = [item for item in values().get("ALLOWED_DOMAINS", "").split(",") if item]
        ui.section("Domínios autorizados")
        ui.table([[f"@{item}"] for item in current] or [[ui.pending("nenhum: tudo vai para a Quarentena")]], ["Domínio"])
        choice = ui.menu("Domínios", ["Adicionar domínio", "Remover domínios", "Voltar"])
        added: list[str] = []
        if choice == 0:
            item = _domains(ui.ask("domínio (ex.: empresa.com.br)", validate=_domains))
            added = [entry for entry in item.split(",") if entry not in current]
            current += added
        elif choice == 1 and current:
            chosen = ui.checklist("Quais remover?", [f"@{item}" for item in current], cancel=True) or []
            current = [item for index, item in enumerate(current) if index not in chosen]
        else:
            return
        config.save(APP, {"ALLOWED_DOMAINS": ",".join(current)})
        publish_worker()
        for item in added:
            mailbox.release(item)


def reprocess() -> None:
    found = mailbox.inbox()
    if not found:
        ui.info("a entrada está vazia: nada para reprocessar")
        return
    ui.note("Cada e-mail escolhido volta para a entrada como novo, e as automações que leem a caixa o processam de novo.")
    chosen = ui.checklist("Quais e-mails reprocessar?", [f"{date}  {title}" for _, date, title in found], all_option=True, cancel=True)
    if chosen:
        mailbox.reprocess([found[index][0] for index in chosen])


def reprocess_recent() -> None:
    found = mailbox.inbox("30d")
    if not found:
        ui.info("nenhum e-mail na entrada nos últimos 30 dias")
        return
    mailbox.reprocess([uid for uid, _, _ in found])


def show_key() -> None:
    current = values()
    ui.warn("a chave é a senha do envio: cole só na outra máquina e não mostre a ninguém")
    ui.info(f"endereço: {current.get('SEND_URL', '-')}")
    ui.info(f"chave: {current.get('SEND_KEY', '-')}")


def test_send() -> None:
    if not mail.configured():
        ui.fail("esta máquina ainda não envia e-mails: instale o app mail")
    target = ui.ask("enviar o teste para (um destinatário confirmado)", validate=validate.email)
    if mail.send(target, "Teste do Astroverso", f"E-mail de teste enviado por {net.hostname()}."):
        ui.ok(f"e-mail de teste enviado para {target}")


def cleanup() -> None:
    current = values()
    token, account = current["CLOUDFLARE_API_TOKEN"], current["ACCOUNT_ID"]
    ui.note(
        "Lista os Workers e os KV da sua conta da Cloudflare, menos os que este app usa, para você apagar os que não "
        "servem mais (de instalações antigas, por exemplo). Nada é apagado sem você marcar."
    )
    found = [("Worker", name, name) for name in cloudflare.workers(token, account) if name != cloudflare.WORKER]
    found += [("KV", str(item.get("title")), str(item.get("id"))) for item in cloudflare.kv_list(token, account)
              if str(item.get("id")) != current.get("KV_ID")]
    if not found:
        ui.ok("nada para limpar: só os recursos deste app")
        return
    chosen = ui.checklist("O que apagar na Cloudflare?", [f"{kind}: {name}" for kind, name, _ in found], cancel=True) or []
    if not chosen or not ui.confirm(f"Apagar {len(chosen)} recurso(s) da Cloudflare? Não tem volta.", default=False):
        return
    for index in chosen:
        kind, name, identifier = found[index]
        try:
            (cloudflare.worker_delete if kind == "Worker" else cloudflare.kv_delete)(token, account, identifier)
            ui.ok(f"{kind} {name} apagado")
        except cloudflare.CloudflareError as problem:
            ui.warn(str(problem))


def remove() -> None:
    ui.step("E-mail")
    current = values()
    if mode() == "server":
        changes.undo_all(items())
        if mailbox.installed() and current.get("KV_ID"):
            try:
                fetch_now()
            except SystemExit:
                ui.warn("a última busca falhou: os e-mails que estavam na Cloudflare se perdem com o KV")
        token, account, zone_id = current.get("CLOUDFLARE_API_TOKEN", ""), current.get("ACCOUNT_ID", ""), current.get("ZONE_ID", "")
        steps = [
            ("regra do Email Routing", lambda: cloudflare.rule_delete(token, zone_id, current["MAIL_ADDRESS"])),
            (f"Worker {cloudflare.WORKER}", lambda: cloudflare.worker_delete(token, account, cloudflare.WORKER)),
            (f"KV {cloudflare.KV_TITLE}", lambda: cloudflare.kv_delete(token, account, current["KV_ID"])),
            ("Email Routing do domínio", lambda: cloudflare.routing_disable(token, zone_id, current["MAIL_ADDRESS"].split("@", 1)[1], current["ZONE_NAME"])),
        ]
        for label, step in steps if token else []:
            try:
                step()
                ui.ok(f"{label} removido")
            except (cloudflare.CloudflareError, KeyError) as problem:
                ui.warn(f"{label} ficou: {problem} (remova pelo painel da Cloudflare)")
        container.remove(mailbox.NAME, mailbox.IMAGE)
        mailboxes.withdraw(APP)
    mail.forget()
    if mailbox.vmail().exists() and not ui.confirm(f"Apagar também os e-mails da caixa ({mailbox.vmail()})?", default=False):
        for path in config.state(APP).iterdir():
            if path != mailbox.vmail():
                run.cmd(["podman", "unshare", "rm", "-rf", "--", str(path)])
        ui.info(f"os e-mails ficaram em {mailbox.vmail()}")
        return
    config.purge(APP)


def backup(folder: Path) -> None:
    shutil.copy2(config.env_file(APP), folder / ".env")
    if mode() == "server":
        shutil.copy2(mailbox.password_file(), folder / "imap_password")
        run.cmd(["podman", "unshare", "tar", "-C", str(config.state(APP)), "-cf", str(folder / "vmail.tar"), "vmail"])


def restore(folder: Path) -> None:
    if not (folder / ".env").exists():
        ui.fail(f"backup sem a configuração do {APP}")
    config.state(APP)
    shutil.copy2(folder / ".env", config.env_file(APP))
    config.env_file(APP).chmod(0o600)
    if (folder / "imap_password").exists():
        mailbox.password_file().parent.mkdir(mode=0o700, exist_ok=True)
        shutil.copy2(folder / "imap_password", mailbox.password_file())
        mailbox.password_file().chmod(0o600)
    if (folder / "vmail.tar").exists():
        run.cmd(["podman", "unshare", "tar", "-C", str(config.state(APP)), "-xf", str(folder / "vmail.tar")])
    install(reuse=True)


def _ago(stamp: int) -> str:
    return datetime.fromtimestamp(stamp).strftime("%d/%m %H:%M") if stamp else "-"


def summary() -> None:
    ui.step("Resumo do e-mail")
    current = values()
    if mode() == "server":
        last = mailbox.last_fetch()
        ui.section("Caixa")
        ui.table([
            ["Endereço", current.get("MAIL_ADDRESS", "-")],
            ["Caixa (Dovecot)", ui.good("no ar") if mailbox.installed() else ui.bad("parada")],
            ["Última busca", (ui.good(f"às {_ago(last.get('time', 0))}") if last.get("ok") else ui.bad(last.get("error", "falhou"))) if last else ui.off("ainda não rodou")],
            ["Na entrada", str(mailbox.search_count("INBOX")) if mailbox.installed() else "-"],
            ["Na Quarentena", str(mailbox.search_count(mailbox.QUARANTINE)) if mailbox.installed() else "-"],
            ["Domínios autorizados", current.get("ALLOWED_DOMAINS", "-")],
        ])
        ui.section("Cloudflare")
        token = current.get("CLOUDFLARE_API_TOKEN", "")
        ui.table([
            ["Token", ui.good("válido") if token and cloudflare.verify(token) else ui.bad("recusado")],
            ["Worker", cloudflare.WORKER],
            ["Envio", current.get("SEND_URL", "-")],
        ])
        watch.summary(APP)
    ui.section("Envio nesta máquina")
    ui.table([["Envio", ui.good("configurado") if mail.configured() else ui.pending("não configurado")]])


def collect(previous: watch.State) -> dict[str, watch.Problem]:
    current = values()
    found: dict[str, watch.Problem] = {}
    if not mailbox.installed():
        found["container"] = watch.Problem("erro", "Caixa de e-mail parada", "Os e-mails ficam guardados na Cloudflare até ela voltar.")
        return found
    last = mailbox.last_fetch()
    if last and not last.get("ok"):
        found["fetch"] = watch.Problem("erro", "Busca dos e-mails falhando", str(last.get("error", "")), "fetch")
    token = current.get("CLOUDFLARE_API_TOKEN", "")
    try:
        valid = cloudflare.verify(token)
        waiting = mailbox.pending(current) if valid else []
    except cloudflare.CloudflareError:
        return found
    if not valid:
        found["token"] = watch.Problem("erro", "Token da Cloudflare do app mail recusado",
                                       "Os e-mails param de chegar e de ser enviados. Crie outro: " + docs.link(DOCS / "cloudflare.md", "criar-o-token"))
    hour = datetime.now().hour
    if waiting and 8 <= hour <= 20 and min(waiting).timestamp() < time.time() - 1800:
        found["waiting"] = watch.Problem("aviso", f"{len(waiting)} e-mail(s) parados na Cloudflare", "A busca não está trazendo os e-mails para a caixa.", "waiting")
    count = mailbox.search_count(mailbox.QUARANTINE)
    if count:
        found["quarantine"] = watch.Problem("info", f"{count} e-mail(s) na Quarentena",
                                            "Pode ser um remetente que falta autorizar (ação Domínios autorizados).", "quarantine")
    return found


def check() -> None:
    watch.run(APP, collect, BUTTONS, "e-mail em ordem")


def manage() -> None:
    changes.manage(APP, items())


def actions() -> list[Action]:
    common = [Action("summary", "Resumo do e-mail", summary, remote=True), Action("test", "Enviar um e-mail de teste", test_send)]
    if mode() != "server":
        return common
    return common + [
        Action("fetch", "Buscar os e-mails agora", fetch_now, remote=True),
        Action("fetch-scheduled", "Busca agendada", fetch_scheduled, menu=False),
        Action("domains", "Domínios autorizados", domains),
        Action("recipients", "Destinatários de e-mail", recipients),
        Action("reprocess", "Reprocessar e-mails", reprocess),
        Action("reprocess-recent", "Reprocessar os e-mails dos últimos 30 dias", reprocess_recent, remote=True, confirm=True, menu=False),
        Action("key", "Mostrar o endereço e a chave de envio", show_key),
        Action("cleanup", "Limpar Workers e KV antigos da Cloudflare", cleanup),
        Action("changes", "Mudanças no sistema", manage),
        Action("watch", "Verificar agora (e avisar no Discord)", check, remote=True),
        Action("backup-now", "Fazer backup agora", lambda: kit_backup.run_backup(APP, backup), remote=True),
        Action("restore-version", "Restaurar uma versão", lambda: kit_backup.restore(APP, backup, restore)),
    ]

