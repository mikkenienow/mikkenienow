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
param([ValidateSet("on", "off", "status")][string]$Action = "status", [int]$Port = 8000, [string]$Distro = "Ubuntu")
$rule = "Decision Lab (fase 3) $Port"

if ($Action -eq "on") {
  $wslIp = (wsl -d $Distro -- hostname -I).Trim().Split(" ")[0]
  if (-not $wslIp) { throw "não consegui o IP do WSL ($Distro)" }
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
