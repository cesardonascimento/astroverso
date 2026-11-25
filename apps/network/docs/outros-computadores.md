# Outros computadores: liberar a porta do Tailscale

O Tailscale de cada aparelho tenta se ligar **direto** ao servidor pela porta UDP `41641`. Se o firewall de um
computador bloquear essa porta, a conexão entre ele e o servidor passa por um servidor intermediário do Tailscale
(relay), **até dentro de casa**. Funciona, mas fica bem mais lento.

Faça isto em cada computador da casa que tem o Tailscale. Celulares e tablets não precisam.

O **Resumo da rede**, no servidor, mostra aparelho por aparelho quem está direto e quem está por relay.

## Windows

**Pelo PowerShell** (botão direito no menu Iniciar → **Terminal (Admin)** ou **Windows PowerShell (Admin)**):

```powershell
New-NetFirewallRule -DisplayName "Tailscale" -Direction Inbound -Protocol UDP -LocalPort 41641 -Action Allow
```

**Pela tela**, se preferir:

1. Abra **Firewall do Windows Defender com Segurança Avançada** (procure "firewall" no menu Iniciar).
2. Em **Regras de Entrada**, clique em **Nova Regra…**.
3. Escolha **Porta** → **UDP** → **Portas locais específicas**: `41641`.
4. **Permitir a conexão**, marque **Domínio**, **Particular** e **Público**, e dê o nome `Tailscale`.

A regra vale para todos os perfis de rede. Isso importa porque o Windows às vezes trata a rede de casa como
**Pública**, que é mais fechada.

## Linux

Com **firewalld** (Fedora, RHEL e derivados):

```sh
sudo firewall-cmd --permanent --add-port=41641/udp && sudo firewall-cmd --reload
```

Com **ufw** (Ubuntu, Debian e derivados):

```sh
sudo ufw allow 41641/udp
```

Sem firewall ativo, não há nada a fazer.

## macOS

O firewall do macOS controla aplicativos, não portas, e costuma liberar o Tailscale na primeira vez que ele abre
(aparece um aviso pedindo permissão). Se o computador estiver por relay, confira em **Ajustes do Sistema** → **Rede**
→ **Firewall** → **Opções** se o Tailscale está com **Permitir conexões de entrada**.

## Conferir

No computador, depois de liberar a porta:

```
tailscale ping <nome-da-máquina>
```

`<nome-da-máquina>` é o nome do servidor no Tailscale. A resposta deve terminar com `via <ip>:41641`, que indica
conexão direta. Se continuar `via DERP(...)`, veja [tailscale.md](tailscale.md#direto-ou-por-relay).
