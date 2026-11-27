$ErrorActionPreference = 'Stop'
$ProgressPreference = 'SilentlyContinue'
try {
    $base = Join-Path $env:ProgramData 'Astroverso'
    $link = Join-Path $base 'snapshot-__NOME__'
    $ids = Join-Path $base 'snapshot-__NOME__.txt'
    New-Item -ItemType Directory -Force -Path $base | Out-Null

    if (Get-Item -LiteralPath $link -Force -ErrorAction SilentlyContinue) {
        cmd /c rmdir "$link" | Out-Null
    }
    if (Test-Path -LiteralPath $ids) {
        foreach ($id in Get-Content -LiteralPath $ids) {
            Get-CimInstance Win32_ShadowCopy | Where-Object { $_.ID -eq $id } | Remove-CimInstance
            Write-Output "snapshot $id apagado"
        }
        Remove-Item -LiteralPath $ids
    }

    if ('__ACAO__' -eq 'criar') {
        if (-not (Test-Path -LiteralPath '__DRIVE__:\')) {
            throw 'disco __DRIVE__: nao encontrado'
        }
        $result = Invoke-CimMethod -ClassName Win32_ShadowCopy -MethodName Create -Arguments @{ Volume = '__DRIVE__:\'; Context = 'ClientAccessible' }
        if ($result.ReturnValue -ne 0) {
            $motivos = @{
                1 = 'sem permissao de administrador'
                3 = 'disco nao encontrado'
                4 = 'disco nao suportado (o snapshot so funciona em NTFS ou ReFS)'
                6 = 'sem espaco para o snapshot'
                7 = 'disco em uso por outro snapshot'
                9 = 'outro snapshot sendo criado agora'
                11 = 'o servico de Copias de Sombra de Volume nao respondeu'
            }
            $motivo = $motivos[[int]$result.ReturnValue]
            if (-not $motivo) { $motivo = 'erro desconhecido' }
            throw "o Windows recusou o snapshot do disco __DRIVE__: $motivo (codigo $($result.ReturnValue))"
        }
        Add-Content -LiteralPath $ids -Value $result.ShadowID
        $shadow = Get-CimInstance Win32_ShadowCopy | Where-Object { $_.ID -eq $result.ShadowID }
        cmd /c mklink /d "$link" "$($shadow.DeviceObject)\" | Out-Null
        if (-not (Test-Path -LiteralPath "$link\")) {
            throw 'snapshot criado, mas a pasta dele nao abre'
        }
        Write-Output "snapshot $($result.ShadowID) do disco __DRIVE__: em $link"
    }
} catch {
    Write-Output "erro: $($_.Exception.Message)"
    exit 1
}
