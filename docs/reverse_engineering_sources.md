# Reverse-engineering sources

| Conclusion | Status | Phase | External source | Evidence summary |
|---|---|---:|---|---|
| Core transport is long-lived TCP | CONFIRMED | 5 | `../phase5_output/protocol/transport.md` | `MarsNet` / `SocketTcp` send-receive path |
| Frame layout and totalLen rule | CONFIRMED | 5 | `../phase5_output/protocol/framing.md` | encoder/decoder symmetry at recovered RVAs |
| PackInt zigzag and 1–5 byte prefix | CONFIRMED | 5 | `../phase5_output/protocol/framing.md` | `marsnet.Encoding.PackInt/UnpackInt` |
| Header protobuf fields | CONFIRMED | 5 | `../phase5_output/protocol/message_schemas.json` | generated CommandX2 classes |
| Request sign is CRC32(body) | CONFIRMED | 5 | `../phase5_output/protocol/framing.md` | encoder call chain |
| Core message IDs | CONFIRMED | 5 | `../phase5_output/protocol/message_registry.csv` | `ERequestTypes` constants |
| Selected protobuf schemas | CONFIRMED | 5 | `../phase5_output/protocol/message_schemas.json` | Serialize/Deserialize methods |
| 16 MiB packet limit | TEMPORARY_COMPAT | 6 | `src/x2server/config/settings.py` | local defensive default, not original behavior |

Large inputs are intentionally not copied. See `reverse_data/README.md` for the external dependency index.

