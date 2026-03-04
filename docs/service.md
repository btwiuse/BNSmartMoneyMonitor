# Run As Service

## macOS `launchd`

Template file:

- `deploy/launchd/com.example.smartmoney.plist`

Before installing, replace these placeholders in the plist:

- `__LABEL__`
- `__PROJECT_ROOT__`
- `__PYTHON_BIN__`

### Install

```bash
mkdir -p ~/Library/LaunchAgents
cp deploy/launchd/com.example.smartmoney.plist ~/Library/LaunchAgents/com.example.smartmoney.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.smartmoney.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.smartmoney.plist
launchctl enable gui/$(id -u)/com.example.smartmoney
launchctl kickstart -k gui/$(id -u)/com.example.smartmoney
```

### Check Status

```bash
launchctl print gui/$(id -u)/com.example.smartmoney
```

### Stop

```bash
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.smartmoney.plist
```

### Restart After Config Change

```bash
cp deploy/launchd/com.example.smartmoney.plist ~/Library/LaunchAgents/com.example.smartmoney.plist
launchctl bootout gui/$(id -u) ~/Library/LaunchAgents/com.example.smartmoney.plist 2>/dev/null || true
launchctl bootstrap gui/$(id -u) ~/Library/LaunchAgents/com.example.smartmoney.plist
launchctl kickstart -k gui/$(id -u)/com.example.smartmoney
```

### Logs

Application logs:

- `logs/scheduler.log`
- `logs/collector.log`
- `logs/web.log`

`launchd` stdout/stderr:

- `logs/launchd.stdout.log`
- `logs/launchd.stderr.log`

Dashboard URL:

- `http://127.0.0.1:8765`

## Linux `systemd`

Template file:

- `deploy/systemd/smartmoney.service`

Before installing, replace:

- `User=CHANGE_ME`
- `/opt/smartmoney` with your actual project directory

### Install

```bash
sudo cp deploy/systemd/smartmoney.service /etc/systemd/system/smartmoney.service
sudo systemctl daemon-reload
sudo systemctl enable smartmoney.service
sudo systemctl restart smartmoney.service
```

### Check Status

```bash
sudo systemctl status smartmoney.service
```

### Logs

```bash
sudo journalctl -u smartmoney.service -f
```

## Notes

- The service runs `smart_signal.scheduler`, so collection and dashboard stay in one long-running process.
- The scheduler also starts the Binance Futures all-market ticker websocket stream by default and writes the latest snapshot to `data/futures_price_snapshot.json`.
- `--no-align-to-interval` is intentional here: after a reboot or crash, the process comes back immediately and then scheduler handles the next 5-minute cadence.
- Ensure `.tmp/` and `logs/` exist and that the service user can write to them.
- For public repositories, keep only template service files under version control. Put machine-specific copies in `~/Library/LaunchAgents/` or another local-only path.
