# Android lab tools

These utilities inspect the disposable X2 Android lab. They do not download an
SDK, install drivers, modify hosts/firewall settings, install an APK, or start
the client.

- `android_preflight.py` is a read-only, fail-closed check for the expected AVD,
  package, clean-state evidence, guest hostname override, local listeners and
  deny-by-default isolation record.

The preflight must print `SAFE_TO_RUN=true` before any future First Contact
launcher may start the APK. An evidence JSON file is runtime state and must not
be committed.
