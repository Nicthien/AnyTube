# Site sessions and outgoing network

The [0.6.0 validation report](VALIDATION-0.6.0.md#english) describes tested paths. This change does not announce compatibility with any particular public site.

## Interactive sessions

**Open session** presents remote Chromium inside AnyTube, with the address visible. Users perform site checks themselves. AnyTube does not automatically accept age checks or manufacture a successful verification. Clicks, keyboard input and displayed QR codes are available; Escape returns focus to AnyTube controls. A separate text field supports mobile keyboards.

Camera, microphone, secondary windows and site WebSockets are unsupported. GET navigation redirects and POST-to-GET redirects are handled; redirects requiring an upload replay are refused. These limits may prevent some sign-in or verification flows.

Explicitly saving a session preserves the selected site's cookies, localStorage and IndexedDB, encrypted using the existing vault. Cross-site identity-provider state remains temporary; sessionStorage is not restored. Retention is at most 30 days after explicit validation, with no sliding extension during searches. Sites may expire their own sessions earlier. Live browsers close after 15 minutes of inactivity, with one per account and two per server. Saved sessions can be renewed or deleted.

For manual uploads, first select the site's file field, then choose a PDF, JPEG or PNG in AnyTube, up to 20 MiB. Transfer uses memory. The service erases its copy after transfer; Chromium's input retains the selection until form submission or context closure. No file, keystroke or screen is stored in diagnostics.

Resuming discovery reloads responses and repeats validation using the remaining budget. Search and extraction workers can receive scoped cookies, never browser-control credentials. Authentication that needs JavaScript storage does not automatically work with yt-dlp. Search, video-page recognition, extraction and playback remain separate capabilities.

## Docker setup

Merge `compose.unraid.yaml` and `compose.interactive.yaml`. Configure distinct server-only `ANYTUBE_INTERACTIVE_TOKEN` and `ANYTUBE_BROWSER_EGRESS_TOKEN` secrets. Do not commit them. No browser/CDP port is published; temporary browser data stays on memory-backed filesystems.

`deploy/chromium-seccomp.json` is the Playwright 1.62 profile needed for Chromium's namespace sandbox. Do not substitute `--no-sandbox`. Set `ANYTUBE_CHROMIUM_SECCOMP` to an absolute profile path when Compose runs from another directory. The browser resolves its configured Docker gateway at startup, then blocks DNS and all connections outside that gateway.

Existing Browserless settings are preserved. Integrated Chromium handles saved sessions, proxy/VPN observation, and observation when no other browser was configured.

## Proxy and optional VPN

Administrator-only **Outgoing network** offers Direct, HTTP/HTTPS proxy and integrated VPN. Direct remains the initial mode. The proxy needs a numeric IP bootstrap, with an optional TLS certificate name for HTTPS; TLS verification stays enabled. Credentials are encrypted. The network test reports reachability and observed public IP, not universal leak-test coverage.

In proxy/VPN mode, public DNS uses HTTPS through the selected proxy. CONNECT requests target validated numeric addresses. Private or mixed public/private answers and public ports other than 80/443 are refused. There is no automatic Direct fallback. Explicitly configured internal services keep their administrator-controlled internal route. Media, subtitles and thumbnails are relayed by AnyTube; third-party frames and direct media loads are blocked. Route changes invalidate connections and require session revalidation, while the application UI remains available.

Merge `compose.vpn.yaml` only after preparing server parameters. Its `vpn` profile is opt-in and uses `qmcgaw/gluetun:v3.41.3`, with firewall enabled and no published port.

Configure `ANYTUBE_VPN_TYPE` (`wireguard` or `openvpn`), `ANYTUBE_VPN_CONFIG` (absolute server-side config path), and non-conflicting `ANYTUBE_VPN_SUBNET` / `ANYTUBE_VPN_IP` (defaults `172.30.90.0/24` / `172.30.90.3`). Optional OpenVPN credentials use `ANYTUBE_OPENVPN_USER` / `ANYTUBE_OPENVPN_PASSWORD`; proxy authentication uses `ANYTUBE_VPN_PROXY_USER` / `ANYTUBE_VPN_PROXY_PASSWORD`.

The `vpn-config` service validates the file before copying it to Gluetun's volume. OpenVPN scripts, plugins, remote management and arbitrary includes are refused. Certificates and keys must use inline blocks; external file references are refused. WireGuard accepts one interface and peer, without system hooks. The French guide contains format examples with placeholders only. After explicitly starting the profile, select VPN in AnyTube and test its HTTP proxy, usually `http://172.30.90.3:8888`. The protocol field describes the configured service; it does not rewrite provider settings.

## Reports and delivery gates

Diagnostic ZIP exports include access/session states and route revision, excluding session access identifiers, cookies, storage, documents, screens and secrets. Public URLs and search terms remain included.

Validation scripts include `check-interactive-browser.py`, `check-source-diagnostics.py`, `check-source-diagnostics-ui.py`, `check-network-route.py` and `check-integrated-stack.py`. The last script refuses environments other than `validation-060` and creates an ephemeral account: never run it against production data.

Publication requires the completed validation report, including outage and isolation tests. Fixture success does not establish compatibility with a public site or guarantee that its age-verification service accepts a remote browser.
