# Roteador: IP fixo, DNS e porta do Tailscale

Três ajustes do `network` são feitos no roteador da casa. Cada marca chama as telas de um jeito, então abaixo estão
os nomes mais comuns. Na dúvida, procure o modelo do seu roteador junto com o nome do ajuste (por exemplo, "reserva
de DHCP").

**Para entrar no roteador:** abra no navegador o IP dele, que costuma ser o gateway da rede (`192.168.0.1`,
`192.168.1.1` ou parecido). O usuário e a senha ficam numa etiqueta embaixo do aparelho, quando não foram trocados.

Nos exemplos, `<ip>` é o IP do servidor na rede de casa. O instalador mostra o valor certo na tela.

## Reservar o IP e apontar o DNS

### 1. Reservar o IP do servidor

**Para que serve:** o DNS da casa, o anúncio no Tailscale e todos os endereços do Astroverso apontam para `<ip>`.
Se o roteador entregar outro IP ao servidor depois de reiniciar, tudo para.

Procure por **DHCP**, **LAN**, **Reserva de endereço**, **Address Reservation**, **Static Lease** ou **IP
estático**. Crie uma reserva com:

- o **MAC** do servidor (o roteador costuma listar os aparelhos conectados, e basta escolher o servidor na lista);
- o IP `<ip>`.

Salve. Alguns roteadores só aplicam a reserva depois que o servidor reconecta ou reinicia.

### 2. DNS primário e secundário

**Para que serve:** o roteador avisa aos aparelhos da casa qual DNS usar. Com o AdGuard como primário, os aparelhos
ganham o bloqueio de propaganda e os endereços `*.<domínio>` passam a funcionar em casa sem o Tailscale.

Na mesma tela de **DHCP** ou **LAN**, procure **DNS primário** e **DNS secundário** (ou **DNS Server 1** e **2**).
Atenção: é o DNS **entregue aos aparelhos** (DHCP), não o DNS que o próprio roteador usa para a internet (WAN).

| Campo | Valor |
|---|---|
| DNS primário | `<ip>` |
| DNS secundário | um DNS público, como `1.1.1.1` |

Salve. Os aparelhos pegam o DNS novo quando renovam a conexão: desligar e ligar o Wi-Fi resolve na hora.

**Por que um secundário:** se o servidor estiver desligado ou o AdGuard parado, os aparelhos continuam navegando
pelo secundário, só que sem bloqueio e sem os endereços da casa. Sem ele, a casa inteira ficaria sem internet. O
custo é que, de vez em quando, um aparelho pode perguntar ao secundário mesmo com o AdGuard no ar: um anúncio
escapa ou um endereço da casa demora para abrir.

**Se o roteador não deixa trocar o DNS** (comum em roteadores do provedor), dá para colocar o DNS manualmente em
cada aparelho, com os mesmos dois valores, ou usar um roteador seu atrás do do provedor.

**IPv6:** alguns roteadores também entregam um DNS IPv6 do provedor, que passa por fora do AdGuard. Se o painel do
AdGuard mostrar poucas consultas de um aparelho, procure no roteador a opção de DNS do IPv6 (às vezes em **IPv6** →
**DHCPv6** ou **RA**) e desligue a entrega de DNS por ali.

**Para conferir:** depois de reconectar um aparelho ao Wi-Fi, ele deve aparecer no painel do AdGuard
(`https://adguard.<domínio>`), em **Registro de consultas**. No servidor, use a ação **Marcar o DNS no roteador como
feito** se você respondeu "não" na instalação.

## Redirecionar a porta do Tailscale

**Para que serve:** fora de casa (4G, outra rede), o Tailscale tenta ligar o seu aparelho direto ao servidor.
Atrás do roteador, isso às vezes falha, e a conexão passa por um servidor intermediário do Tailscale, bem mais
lento. O redirecionamento garante a conexão direta. É opcional, mas recomendado, principalmente para vídeo,
jogos e arquivos grandes.

Procure **Redirecionamento de portas**, **Port Forwarding**, **Servidor virtual**, **Virtual Server** ou **NAT**.
Crie uma regra:

| Campo | Valor |
|---|---|
| Protocolo | UDP |
| Porta externa | `41641` |
| IP interno | `<ip>` |
| Porta interna | `41641` |

Salve. A porta só aceita aparelhos da sua conta do Tailscale: o tráfego é criptografado e autenticado pelo próprio
Tailscale, então ela não expõe o servidor.

**Se a internet é de um provedor com CGNAT** (o roteador recebe um IP como `100.64.x.x` na WAN), o redirecionamento
não tem efeito, e só o provedor pode mudar isso. O Tailscale continua funcionando, às vezes por relay.

**Para conferir:** no **Resumo da rede**, os aparelhos fora de casa devem aparecer como **direto**. No servidor, use
a ação **Marcar o redirecionamento no roteador como feito** se você respondeu "não" na instalação.
