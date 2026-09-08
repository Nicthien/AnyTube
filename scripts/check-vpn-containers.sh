#!/bin/bash
set -euo pipefail
# Run on an isolated Docker-capable Linux host. No production data is mounted.
root=$(cd "$(dirname "$0")/.." && pwd)
base=${ANYTUBE_TEST_OUTPUT:?Set an absolute directory for fixture logs}
mkdir -p "$base"
APP_IMAGE=${ANYTUBE_TEST_IMAGE:-anytube:0.6.0-preview}
docker build -f "$root/scripts/Dockerfile.network-test" -t anytube:network-test-060 "$root"
# Refuse existing resources before installing the cleanup trap.
for name in anytube060-vpn-client anytube060-vpn-server; do
  if docker inspect "$name" >/dev/null 2>&1; then echo "Existing test container: $name" >&2; exit 1; fi
done
if docker network inspect anytube060-vpn-test >/dev/null 2>&1; then echo 'Existing test network' >&2; exit 1; fi
work=$(mktemp -d "$base/vpn-fixture-XXXXXX")
chmod 700 "$work"
cleanup() {
  docker logs anytube060-vpn-client > "$base/vpn-client-last.log" 2>&1 || true
  chmod 644 "$base/vpn-client-last.log"
  docker rm -f anytube060-vpn-client anytube060-vpn-server >/dev/null 2>&1 || true
  docker network rm anytube060-vpn-test >/dev/null 2>&1 || true
  # Ephemeral test keys are removed by the test container; keep only logs.
  docker run --rm --network none -v "$work:/fixture" anytube:network-test-060 sh -c 'find /fixture -type f ! -name "*.log" -delete' >/dev/null 2>&1 || true
}
trap cleanup EXIT
public_flows() {
 docker run --rm --network anytube060-vpn-test --user 0:0 --entrypoint python -e TEST_PROXY=http://172.30.91.3:8888 -e PYTHONPATH=/app    -v "$root/app:/app/app:ro" -v "$root/scripts/check-public-flows.py:/app/check-public-flows.py:ro"    "$APP_IMAGE" /app/check-public-flows.py
}
route_check() {
  docker run --rm --network anytube060-vpn-test --entrypoint python -e TEST_PROXY=http://172.30.91.3:8888 -e ANYTUBE_SERVICE_MODE=1 \
    -v "$root/app:/app/app:ro" -v "$root/scripts/check-network-route.py:/app/check.py:ro" \
    "$APP_IMAGE" /app/check.py "$@"
}
docker network create --subnet 172.30.91.0/24 anytube060-vpn-test >/dev/null
docker run -d --name anytube060-vpn-server --network anytube060-vpn-test --ip 172.30.91.2 --cap-add NET_ADMIN --device /dev/net/tun --sysctl net.ipv4.ip_forward=1 -v "$work:/fixture" anytube:network-test-060 >/dev/null
mkdir -p "$work/public"
cp "$root/scripts/public-flow-fixture.py" "$work/public-flow-fixture.py"
docker run --rm --network none --user 0:0 --entrypoint ffmpeg -v "$work:/fixture" "$APP_IMAGE" -hide_banner -loglevel error -f lavfi -i color=c=blue:s=160x90:r=10 -f lavfi -i sine=frequency=440:sample_rate=44100 -t 2 -c:v libx264 -threads 1 -pix_fmt yuv420p -c:a aac /fixture/public/sample.mp4
docker run --rm --network none --user 0:0 --entrypoint ffmpeg -v "$work:/fixture" "$APP_IMAGE" -hide_banner -loglevel error -i /fixture/public/sample.mp4 -c copy -f mpegts /fixture/public/sample.ts
docker exec anytube060-vpn-server ip addr add 93.184.216.34/32 dev lo
docker exec -d anytube060-vpn-server sh -c 'python3 /fixture/public-flow-fixture.py > /fixture/public-http.log 2>&1'
if [ "${SKIP_WIREGUARD:-0}" != 1 ]; then
docker exec anytube060-vpn-server sh -ec '
  umask 077
  cd /fixture
  wg genkey > server.key; wg pubkey < server.key > server.pub
  wg genkey > client.key; wg pubkey < client.key > client.pub
  ip link add wg0 type wireguard
  ip addr add 10.77.0.1/24 dev wg0
  wg set wg0 listen-port 51820 private-key server.key peer "$(cat client.pub)" allowed-ips 10.77.0.2/32
  ip link set wg0 up
  iptables -t nat -A POSTROUTING -s 10.77.0.0/24 -o eth0 -j MASQUERADE
  mkdir wireguard
  printf "[Interface]\nPrivateKey = %s\nAddress = 10.77.0.2/32\n[Peer]\nPublicKey = %s\nEndpoint = 172.30.91.2:51820\nAllowedIPs = 0.0.0.0/0\nPersistentKeepalive = 5\n" "$(cat client.key)" "$(cat server.pub)" > wireguard/wg0.conf
'
docker run -d --name anytube060-vpn-client --network anytube060-vpn-test --ip 172.30.91.3 --cap-add NET_ADMIN --device /dev/net/tun -v "$work/wireguard:/gluetun/wireguard:ro" -e VPN_SERVICE_PROVIDER=custom -e VPN_TYPE=wireguard -e HTTPPROXY=on -e HTTPPROXY_LOG=off -e FIREWALL=on qmcgaw/gluetun:v3.41.3 >/dev/null
for i in $(seq 1 30); do
  if docker exec anytube060-vpn-server curl --silent --fail --max-time 5 --proxy http://172.30.91.3:8888 https://1.1.1.1/cdn-cgi/trace >/dev/null; then break; fi
  sleep 2
done
docker exec anytube060-vpn-server curl --silent --fail --max-time 15 --proxy http://172.30.91.3:8888 https://1.1.1.1/cdn-cgi/trace >/dev/null
docker exec anytube060-vpn-server sh -ec 'wg show wg0 latest-handshakes | awk "\$2>0 {found=1} END {exit !found}"'
echo WIREGUARD_TUNNEL_OK
route_check
public_flows
docker exec anytube060-vpn-server ip link set wg0 down
if docker exec anytube060-vpn-server curl --silent --fail --max-time 8 --proxy http://172.30.91.3:8888 https://1.1.1.1/cdn-cgi/trace >/dev/null; then echo VPN_FAIL_OPEN; exit 1; fi
echo WIREGUARD_FAIL_CLOSED_OK
route_check --expect-failure
docker logs anytube060-vpn-client > "$work/wireguard.log" 2>&1
docker rm -f anytube060-vpn-client >/dev/null
fi
docker exec anytube060-vpn-server sh -ec '
  cd /fixture; umask 077
  openssl req -x509 -newkey rsa:2048 -nodes -keyout ca.key -out ca.crt -subj /CN=AnyTubeFixtureCA -days 1 >/dev/null 2>&1
  for role in server client; do
    openssl req -newkey rsa:2048 -nodes -keyout "$role-tls.key" -out "$role.csr" -subj "/CN=AnyTubeFixture-$role" >/dev/null 2>&1
    printf "keyUsage=digitalSignature,keyEncipherment\nextendedKeyUsage=%sAuth\n" "$role" > "$role.ext"
    openssl x509 -req -in "$role.csr" -CA ca.crt -CAkey ca.key -CAcreateserial -out "$role.crt" -days 1 -extfile "$role.ext" >/dev/null 2>&1
  done
  printf "port 1194\nproto udp\ndev tun\nserver 10.78.0.0 255.255.255.0\ntopology subnet\nca /fixture/ca.crt\ncert /fixture/server.crt\nkey /fixture/server-tls.key\ndh none\ndata-ciphers AES-256-GCM\npush \"redirect-gateway def1\"\nkeepalive 5 20\nverb 3\n" > server.conf
  printf "client\ndev tun\nproto udp\nremote 172.30.91.2 1194\nnobind\nremote-cert-tls server\ndata-ciphers AES-256-GCM\nverb 3\n" > custom.conf
  for item in ca cert key; do
    case "$item" in ca) file=ca.crt;; cert) file=client.crt;; key) file=client-tls.key;; esac
    printf "<%s>\n" "$item" >> custom.conf
    cat "$file" >> custom.conf
    printf "</%s>\n" "$item" >> custom.conf
  done
  iptables -t nat -A POSTROUTING -s 10.78.0.0/24 -o eth0 -j MASQUERADE
  openvpn --config server.conf --daemon --writepid /fixture/openvpn.pid --log /fixture/openvpn-server.log
'
docker run -d --name anytube060-vpn-client --network anytube060-vpn-test --ip 172.30.91.3 --cap-add NET_ADMIN --device /dev/net/tun -v "$work/custom.conf:/gluetun/custom.conf:ro" -e VPN_SERVICE_PROVIDER=custom -e VPN_TYPE=openvpn -e OPENVPN_CUSTOM_CONFIG=/gluetun/custom.conf -e HTTPPROXY=on -e HTTPPROXY_LOG=off -e FIREWALL=on qmcgaw/gluetun:v3.41.3 >/dev/null
for i in $(seq 1 30); do
  if docker exec anytube060-vpn-server curl --silent --fail --max-time 5 --proxy http://172.30.91.3:8888 https://1.1.1.1/cdn-cgi/trace >/dev/null; then break; fi
  sleep 2
done
docker exec anytube060-vpn-server curl --silent --fail --max-time 15 --proxy http://172.30.91.3:8888 https://1.1.1.1/cdn-cgi/trace >/dev/null
echo OPENVPN_TUNNEL_OK
route_check
public_flows
docker exec anytube060-vpn-server sh -c 'kill $(cat /fixture/openvpn.pid)'
if docker exec anytube060-vpn-server curl --silent --fail --max-time 8 --proxy http://172.30.91.3:8888 https://1.1.1.1/cdn-cgi/trace >/dev/null; then echo VPN_FAIL_OPEN; exit 1; fi
echo OPENVPN_FAIL_CLOSED_OK
route_check --expect-failure
docker logs anytube060-vpn-client > "$work/openvpn.log" 2>&1
echo VPN_FIXTURES_COMPLETE
