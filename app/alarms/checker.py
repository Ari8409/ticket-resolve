"""
AlarmChecker — answers the pre-dispatch question:
  "Is the alarm for this node still active, or has it already cleared?"

A cleared alarm means the network has self-healed.  Dispatching a truck
would waste OpEx with no work to do on site.
"""
from __future__ import annotations

import logging
from typing import Optional

from app.alarms.models import AlarmCheckResult, AlarmStatus
from app.alarms.store import AlarmStore

log = logging.getLogger(__name__)


class AlarmChecker:
    def __init__(self, store: AlarmStore) -> None:
        self._store = store

    async def check(
        self,
        node: str,
        alarm_type: Optional[str] = None,
    ) -> AlarmCheckResult:
        """
        Look up the most recent alarm for `node` (optionally filtered by
        `alarm_type`) and return a structured result.

        Decision logic
        --------------
        - No alarm found          → alarm_found=False, dispatch_blocked=False
          (ticket may be spurious; agent decides)
        - Alarm found, ACTIVE     → alarm_found=True,  dispatch_blocked=False
          (fault persists — evaluation continues normally)
        - Alarm found, CLEARED    → alarm_found=True,  dispatch_blocked=True
          (fault self-healed — no truck needed, return HOLD)
        - Alarm found, ACK'd      → treat as still active
        """
        alarm = await self._store.get_latest_for_node(node, alarm_type)
        if not alarm:
            log.debug("No alarm record for node=%s type=%s", node, alarm_type)
            return AlarmCheckResult.not_found(node)

        if alarm.status == AlarmStatus.CLEARED:
            log.info("Alarm %s on %s is CLEARED — blocking dispatch", alarm.alarm_id, node)
            return AlarmCheckResult.cleared(node, alarm)

        log.debug("Alarm %s on %s is %s", alarm.alarm_id, node, alarm.status.value)
        return AlarmCheckResult.active(node, alarm)

    async def check_any_active(self, node: str) -> bool:
        """True if at least one alarm is still active for the node."""
        active = await self._store.get_active_for_node(node)
        return len(active) > 0
