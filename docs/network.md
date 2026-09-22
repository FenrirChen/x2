# M2 network boundary

## Call path

```text
localhost client
  → asyncio TCP listener (X2TCPServer)
  → X2Connection.read loop
  → existing PacketStreamDecoder.feed
  → 0..N DecodedPacket values
  → Dispatcher: message ID → registry → optional handler
  → optional OutboundMessage
  → existing ProtocolCodec + ResponseHeader
  → StreamWriter.write + await drain
```

The network layer does not duplicate PackInt, framing, protobuf or CRC code. It does not own Login, Player, Guide, Fight or database state.

## Lifecycle

`X2TCPServer.start` binds the configured address, defaulting to `127.0.0.1`. Each accepted socket receives an independent process-local connection ID, `SessionState` and decoder. Connection ID, network session ID and future player ID are separate concepts.

EOF, reset, timeout and protocol errors close only the affected connection. EOF with buffered incomplete bytes is logged. `stop` first closes the listener, then active writers, waits for owned tasks and cancels only tasks that fail to finish inside the configured shutdown interval.

Reads use the lower of `read_timeout` and `idle_timeout`. Writes always call `writer.write` followed by `await writer.drain` under `write_timeout`. The packet-size limit remains the M1 `TEMPORARY_COMPAT` setting.

## Dispatcher behavior

- Known message with an explicitly registered handler: call handler; send its optional registered response.
- Known message without a handler, including `C2L_Login` 54: log metadata and return no response.
- Unknown message ID: log a protocol warning and return no response.
- Malformed frame, invalid CRC or oversized length: close the current connection without crashing the listener.

No message body or token is logged. Context includes connection ID, peer, message ID/name and request ID.

## Configuration

| Environment variable | Default |
|---|---:|
| `X2_TCP_HOST` | `127.0.0.1` |
| `X2_TCP_PORT` | `0` (ephemeral development port) |
| `X2_READ_TIMEOUT` | `30` seconds |
| `X2_WRITE_TIMEOUT` | `10` seconds |
| `X2_IDLE_TIMEOUT` | `120` seconds |
| `X2_MAX_CONNECTIONS` | `128` |
| `X2_MAX_PACKET_SIZE` | `16777216` bytes |

## Test scope

All socket tests use automated localhost clients and synthetic frames. They cover clean connect/close, response correlation, fragmentation, concatenation, partial packets, bad CRC isolation, malformed/oversized lengths, incomplete EOF and graceful shutdown. No original client or retired service is used.

