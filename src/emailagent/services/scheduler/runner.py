import logging
from typing import Optional

from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.interval import IntervalTrigger

from src.emailagent.config import settings
from src.emailagent.services.scheduler.orchestrator import EmailSyncOrchestrator

logger = logging.getLogger("emailagent.scheduler.runner")


class AgentSchedulerRunner:

    def __init__(self, orchestrator: Optional[EmailSyncOrchestrator] = None):
        self._orchestrator = orchestrator or EmailSyncOrchestrator()
        self._scheduler = AsyncIOScheduler()
        self._job_id = settings.SCHEDULER_JOB_ID

    @property
    def is_running(self) -> bool:
        return self._scheduler.running

    def start(self) -> None:
        """
        Registers the periodic job with concurrency safeguards and starts the scheduler.
        """
        if self._scheduler.running:
            logger.warning("AgentSchedulerRunner is already running.")
            return

        interval_minutes = settings.SCHEDULER_INTERVAL_MINUTES
        logger.info(
            "Registering background periodic sync job (ID: '%s', interval: %d min)...",
            self._job_id,
            interval_minutes
        )

        self._scheduler.add_job(
            func=self._orchestrator.execute_cycle,
            trigger=IntervalTrigger(minutes=interval_minutes),
            id=self._job_id,
            name="Periodic Mailbox Sync & Analysis Worker",
            max_instances=1,
            coalesce=True,
            replace_existing=True,
        )

        self._scheduler.start()
        logger.info("AgentSchedulerRunner started successfully.")

    def shutdown(self, wait: bool = False) -> None:
        """
        Gracefully terminates the background scheduler.
        """
        if not self._scheduler.running:
            logger.debug("AgentSchedulerRunner is not running, skipping shutdown.")
            return

        logger.info("Shutting down AgentSchedulerRunner (wait=%s)...", wait)
        self._scheduler.shutdown(wait=wait)
        logger.info("AgentSchedulerRunner shutdown complete.")

    def reschedule_interval(self, new_interval_minutes: int) -> bool:
        """
        Dynamically adjusts the polling frequency without restarting the application.
        """
        if new_interval_minutes < 1:
            raise ValueError("Interval must be at least 1 minute.")

        existing_job = self._scheduler.get_job(self._job_id)
        if not existing_job:
            logger.warning("Cannot reschedule: Job '%s' not found.", self._job_id)
            return False

        self._scheduler.reschedule_job(
            job_id=self._job_id,
            trigger=IntervalTrigger(minutes=new_interval_minutes)
        )
        logger.info("Job '%s' rescheduled to run every %d minutes.", self._job_id, new_interval_minutes)
        return True
