"""Application entry points for TokenBank."""

from __future__ import annotations

from tokenbank.cli.main import app


def main() -> None:
    """Run the TokenBank CLI."""
    app()


__all__ = ["app", "main"]


if __name__ == "__main__":
    main()

