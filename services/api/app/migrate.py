from __future__ import annotations

from fleetmind_common.db import Base, engine, ensure_schema_compatibility

# Import all mapped tables before metadata creation.
from fleetmind_common import diagnostic_store as _diagnostic_store  # noqa: F401
from fleetmind_common import models as _models  # noqa: F401
from fleetmind_common import platform_store as _platform_store  # noqa: F401


def main() -> None:
    Base.metadata.create_all(bind=engine)
    ensure_schema_compatibility()
    print("FleetMind schema compatibility migration complete.")


if __name__ == "__main__":
    main()
