"""
CLI interface for ISRT – Insurgency Sandstorm RCON Tool.

Entry point: ``isrt`` (or ``python -m isrt``).

Commands
--------
``isrt exec``       – Run a single RCON command and print the response.
``isrt shell``      – Start an interactive RCON shell.
``isrt profile``    – Manage saved connection profiles.
``isrt players``    – Shortcut: list connected players.
``isrt broadcast``  – Shortcut: broadcast a message to all players.
``isrt map``        – Shortcut: change the current map.
``isrt kick``       – Shortcut: kick a player.
``isrt ban``        – Shortcut: ban a player.
"""

import sys

import click

from isrt import __version__
from isrt import config as cfg
from isrt.rcon import AuthenticationError
from isrt.rcon import ConnectionError as RCONConnectionError
from isrt.rcon import RCONClient, RCONError

# ---------------------------------------------------------------------------
# Shared connection options
# ---------------------------------------------------------------------------

_shared_options = [
    click.option("--host", "-H", default=None, help="Server hostname or IP."),
    click.option(
        "--port",
        "-p",
        default=None,
        type=int,
        help=f"RCON port (default: {cfg.DEFAULT_PORT}).",
    ),
    click.option("--password", "-P", default=None, help="RCON password."),
    click.option(
        "--timeout",
        "-t",
        default=None,
        type=float,
        help=f"Socket timeout in seconds (default: {cfg.DEFAULT_TIMEOUT}).",
    ),
    click.option(
        "--profile",
        "-r",
        default=None,
        help="Name of a saved connection profile.",
    ),
]


def _add_shared_options(func):
    for option in reversed(_shared_options):
        func = option(func)
    return func


def _resolve_connection(host, port, password, timeout, profile):
    """
    Merge CLI flags, a named profile, and the default profile to produce a
    complete set of connection parameters.  Returns (host, port, password, timeout).
    """
    profile_name = profile or cfg.get_default_profile()
    profile_data = cfg.get_profile(profile_name) if profile_name else {}

    resolved_host = host or profile_data.get("host")
    resolved_port = port or profile_data.get("port", cfg.DEFAULT_PORT)
    resolved_password = password or profile_data.get("password")
    resolved_timeout = timeout or profile_data.get("timeout", cfg.DEFAULT_TIMEOUT)

    if not resolved_host:
        raise click.UsageError(
            "No host specified.  Use --host or save a profile with "
            "`isrt profile save`."
        )
    if not resolved_password:
        resolved_password = click.prompt("RCON password", hide_input=True)

    return resolved_host, resolved_port, resolved_password, resolved_timeout


def _make_client(host, port, password, timeout, profile) -> RCONClient:
    """Build an RCONClient from CLI flags / profile (no connection yet)."""
    h, p, pw, t = _resolve_connection(host, port, password, timeout, profile)
    return RCONClient(h, p, pw, t)


def _run_with_client(client: RCONClient, fn):
    """Connect, authenticate, call fn(client), then disconnect.  Exit on error."""
    try:
        with client:
            fn(client)
    except RCONConnectionError as exc:
        click.echo(click.style(f"Connection error: {exc}", fg="red"), err=True)
        sys.exit(1)
    except AuthenticationError as exc:
        click.echo(click.style(f"Authentication error: {exc}", fg="red"), err=True)
        sys.exit(1)


# ---------------------------------------------------------------------------
# Root group
# ---------------------------------------------------------------------------


@click.group()
@click.version_option(__version__, prog_name="isrt")
def cli():
    """Insurgency Sandstorm RCON Tool (ISRT).

    Connect to and manage Insurgency: Sandstorm game servers remotely via
    the Source RCON protocol.

    \b
    Quick-start:
      isrt profile save default --host 192.168.1.1 --port 27015 --password secret
      isrt players
      isrt exec "AdminBroadcast Hello everyone"
      isrt shell
    """


# ---------------------------------------------------------------------------
# exec – single command
# ---------------------------------------------------------------------------


@cli.command("exec")
@click.argument("command", nargs=-1, required=True)
@_add_shared_options
def exec_cmd(command, host, port, password, timeout, profile):
    """Execute a single RCON command and print the response.

    COMMAND may be given as multiple words without quotes:

    \b
      isrt exec AdminBroadcast Hello World
      isrt exec "AdminListPlayers"
    """
    full_command = " ".join(command)
    client = _make_client(host, port, password, timeout, profile)
    result = []

    def _do(c):
        try:
            response = c.execute(full_command)
        except RCONError as exc:
            click.echo(click.style(f"RCON error: {exc}", fg="red"), err=True)
            sys.exit(1)
        result.append(response)

    _run_with_client(client, _do)
    if result and result[0]:
        click.echo(result[0])


# ---------------------------------------------------------------------------
# shell – interactive RCON session
# ---------------------------------------------------------------------------


@cli.command()
@_add_shared_options
def shell(host, port, password, timeout, profile):
    """Start an interactive RCON shell.

    Type RCON commands at the prompt and press Enter to execute them.
    Type ``exit`` or press Ctrl-D / Ctrl-C to quit.
    """
    h, p, _, _ = _resolve_connection(host, port, password, timeout, profile)
    client = _make_client(host, port, password, timeout, profile)

    def _do(c):
        click.echo(
            click.style(
                f"Connected to {h}:{p}  (type 'exit' or Ctrl-D to quit)",
                fg="green",
            )
        )
        while True:
            try:
                cmd = click.prompt(
                    click.style("rcon", fg="cyan", bold=True),
                    prompt_suffix="> ",
                )
            except (EOFError, KeyboardInterrupt):
                click.echo()
                break
            cmd = cmd.strip()
            if not cmd:
                continue
            if cmd.lower() in ("exit", "quit"):
                break
            try:
                response = c.execute(cmd)
            except RCONError as exc:
                click.echo(click.style(f"Error: {exc}", fg="red"))
                continue
            if response:
                click.echo(response)
            else:
                click.echo(click.style("(no response)", fg="bright_black"))
        click.echo(click.style("Disconnected.", fg="yellow"))

    _run_with_client(client, _do)


# ---------------------------------------------------------------------------
# profile – manage saved profiles
# ---------------------------------------------------------------------------


@cli.group()
def profile():
    """Manage saved RCON connection profiles."""


@profile.command("save")
@click.argument("name")
@click.option("--host", "-H", required=True, help="Server hostname or IP.")
@click.option("--port", "-p", default=cfg.DEFAULT_PORT, show_default=True, type=int)
@click.option("--password", "-P", default=None, help="RCON password (prompted if omitted).")
@click.option(
    "--timeout",
    "-t",
    default=cfg.DEFAULT_TIMEOUT,
    show_default=True,
    type=float,
)
@click.option("--set-default", is_flag=True, help="Also set as the default profile.")
def profile_save(name, host, port, password, timeout, set_default):
    """Save a connection profile named NAME."""
    if password is None:
        password = click.prompt("RCON password", hide_input=True)
    cfg.save_profile(name, host, port, password, timeout)
    if set_default:
        cfg.set_default_profile(name)
    click.echo(click.style(f"Profile '{name}' saved.", fg="green"))


@profile.command("list")
def profile_list():
    """List all saved profiles."""
    profiles = cfg.list_profiles()
    default = cfg.get_default_profile()
    if not profiles:
        click.echo("No profiles saved yet.")
        return
    for name, data in profiles.items():
        marker = " (default)" if name == default else ""
        click.echo(
            f"  {click.style(name, bold=True)}{marker}  "
            f"{data['host']}:{data['port']}"
        )


@profile.command("delete")
@click.argument("name")
def profile_delete(name):
    """Delete the profile named NAME."""
    if cfg.delete_profile(name):
        click.echo(click.style(f"Profile '{name}' deleted.", fg="yellow"))
    else:
        click.echo(click.style(f"Profile '{name}' not found.", fg="red"), err=True)
        sys.exit(1)


@profile.command("default")
@click.argument("name")
def profile_default(name):
    """Set the default profile to NAME."""
    if cfg.get_profile(name) is None:
        click.echo(
            click.style(f"Profile '{name}' does not exist.", fg="red"), err=True
        )
        sys.exit(1)
    cfg.set_default_profile(name)
    click.echo(click.style(f"Default profile set to '{name}'.", fg="green"))


# ---------------------------------------------------------------------------
# Convenience shortcuts
# ---------------------------------------------------------------------------


@cli.command()
@_add_shared_options
def players(host, port, password, timeout, profile):
    """List players currently connected to the server."""
    client = _make_client(host, port, password, timeout, profile)
    result = []

    def _do(c):
        try:
            result.append(c.execute("AdminListPlayers"))
        except RCONError as exc:
            click.echo(click.style(f"RCON error: {exc}", fg="red"), err=True)
            sys.exit(1)

    _run_with_client(client, _do)
    response = result[0] if result else ""
    click.echo(response if response else click.style("(no players)", fg="bright_black"))


@cli.command()
@click.argument("message", nargs=-1, required=True)
@_add_shared_options
def broadcast(message, host, port, password, timeout, profile):
    """Broadcast MESSAGE to all players on the server."""
    msg = " ".join(message)
    client = _make_client(host, port, password, timeout, profile)

    def _do(c):
        try:
            c.execute(f"AdminBroadcast {msg}")
        except RCONError as exc:
            click.echo(click.style(f"RCON error: {exc}", fg="red"), err=True)
            sys.exit(1)

    _run_with_client(client, _do)
    click.echo(click.style(f"Broadcast sent: {msg}", fg="green"))


@cli.command()
@click.argument("map_name")
@_add_shared_options
def map(map_name, host, port, password, timeout, profile):
    """Change the server map to MAP_NAME (e.g. PowerPlant)."""
    client = _make_client(host, port, password, timeout, profile)

    def _do(c):
        try:
            c.execute(f"AdminChangeLevel {map_name}")
        except RCONError as exc:
            click.echo(click.style(f"RCON error: {exc}", fg="red"), err=True)
            sys.exit(1)

    _run_with_client(client, _do)
    click.echo(click.style(f"Map change to '{map_name}' requested.", fg="green"))


@cli.command()
@click.argument("player")
@click.argument("reason", default="Kicked by admin")
@_add_shared_options
def kick(player, reason, host, port, password, timeout, profile):
    """Kick PLAYER from the server with an optional REASON."""
    client = _make_client(host, port, password, timeout, profile)

    def _do(c):
        try:
            c.execute(f"AdminKick {player} {reason}")
        except RCONError as exc:
            click.echo(click.style(f"RCON error: {exc}", fg="red"), err=True)
            sys.exit(1)

    _run_with_client(client, _do)
    click.echo(click.style(f"Kick command sent for player '{player}'.", fg="yellow"))


@cli.command()
@click.argument("player")
@click.argument("reason", default="Banned by admin")
@_add_shared_options
def ban(player, reason, host, port, password, timeout, profile):
    """Permanently ban PLAYER with an optional REASON."""
    client = _make_client(host, port, password, timeout, profile)

    def _do(c):
        try:
            c.execute(f"AdminBan {player} {reason} 0")
        except RCONError as exc:
            click.echo(click.style(f"RCON error: {exc}", fg="red"), err=True)
            sys.exit(1)

    _run_with_client(client, _do)
    click.echo(click.style(f"Ban command sent for player '{player}'.", fg="red"))
