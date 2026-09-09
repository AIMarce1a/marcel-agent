"""Parser for the one-time legacy home cutover."""

from __future__ import annotations


def build_migrate_legacy_parser(subparsers) -> None:
    parser = subparsers.add_parser(
        "migrate-legacy",
        help="Migrate a legacy home to Marcel",
        description="Copy the legacy home safely; the normal CLI performs this automatically.",
    )

    def run(_args) -> int:
        from marcel_migration import migrate_if_needed

        result = migrate_if_needed()
        print(result["status"])
        return 0

    parser.set_defaults(func=run)