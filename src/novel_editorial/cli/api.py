"""API command group: serve the HTTP API (thin shell over the api layer)."""

from __future__ import annotations

import typer

from novel_editorial.core.config import load_settings

api_app = typer.Typer(help="Serve and manage the HTTP API")


@api_app.command("serve")
def api_serve(
    host: str | None = typer.Option(None, "--host", help="Bind host (defaults to config)"),
    port: int | None = typer.Option(None, "--port", help="Bind port (defaults to config)"),
) -> None:
    """Run the HTTP API server with uvicorn."""
    import uvicorn

    from novel_editorial.api.app import create_app

    settings = load_settings()
    bind_host = host if host is not None else settings.api_host
    bind_port = port if port is not None else settings.api_port
    uvicorn.run(create_app(), host=bind_host, port=bind_port)
