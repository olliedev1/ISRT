# ISRT – Insurgency Sandstorm RCON Tool

A command-line tool for remotely administering **Insurgency: Sandstorm** game
servers via the [Source RCON Protocol](https://developer.valvesoftware.com/wiki/Source_RCON_Protocol).

---

## Features

- **Interactive shell** – real-time RCON session with command history
- **Single-command execution** – run one RCON command from your shell script
- **Named connection profiles** – save host/port/password so you don't repeat yourself
- **Convenience shortcuts** – `players`, `broadcast`, `map`, `kick`, `ban`
- Pure Python, no dependencies beyond [`click`](https://click.palletsprojects.com/)

---

## Requirements

- Python 3.8+
- `click` ≥ 8.0 (installed automatically)

---

## Installation

```bash
pip install .
```

Or install in editable/development mode:

```bash
pip install -e ".[dev]"
```

---

## Quick-start

### 1. Save a profile (optional but convenient)

```bash
isrt profile save myserver --host 192.168.1.100 --port 27015 --password secret
```

Set it as the default so you don't need `--host`/`--password` every time:

```bash
isrt profile save myserver --host 192.168.1.100 --password secret --set-default
```

### 2. List connected players

```bash
isrt players
# or without a saved profile:
isrt players --host 192.168.1.100 --password secret
```

### 3. Execute any RCON command

```bash
isrt exec AdminListPlayers
isrt exec "AdminBroadcast Server restarting in 5 minutes"
```

### 4. Start an interactive shell

```bash
isrt shell
```

```
Connected to 192.168.1.100:27015  (type 'exit' or Ctrl-D to quit)
rcon> AdminListPlayers
0. PlayerOne (SteamID: 76561198xxxxxxxxx) Team 0
1. PlayerTwo (SteamID: 76561198yyyyyyyyy) Team 1
rcon> exit
Disconnected.
```

---

## Commands

| Command | Description |
|---|---|
| `isrt exec COMMAND…` | Execute one RCON command and print the response |
| `isrt shell` | Interactive RCON session |
| `isrt players` | List connected players (`AdminListPlayers`) |
| `isrt broadcast MESSAGE…` | Broadcast a message (`AdminBroadcast`) |
| `isrt map MAP_NAME` | Change the map (`AdminChangeLevel`) |
| `isrt kick PLAYER [REASON]` | Kick a player (`AdminKick`) |
| `isrt ban PLAYER [REASON]` | Permanently ban a player (`AdminBan`) |
| `isrt profile save NAME` | Save a connection profile |
| `isrt profile list` | List saved profiles |
| `isrt profile delete NAME` | Delete a profile |
| `isrt profile default NAME` | Set the default profile |

### Connection flags (available on all connection commands)

| Flag | Short | Default | Description |
|---|---|---|---|
| `--host` | `-H` | | Server hostname or IP |
| `--port` | `-p` | `27015` | RCON port |
| `--password` | `-P` | | RCON password (prompted if omitted) |
| `--timeout` | `-t` | `10.0` | Socket timeout (seconds) |
| `--profile` | `-r` | | Use a saved profile |

---

## Common Insurgency: Sandstorm RCON Commands

| Command | Description |
|---|---|
| `AdminListPlayers` | List all connected players |
| `AdminKick <Name> <Reason>` | Kick a player |
| `AdminBan <Name> <Reason> 0` | Permanently ban a player |
| `AdminChangeLevel <Map>` | Change the map |
| `AdminRestartLevel` | Restart the current map |
| `AdminBroadcast <Message>` | Send a message to all players |
| `AdminPauseMatch` / `AdminUnpauseMatch` | Pause or unpause the match |
| `AdminEndMatch` | End the current match |
| `AdminSetBotQuota <N>` | Set number of bots |
| `AdminForceTeam <Name> <0\|1>` | Move a player to Security (0) or Insurgents (1) |
| `AdminHelp` | Show all available admin commands |

---

## Enabling RCON on your server

Add the following to your server's startup parameters or `Engine.ini`:

```
-Port=27015
-QueryPort=27016
-RCON=true
-RCONPort=27015
-RCONPassword=YourSecretPassword
```

---

## Running Tests

```bash
pytest
```

---

## License

MIT
