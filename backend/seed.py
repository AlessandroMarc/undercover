"""Rebuild the database from data/, with: uv run -m backend.seed"""

from backend.database import database_path, seed


def main() -> None:
    """Rebuild the database and say what it holds."""
    path = database_path()
    counts = seed(path)
    print(
        f"Seeded {counts['claims']} claims, {counts['policies']} policies, "
        f"{counts['customers']} customers and {counts['handlers']} handlers "
        f"into {path.name}"
    )


if __name__ == "__main__":
    main()
