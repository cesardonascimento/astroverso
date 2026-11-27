# Backup de um PC com Windows (sem Astroverso)

O Astroverso não roda no Windows, mas o PC pode mandar backups de pastas para o vault da casa do mesmo
jeito que os apps: com o [restic](https://restic.net) e uma tarefa agendada. É o PC que manda (o servidor nunca busca),
criptografado, só acrescentando versões. O servidor acompanha o PC como qualquer outra máquina: resumo, aviso de 36 h
sem backup e a manutenção de domingo (30 diárias e 12 mensais).

## 1. Cadastrar o PC no servidor

No gerenciador do Astroverso, na máquina do servidor: **backup → Adicionar uma máquina**, com o nome do PC (ex.:
`<nome-da-máquina>`). Anote:

- a **senha de acesso** e a **senha do repositório** (guarde as duas no gerenciador de senhas: veja
  [senhas.md](senhas.md));
- as linhas **repositório em `<pasta>`: `rest:https://vault.<domínio>/<nome-da-máquina>/<id>/`**, uma por pasta de
  destino. Cada pasta do PC vai para o repositório da pasta do vault que você escolher.

Os mesmos dados aparecem depois em **Mostrar os dados de uma máquina**.

## 2. Preparar a pasta no PC

Tudo no PowerShell **como administrador**.

1. Crie a pasta e deixe só os administradores e o sistema entrarem nela (as senhas ficam aqui):

   ```powershell
   New-Item -ItemType Directory -Force C:\ProgramData\Astroverso\backup
   icacls C:\ProgramData\Astroverso\backup /inheritance:r /grant:r "*S-1-5-32-544:(OI)(CI)F" "*S-1-5-18:(OI)(CI)F"
   ```

2. Baixe o `restic_<versão>_windows_amd64.zip` da página de versões do restic
   (<https://github.com/restic/restic/releases>), extraia o `.exe` para a pasta e renomeie para `restic.exe`.

3. Grave as duas senhas, cada uma num arquivo de uma linha. O `Read-Host` pede a senha sem mostrar e sem guardar no
   histórico do PowerShell (nunca escreva a senha no próprio comando):

   ```powershell
   $Senha = Read-Host "senha de acesso" -AsSecureString
   [Net.NetworkCredential]::new("", $Senha).Password | Set-Content -NoNewline C:\ProgramData\Astroverso\backup\acesso.txt
   $Senha = Read-Host "senha do repositorio" -AsSecureString
   [Net.NetworkCredential]::new("", $Senha).Password | Set-Content -NoNewline C:\ProgramData\Astroverso\backup\senha.txt
   Remove-Variable Senha
   ```

## 3. Os dois arquivos do backup

Crie `C:\ProgramData\Astroverso\backup\ambiente.ps1` (os dados de acesso, usados pelo backup e pela restauração):

```powershell
$Maquina = "<nome-da-máquina>"
$Restic = "$PSScriptRoot\restic.exe"
$env:RESTIC_REST_USERNAME = $Maquina
$env:RESTIC_REST_PASSWORD = Get-Content "$PSScriptRoot\acesso.txt" -TotalCount 1
$env:RESTIC_PASSWORD_FILE = "$PSScriptRoot\senha.txt"
```

E `C:\ProgramData\Astroverso\backup\backup.ps1`, com uma linha `Guardar` por pasta do PC:

```powershell
. "$PSScriptRoot\ambiente.ps1"
$Falhou = $false

function Guardar($Repositorio, $Pasta, $Nome) {
    $env:RESTIC_REPOSITORY = $Repositorio
    & $Restic cat config *> $null
    if ($LASTEXITCODE -ne 0) { & $Restic init *>> "$PSScriptRoot\backup.log" }
    & $Restic backup $Pasta --use-fs-snapshot --host $Maquina --tag astroverso --tag app:windows --tag "dados:$Nome" *>> "$PSScriptRoot\backup.log"
    if ($LASTEXITCODE -ne 0) { $script:Falhou = $true }
}

Guardar "rest:https://vault.<domínio>/<nome-da-máquina>/<id>/" "D:\Fotos" "fotos"
Guardar "rest:https://vault.<domínio>/<nome-da-máquina>/<id>/" "C:\Users\<você>\Documents" "documentos"

if ($Falhou) { exit 1 }
```

- **O repositório** é uma das linhas do passo 1: escolha, para cada pasta, a pasta do vault dela. A mesma pasta do
  PC pode ir para mais de uma (uma linha `Guardar` para cada repositório).
- **O nome** (`fotos`, `documentos`) vira a etiqueta `dados:<nome>`: cada pasta é uma série de versões própria, e o
  resumo do servidor mostra `windows (fotos)`. Use um nome sem vírgula e não troque depois (trocar começa uma série
  nova).
- `--use-fs-snapshot` lê a pasta num snapshot do Windows (VSS): entram também os arquivos abertos.
- Caminho com acento: salve os dois arquivos como **UTF-8 com BOM** (no Bloco de Notas: Salvar como → Codificação),
  senão o PowerShell lê os acentos errado.

## 4. Testar

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File C:\ProgramData\Astroverso\backup\backup.ps1
Get-Content -Tail 20 C:\ProgramData\Astroverso\backup\backup.log
```

O fim do log mostra `snapshot <id> saved` para cada pasta. No servidor, o **Resumo dos backups** passa a mostrar o PC
com `windows (<nome>)`. A primeira vez demora (manda tudo); as seguintes mandam só o que mudou.

## 5. Agendar

Todo dia às 02:30, como o sistema (o snapshot pede administrador), e logo ao ligar se o PC estava desligado na hora:

```powershell
$Acao = New-ScheduledTaskAction -Execute "powershell.exe" -Argument '-NoProfile -ExecutionPolicy Bypass -File "C:\ProgramData\Astroverso\backup\backup.ps1"'
$Quando = New-ScheduledTaskTrigger -Daily -At 02:30
$Quem = New-ScheduledTaskPrincipal -UserId "SYSTEM" -LogonType ServiceAccount -RunLevel Highest
$Como = New-ScheduledTaskSettingsSet -StartWhenAvailable -ExecutionTimeLimit (New-TimeSpan -Hours 12)
Register-ScheduledTask -TaskName "Astroverso backup" -Action $Acao -Trigger $Quando -Principal $Quem -Settings $Como
```

Um PC desligado por mais de 36 h aparece no `#vault` como "sem backup": é o aviso de que as versões pararam.

## Restaurar

No PowerShell como administrador, com o repositório onde está a versão:

```powershell
. C:\ProgramData\Astroverso\backup\ambiente.ps1
$env:RESTIC_REPOSITORY = "rest:https://vault.<domínio>/<nome-da-máquina>/<id>/"
& $Restic snapshots --tag dados:fotos
& $Restic restore <id da versão> --target D:\Restaurado
```

A versão vem numa pasta nova (`D:\Restaurado\...`, com o caminho original dentro): copie dela o que precisar.

## Atualizar o restic

```powershell
& C:\ProgramData\Astroverso\backup\restic.exe self-update
```

## Remover

```powershell
Unregister-ScheduledTask -TaskName "Astroverso backup" -Confirm:$false
Remove-Item -Recurse -Force C:\ProgramData\Astroverso\backup
```

Isso apaga a tarefa, o restic e as senhas do PC. Os backups continuam no servidor. Para o servidor parar de esperar
o PC: **backup → Descadastrar máquinas** (os repositórios dele ficam nas pastas do vault).
