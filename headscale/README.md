# Self-hosted Headscale mesh

This runs Headscale plus its embedded DERP/STUN service on a public Linux VPS.
The coordination server helps clients discover each other and attempt direct
WireGuard paths. If NAT traversal fails, encrypted WireGuard packets use DERP.
DERP is a relay, so it is not a direct route.

## Deploy the control plane on Render

`render.yaml` creates a free Headscale web service at
`https://connect-headscale.onrender.com`. The free service has an ephemeral
filesystem: its device database and private keys can be lost after a restart
or redeploy. Treat this as a temporary connectivity test, not a durable
control plane. Persistent storage on Render requires a paid plan.

Render web services do not expose inbound UDP, so this deployment disables
Headscale's embedded STUN/DERP. It still uses the public default DERP map for
encrypted fallback, and clients can still attempt direct WireGuard connections
to each other. If direct connectivity fails, packets go through DERP. Headscale
and its clients do not require a paid Tailscale control-plane subscription.

The Render container automatically creates the `connect` user and two
single-use preauth keys at startup. Find `CONNECT_DEVICE_1_AUTHKEY` and
`CONNECT_DEVICE_2_AUTHKEY` in the service's runtime logs. They expire after
24 hours; treat them as passwords and do not share or commit them. A service
restart may create fresh keys.

## Join Windows clients to the Render control plane

Install the official Tailscale Windows client on both computers. This is the
client software only; point it at your Headscale instance rather than the
paid Tailscale control plane. In elevated PowerShell on each computer, use
that computer's own one-time auth key:

```powershell
tailscale up --login-server https://connect-headscale.onrender.com --authkey YOUR_ONE_TIME_KEY --accept-routes=false --accept-dns=false
tailscale ip -4
```

The allocated `100.x.y.z` addresses form the private mesh. On the first
computer run the chat server:

```powershell
py -3 connect.py --port 8765
```

On the second computer connect to the first computer's mesh address:

```powershell
py -3 connect.py --connect 100.x.y.z --port 8765
```

If Windows Firewall blocks the connection, add this rule in elevated
PowerShell on the first computer:

```powershell
New-NetFirewallRule -DisplayName "Connect over Headscale" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -RemoteAddress 100.64.0.0/10
```

Run `tailscale ping DEVICE_NAME` to check the route. A `direct` response means
the WireGuard packets travel between the computers; `via DERP(...)` means they
are relayed. Headscale can coordinate discovery, but cannot force direct
connectivity through restrictive CGNAT or firewalls.

## Deploy on your own VPS instead

Use the VPS option below if you want Headscale's embedded DERP/STUN. It needs
a public IP and inbound UDP `3478`, which Render web services do not provide.
The VPS and domain may incur hosting costs.

## Server setup

Requirements: a Linux VPS with a public IPv4 address, Docker Compose, and a DNS
name whose A record points to that IPv4 address.

On the VPS, clone this repository and enter the deployment directory:

```sh
git clone https://github.com/Thieez/connect.git
cd connect/headscale
cp .env.example .env
```

Set `HEADSCALE_DOMAIN` in `.env` to your DNS name. Change
`server_url` at the top of `config.yaml` to `https://<your DNS name>`. In the
VPS firewall, allow inbound TCP `80` and `443`, and UDP `3478`. Start the
services:

```sh
docker compose up -d
docker compose exec headscale headscale health
```

Caddy obtains and renews the HTTPS certificate. The named Docker volumes keep
Headscale's database/keys and Caddy certificates across container restarts.
Back up the `headscale-data` volume; it contains the private identity keys for
the control server and DERP.

Create a mesh user, list users to obtain its numeric ID, then create a
single-use auth key for each computer:

```sh
docker compose exec headscale headscale users create connect
docker compose exec headscale headscale users list
docker compose exec headscale headscale preauthkeys create --user USER_ID
```

Treat each auth key as a password. Do not put it in source control or share it
in this chat.

## Join the two Windows computers

Install the official Tailscale client on both computers. This uses the client
to join your self-hosted Headscale server; it does not require signing up for
a paid Tailscale control plane.

Run PowerShell as Administrator on each computer, using its own one-time key:

```powershell
tailscale up --login-server https://YOUR_HEADSCALE_DOMAIN --authkey YOUR_ONE_TIME_KEY --accept-routes=false --accept-dns=false
tailscale status
tailscale ip -4
```

The two devices should appear in `tailscale status`. On one computer, start
the chat server:

```powershell
py -3 connect.py --port 8765
```

On the other, connect to the first computer's `100.x.y.z` address shown by
`tailscale ip -4`:

```powershell
py -3 connect.py --connect 100.x.y.z --port 8765
```

If Windows Firewall blocks the incoming connection, add an elevated rule
restricted to Tailscale's address range:

```powershell
New-NetFirewallRule -DisplayName "Connect over Headscale" -Direction Inbound -Action Allow -Protocol TCP -LocalPort 8765 -RemoteAddress 100.64.0.0/10
```

Check the route with `tailscale ping DEVICE_NAME`. A `direct` response means
WireGuard traffic goes between the computers. A `via DERP(...)` response
means it is encrypted but relayed. Headscale improves coordination and offers
a self-hosted relay, but no coordination system can guarantee a direct path
through every symmetric/restrictive CGNAT or firewall.
