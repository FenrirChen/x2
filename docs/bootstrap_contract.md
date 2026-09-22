# X2 2.4 bootstrap contract

Status: **Gate A/B Done (static contract closure)**. The shapes below are built
from X2 2.4 IL2CPP evidence, not retired-service traffic. Concrete localhost
values are `TEMPORARY_COMPAT`; field names and parser edges marked CONFIRMED are
client facts.

## Two-stage contract

| Stage | Request | Response | Evidence |
|---|---|---|---|
| Connect info | `POST {Login_Url}/apply/connectInfo`, form fields `packageName`, `fromCH`, `adChannel`, `adSubChannel`, `lebianVersion`, 3 s timeout | JSON `result` object | CONFIRMED |
| Server address | `POST {Login_Url}/apply/address`, form fields `clientType`, `timestamp`, `sign`, 30 s timeout | JSON `result.data[]` | CONFIRMED |

`Login_Url` is a field in the selected local `GameConfig.txt` row. Phase 9
resolved the effective value for `com.siva.project.x2` as
`http://ssl-x2zh1login-release.17m3.com`. Despite its name it is an HTTP base
URL. `AppConfig.LoadGameConfigSuccess` constructs
`ServerConfigUrl = Login_Url + "/apply/connectInfo"` and
`Server_Url = Login_Url + "/apply/address"`. The selected base has no path,
uses implicit port 80, and the endpoints are literal leading-slash suffixes.
TLS is **Not Applicable** for this effective row.

Both requests use `UnityWebRequest.Post(url, Dictionary<string,string>)`.
Therefore form encoding is CONFIRMED. No custom request-header setter is present
in either inspected path; the exact generated header set is treated as
`UNITYWEBREQUEST_POST_DEFAULTS`, not an invented official requirement.

For `/apply/address`, the request sign is:

```text
MD5(clientType + timestamp + GameConst.Server_Key)
```

This HTTP sign is unrelated to the packet-body CRC32 and fight sign.

## Connect-info response

```json
{
  "result": {
    "serviceAppId": "x2-local-compat",
    "pbsServer": "http://127.0.0.1:18080",
    "loginServer": "http://127.0.0.1:18080",
    "accountServer": "http://127.0.0.1:18080",
    "eswebServer": "http://127.0.0.1:18080",
    "lbPbsServer": ["http://127.0.0.1:18080"],
    "lbLoginServer": ["http://127.0.0.1:18080"],
    "lbEswebServer": ["http://127.0.0.1:18080"],
    "areaId": "local"
  }
}
```

| Field | Client destination | Static evidence | Level |
|---|---|---|---|
| `result` | inner configuration object | `LoadWebGameConfig.MoveNext` `0x17E8824–0x17E883C` | CONFIRMED |
| `serviceAppId` | `GameConst.DefaultHttpServiceAppId` | `0x17E8848–0x17E889C` | CONFIRMED |
| `pbsServer` | `GameConst.DefaultHttpServiceUrl` | `0x17E88A8–0x17E88D8` | CONFIRMED |
| `loginServer` | `GameConst.Login_App` | `0x17E88E4–0x17E8914` | CONFIRMED |
| `accountServer` | `GameConst.Login_Server` | `0x17E8920–0x17E8950` | CONFIRMED |
| `eswebServer` | `GameConst.Search_Server` | `0x17E895C–0x17E8990` | CONFIRMED |
| `lbPbsServer` | `DefaultHttpServiceUrl_List` | `0x17E89BC–0x17E8A5C` | CONFIRMED |
| `lbLoginServer` | `Login_App_List` | `0x17E89DC–0x17E8A88` | CONFIRMED |
| `lbEswebServer` | `Search_Server_List` | `0x17E8A04–0x17E8AB4` | CONFIRMED |
| `areaId` | area/config static | `0x17E8AC0–0x17E8B14` | CONFIRMED |

The three scalar URLs are inserted at index zero of their corresponding lists.
A non-empty body then advances the startup FSM to state 5. No TCP endpoint is
read from this response.

## Server-address response and TCP sink

Minimal response:

```json
{
  "result": {
    "data": [
      {"ip": "127.0.0.1", "port": 29000, "weight": 0, "zid": 1, "des": "local"}
    ]
  }
}
```

`result.data` is iterated by `ServerIPModule._getServerIP.MoveNext`
(`0x1786150` onward). Each object becomes `ServerIPModule.IPData`:

| JSON field | Model field | Default when absent | Evidence |
|---|---|---:|---|
| `ip` | `IPData.ip` | empty | CONFIRMED, `0x178623C–0x1786328` |
| `port` | `IPData.port` | `0` | CONFIRMED, `0x178634C–0x178643C` |
| `weight` | `IPData.weight` | `0` | CONFIRMED, `0x1786460–0x1786554` |
| `zid` | `IPData.zid` | `1` | CONFIRMED, `0x178657C–0x1786670` |
| `des` | `IPData.desc` | empty | CONFIRMED, `0x1786698–0x178676C` |

For a minimal contract, `ip` and `port` are operationally required even though
the parser has empty/zero fallbacks. Use exactly one endpoint to avoid relying on
the still-unresolved multi-entry weight ordering.

Data flow to the socket is fully confirmed:

```text
HTTP response bytes
  -> LitJson.JsonMapper.ToObject
  -> result.data[0].ip / port
  -> ServerIPModule.IPData
  -> MarsNetManager.SetIP(ip, port)        0x1786CA0–0x1786D38
  -> MarsNet.SetConnect(ip, port)          0x141ABF4–0x141AC48
  -> MarsNet.Start
  -> SocketTcp.SetConnectEndPoint          0x3E4BBF8–0x3E4BC18
  -> SocketTcpProcess.Start
```

## Remaining unknowns

- The local-routing mechanism needed to make the unmodified APK reach a local
  port-80 service has not been deployed in an isolated Android guest. The APK
  has not been patched.
- Multi-entry weight ordering beyond the observed sort-then-first-item path.
- Full operational semantics of `areaId`, service URLs, and address `zid`.

These unknowns do not prevent construction and offline testing of the minimal
two-response contract, but missing deny-by-default guest isolation prevents a
safe First Contact run.
