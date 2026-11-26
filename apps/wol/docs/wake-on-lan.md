# Wake-on-LAN: o que ligar em cada máquina

O app `wol` manda o "pacote mágico" pela rede de casa: a placa de rede da máquina desligada o reconhece e liga o
computador. Para isso, a máquina precisa estar **no cabo**, na mesma rede do servidor do Astroverso (o pacote não passa
por roteadores nem pelo Tailscale), com o Wake-on-LAN ligado na BIOS e na placa de rede.

## Reserva de IP no roteador

No roteador, reserve um IP fixo para a máquina (pelo MAC da placa de rede, em "DHCP" ou "Reserva de endereço"). O app
confere se a máquina ligou pelo IP: se ele mudar, o app manda o pacote, mas não vê a máquina responder.

## BIOS

Entre na BIOS (tecla `Del` ou `F2` ao ligar) e procure, conforme o fabricante:

- **Wake on LAN**, **Power On By PCI-E**, **Resume by PCI-E Device** ou **Wake Up Event by LAN**: ligado.
- **ErP** ou **EuP Ready** (economia de energia desligada): **desligado**. Com ele ligado, a placa de rede fica sem
  energia com a máquina desligada.
- Em notebooks, o Wake-on-LAN costuma funcionar só na tomada.

## Windows

1. **Gerenciador de Dispositivos** → **Adaptadores de rede** → a placa com cabo → **Propriedades**:
   - aba **Gerenciamento de Energia**: marque **Permitir que este dispositivo ligue o computador** e **Permitir apenas
     que um pacote mágico ligue o computador**;
   - aba **Avançado**: **Wake on Magic Packet** (ou parecido) em **Ativado**.
2. **Painel de Controle** → **Opções de Energia** → **Escolher a função dos botões de energia** → **Alterar
   configurações não disponíveis no momento** → desmarque **Ligar inicialização rápida**. Com ela, o Windows desliga num
   modo em que algumas placas não acordam.
3. **Responder ao ping** (para o app ver que a máquina ligou), no PowerShell como administrador:

   ```powershell
   Enable-NetFirewallRule -Name FPS-ICMP4-ERQ-In
   ```

## Linux

```bash
sudo ethtool <placa> | grep Wake-on      # "g" = pacote mágico ligado
sudo nmcli connection modify <conexão> 802-3-ethernet.wake-on-lan magic
```

## Testar

Desligue a máquina, espere uns segundos e, no gerenciador do Astroverso, **wol → Ligar uma máquina** (ou
`/astro wol:ligar-<nome>` no Discord). O app manda o pacote a cada 4 segundos e avisa quando a máquina responde ao
ping, ou depois de 3 minutos sem resposta.
