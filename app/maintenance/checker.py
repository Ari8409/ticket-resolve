"""
MaintenanceChecker — answers the pre-dispatch question:
  "Is the affected node currently under a planned maintenance window?"

If yes, the maintenance team is already responsible for the node.
A second truck dispatch would create redundancy, safety risk, and OpEx waste.
"""
from __future__ import annotations

import logging
from datetime import datetime
from typing import Optional

from app.maintenance.models import MaintenanceCheckResult
from app.maintenance.store import MaintenanceStore

log = logging.getLogger(__name__)


class MaintenanceChecker:
    def __init__(self, store: MaintenanceStore) -> None:
        self._store = store

    async def check(
        self,
        node: str,
        at: Optional[datetime] = None,
    ) -> MaintenanceCheckResult:
        """
        Check whether `node` is inside an active maintenance window at `at`
        (defaults to current UTC time).

        Returns a MaintenanceCheckResult with:
          - in_maintenance=True  → dispatch_blocked=True  (hold the truck)
          - in_maintenance=False → dispatch_blocked=False (proceed normally)
        """
        when = at or datetime.utcnow()
        window = await self._store.get_for_node(node, at=when)

        if window:
            log.info(
                "Node %s is in maintenance '%s' until %s",
                node, window.title, window.end_time.isoformat(),
            )
            return MaintenanceCheckResult.found(node, window)

        log.debug("No active maintenance window for node=%s at=%s", node, when.isoformat())
        return MaintenanceCheckResult.none_found(node)
