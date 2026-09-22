# Startup routing

## Confirmed data flow

```text
packaged encrypted GameConfig                 CONFIRMED
  -> configs[0] selected by packageName       CONFIRMED
  -> Login_Url                                CONFIRMED
     http://ssl-x2zh1login-release.17m3.com
  -> POST /apply/connectInfo                  CONFIRMED
  -> POST /apply/address                      CONFIRMED
  -> result.data[0].ip / port                 CONFIRMED
  -> MarsNetManager.SetIP                     CONFIRMED
  -> MarsNet.SetConnect                       CONFIRMED
  -> SocketTcp.SetConnectEndPoint             CONFIRMED
  -> long-lived TCP connection                CONFIRMED
```

The base has scheme `http`, host
`ssl-x2zh1login-release.17m3.com`, implicit port `80`, and no base path.
Endpoints are appended as literal strings beginning with `/`. TLS is therefore
**Not Applicable** on this selected startup path.

## Safe local redirect design

The preferred unmodified-client design is an isolated emulator or VM with clean
application data:

1. Override only `ssl-x2zh1login-release.17m3.com` inside that guest so it
   resolves to a controlled host-only address.
2. Bind the local bootstrap service on guest-reachable TCP port 80.
3. Return a guest-reachable, controlled `ip` and port from `/apply/address`.
4. Apply deny-by-default egress in the guest network. Allow only the local
   bootstrap endpoint and local X2 TCP endpoint.
5. Verify the effective guest resolution, listeners and isolation evidence with
   `tools/first_contact_preflight.py` before launching the APK.

Do not change the workstation's permanent global hosts file. The original
hostname, override target, guest configuration location and rollback procedure
must be recorded with the run. The preflight never modifies hosts, firewall,
certificate stores or routing.

## Current status

No isolated Android guest or enforceable egress policy is available in the
current environment. Consequently no hostname override was applied and no
client was launched. Gate C is **Partial**; the design is concrete, but its
network-isolation premises have not been established.
