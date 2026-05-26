import logging
import requests
from config import DISCORD_WEBHOOK_URL, ENABLE_WINDOWS_TOAST

log = logging.getLogger(__name__)


def _windows_toast(job: dict):
    try:
        from plyer import notification
        notification.notify(
            app_name="Job Scraper",
            title=f"{job['company']}  |  {job['source']}",
            message=f"{job['title']}\n{job['location']}\n{job['url']}",
            timeout=10,
        )
    except Exception as e:
        log.debug(f"Toast failed: {e}")


def _discord(job: dict):
    if not DISCORD_WEBHOOK_URL:
        return
    try:
        requests.post(
            DISCORD_WEBHOOK_URL,
            json={
                "content": (
                    f"**{job['title']}**\n"
                    f"{job['company']} ({job['source']})  |  {job['location']}\n"
                    f"{job['url']}"
                )
            },
            timeout=5,
        )
    except Exception as e:
        log.debug(f"Discord notify failed: {e}")


def notify(job: dict):
    if ENABLE_WINDOWS_TOAST:
        _windows_toast(job)
    _discord(job)
