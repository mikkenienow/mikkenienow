# Fase 3 (celular <-> PC) com o laboratório dentro do WSL2.
# O WSL2 fica atrás de NAT: o Windows só encaminha localhost. Para outro dispositivo da rede alcançar a API é
# preciso (1) um portproxy do Windows para o IP do WSL e (2) uma regra de firewall. Requer PowerShell como Administrador.
#
#   .\scripts\phase3_windows.ps1 on     # abre a porta 8000 para a rede local (perfil Privado)
#   .\scripts\phase3_windows.ps1 off    # desfaz tudo
#   .\scripts\phase3_windows.ps1        # mostra o estado
#
# ATENÇÃO: a API do laboratório NÃO tem autenticação. Deixe ligado só durante o teste, numa rede em que você confia.
# O IP do WSL muda a cada reinício da distro: rode "on" de novo depois de um `wsl --shutdown`.
#
# Se o `wsl` falhar neste PowerShell ("Não é possível o acesso ao arquivo pelo sistema"), passe o IP à mão:
#   .\scripts\phase3_windows.ps1 on -WslIp 172.31.160.190      # o IP sai de `hostname -I` dentro do WSL
param([ValidateSet("on", "off", "status")][string]$Action = "status", [int]$Port = 8000, [string]$Distro = "Ubuntu",
      [string]$WslIp = "")
$rule = "Decision Lab (fase 3) $Port"
$admin = ([Security.Principal.WindowsPrincipal][Security.Principal.WindowsIdentity]::GetCurrent()).IsInRole(
  [Security.Principal.WindowsBuiltInRole]::Administrator)
if ($Action -ne "status" -and -not $admin) { Write-Host "Abra o PowerShell como Administrador para usar '$Action'." -ForegroundColor Red; exit 1 }

if ($Action -eq "on") {
  $wslIp = $WslIp
  if (-not $wslIp) { try { $wslIp = "$(wsl -d $Distro -- hostname -I 2>$null)".Trim().Split(" ")[0] } catch { $wslIp = "" } }
  if ($wslIp -notmatch '^\d{1,3}(\.\d{1,3}){3}$') {
    Write-Host "Não consegui o IP do WSL. Rode 'hostname -I' dentro do WSL e use: .\scripts\phase3_windows.ps1 on -WslIp <ip>" -ForegroundColor Red
    exit 1
  }
  netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 | Out-Null
  netsh interface portproxy add v4tov4 listenport=$Port listenaddress=0.0.0.0 connectport=$Port connectaddress=$wslIp
  # Qualquer perfil de rede (o Windows costuma marcar a Ethernet/Wi-Fi de casa como "Pública", e uma regra só
  # "Privada" não vale nela), mas só para quem está na mesma sub-rede ou na tailnet (Tailscale, 100.64.0.0/10).
  Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  New-NetFirewallRule -DisplayName $rule -Direction Inbound -Action Allow -Protocol TCP -LocalPort $Port -Profile Any `
    -RemoteAddress LocalSubnet, "100.64.0.0/10" | Out-Null
  "encaminhando 0.0.0.0:$Port -> ${wslIp}:$Port"
  "no WSL: HOST=0.0.0.0 scripts/lab.sh"
  Get-NetIPAddress -AddressFamily IPv4 | Where-Object { $_.PrefixOrigin -in "Dhcp", "Manual" -and $_.InterfaceAlias -notlike "vEthernet*" } |
    ForEach-Object { "no celular: http://$($_.IPAddress):$Port/   ($($_.InterfaceAlias))" }
}
elseif ($Action -eq "off") {
  netsh interface portproxy delete v4tov4 listenport=$Port listenaddress=0.0.0.0 | Out-Null
  Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue | Remove-NetFirewallRule
  "porta $Port fechada"
}
netsh interface portproxy show v4tov4
Get-NetFirewallRule -DisplayName $rule -ErrorAction SilentlyContinue | Select-Object DisplayName, Enabled, Profile | Format-Table -AutoSize
