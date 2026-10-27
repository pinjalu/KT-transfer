# This computer: private office setup

Prepared for the selected Windows computer on 27 October 2026. Current office
address: **192.168.0.149**, subnet **192.168.0.0/24**, port **8443**. Windows currently
classifies the Ethernet connection as Public. This procedure does not change that
network classification. Reserve this address in the office DHCP configuration;
if it changes, issue a new certificate for the new address.

## Certificate

`scripts/prepare_team_tls.py` creates a 90-day, self-signed server certificate for
this IP and localhost. It cannot issue other certificates. It does not install
trust or open network ports. The generated key stays on the hosting computer in
`data/team-tls/server-key.pem`. Never send that key to teammates or commit it.
Only distribute `team-public.cer` and the SHA-256 fingerprint in
`certificate-info.json` through your normal trusted team channel.

The prepared distribution copy is
[KT-Assistant-team-public.cer](../../outputs/team-release-2026-10-27/KT-Assistant-team-public.cer).
It expires on **25 January 2027**. Its SHA-256 fingerprint is:

```text
82B4083444010E5222C17F0CB4B98688B9F420C3C8E311C53142F9A8F2EFC3E7
```

If issuing a replacement, use a new directory; existing certificates are never
overwritten:

```powershell
.\.venv\Scripts\python.exe scripts\prepare_team_tls.py --ip 192.168.0.149 --output data\team-tls
```

On each teammate's Windows computer, inspect the certificate and compare its
SHA-256 fingerprint with the host's certificate-info file. Then the teammate can
trust this specific certificate for their Windows account:

```powershell
certutil -hashfile .\KT-Assistant-team-public.cer SHA256
Import-Certificate -FilePath .\KT-Assistant-team-public.cer -CertStoreLocation Cert:\CurrentUser\Root
```

Use the browser normally after installation; do not bypass certificate warnings.
Replace and redistribute the certificate before its recorded expiry. An IT-issued
certificate trusted by the team can replace this manual trust process later.

## Activate after local checks

Stop the current localhost server; the runtime lock prevents running two servers
against the same data directory. In PowerShell, from this project folder:

```powershell
.\Start-Team.ps1
```

It serves **https://192.168.0.149:8443**. Run under the original Windows account so
existing encrypted source credentials remain usable. Users sign in again because
sessions are bound to their origin. The owner creates member accounts from Account
settings. Each member starts with a separate workspace and supplies their own
source access. Local folders refer to the host computer and are owner-only.

If Windows blocks office access, the host administrator can add this narrowly
scoped inbound rule in an elevated PowerShell window after reviewing the address:

```powershell
New-NetFirewallRule -DisplayName 'KT Assistant office HTTPS 8443' -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8443 -LocalAddress 192.168.0.149 -RemoteAddress 192.168.0.0/24 -Profile Any
```

This permits only that port on that host address from that office subnet. Do not
configure router port forwarding. Remove the rule when retiring this deployment:

```powershell
Remove-NetFirewallRule -DisplayName 'KT Assistant office HTTPS 8443'
```

## Team acceptance and recovery

From a second office computer, verify the certificate has no warning, `/healthz`
returns `{"status":"ok"}`, protected pages require sign-in, and a member cannot
see the owner's saved project. Reconnect that member's chosen repository and ask
one question with inspectable citations. Only then record the network deployment
as complete. Local HTTPS tests alone do not establish office reachability.

The first release is manually started. Unattended startup, a backup schedule and
an off-host backup destination must be selected before relying on unattended
operation. Stop the server for backups. See [TASK_6_9.md](TASK_6_9.md) for creation,
verification and restoration into a separate directory. Preserve the original
Windows credential keys and the TLS key separately. A project backup does not
include the TLS certificate, `.env`, Ollama models or source repositories.
