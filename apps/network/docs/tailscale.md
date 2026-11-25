# Tailscale: ajustes no painel

O instalador do `network` liga o servidor à sua conta do Tailscale sozinho. Dois ajustes só podem ser feitos por
você, no painel do Tailscale (<https://login.tailscale.com/admin>), com a conta dona da rede. O instalador confere
cada um depois que você responde "Já configurou?".

Nos exemplos, `<ip>` é o IP do servidor na rede de casa, `<nome-da-máquina>` é o nome dele e `<domínio>` é o seu
domínio. O instalador mostra os valores certos na tela.

## Aprovar a rota do servidor

**Para que serve:** o seu domínio aponta para o IP do servidor na rede de casa (`<ip>`). Em casa, qualquer aparelho
chega nesse IP. Fora de casa, o celular só chega nele se o Tailscale souber que o servidor responde por esse IP. O
servidor anuncia isso sozinho (`<ip>/32`, só o próprio IP, não a rede inteira), mas o Tailscale só usa o anúncio
depois que o dono da conta aprova.

1. Abra <https://login.tailscale.com/admin/machines>.
2. Na linha de `<nome-da-máquina>`, aparece a etiqueta **Subnets** com um ponto de alerta: é o anúncio esperando
   aprovação.
3. Clique nos três pontinhos (**⋯**) no fim da linha e escolha **Edit route settings…**.
4. Em **Subnet routes**, marque `<ip>/32` e clique em **Save**.

É só uma vez: a aprovação continua valendo depois de reiniciar ou reinstalar, desde que a máquina mantenha o mesmo
nome no painel. Se você remover a máquina do painel, a aprovação precisa ser feita de novo.

**Se não aparecer nada para aprovar:** confira se a máquina está online no painel e rode a ação **Reconectar ao
Tailscale** no `astroverso`.

## Split DNS

**Para que serve:** fora de casa, o celular pergunta ao DNS do Tailscale, e não ao AdGuard, qual é o IP de
`adguard.<domínio>`. O Split DNS diz ao Tailscale: "perguntas sobre `<domínio>` vão para o AdGuard do servidor".
Com isso, os endereços do Astroverso abrem fora de casa exatamente como dentro.

1. Abra <https://login.tailscale.com/admin/dns>.
2. Em **Nameservers**, clique em **Add nameserver** e escolha **Custom…**.
3. Em **Nameserver**, coloque `<ip>`.
4. Ligue **Restrict to domain** (é isso que faz o Split DNS) e, em **Domain**, coloque `<domínio>`.
5. Clique em **Save**.

Se já existir outra entrada para `<domínio>` (de uma instalação antiga ou de outra máquina), apague: duas entradas
para o mesmo domínio fazem os aparelhos às vezes perguntarem ao lugar errado.

**Não precisa** ligar **Override DNS servers** nem colocar o AdGuard como DNS global do Tailscale. Só os nomes do
domínio passam pelo servidor, e o resto continua com o DNS normal de cada aparelho.

**Para conferir:** no **Resumo da rede**, a linha **Split DNS** mostra `<domínio> → <ip>` com ✔. Em um celular fora
de casa, com o Tailscale ligado, `https://adguard.<domínio>` deve abrir com cadeado.

## Desligar a expiração da chave

**Para que serve:** por padrão, o Tailscale pede um login novo de cada máquina a cada 180 dias. Num servidor, isso
significa que um dia ele sai da rede sozinho e os endereços param de abrir fora de casa. A verificação do `network`
avisa no Discord 14 dias antes, mas o melhor é desligar a expiração no servidor:

1. Abra <https://login.tailscale.com/admin/machines>.
2. Clique nos três pontinhos (**⋯**) na linha de `<nome-da-máquina>` e escolha **Disable key expiry**.

Faça isso só nas máquinas da casa que ficam sempre ligadas. Celulares e notebooks podem continuar expirando: se
um deles for perdido, ele sai da rede sozinho.

## Direto ou por relay

O Tailscale tenta ligar cada aparelho **direto** ao servidor. Quando não consegue, passa por um servidor
intermediário do Tailscale (relay ou DERP). Funciona, mas é bem mais lento e ruim para vídeo, jogos e arquivos
grandes.

O **Resumo da rede** mostra, aparelho por aparelho, se a conexão está direta ou por relay. Também dá para ver no
próprio aparelho:

```
tailscale ping <nome-da-máquina>
```

A resposta `via <ip>:41641` indica conexão direta, e `via DERP(...)` indica relay. As causas mais comuns:

| Situação | O que fazer |
|---|---|
| Por relay até dentro de casa | Liberar a porta UDP `41641` no firewall do outro computador: [outros-computadores.md](outros-computadores.md) |
| Por relay só fora de casa | Redirecionar a porta UDP `41641` no roteador: [roteador.md](roteador.md#redirecionar-a-porta-do-tailscale) |
| Por relay no 4G mesmo com tudo acima feito | Algumas operadoras bloqueiam conexões diretas (CGNAT rígido). Não há o que fazer do lado da casa |
