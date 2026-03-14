"""Slack Bot — Socket Mode app for KB ingestion."""

from __future__ import annotations

import logging

from slack_bolt import App
from slack_bolt.adapter.socket_mode import SocketModeHandler

from kb.config import settings
from kb.slack.handlers import handle_message

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(name)s %(levelname)s %(message)s",
)
log = logging.getLogger(__name__)


def create_app() -> App:
    """Create and configure the Slack Bolt app."""
    app = App(token=settings.slack_bot_token)

    @app.event("message")
    def on_message(event, say):
        # Only process messages in the configured channel
        channel = event.get("channel")
        if channel != settings.slack_channel_id:
            return

        # Ignore bot messages and message_changed events
        if event.get("bot_id") or event.get("subtype"):
            return

        log.info("Processing message in %s", channel)
        handle_message(event, say)

    return app


def main() -> None:
    """Entry point for the Slack bot."""
    if not settings.slack_bot_token or not settings.slack_app_token:
        log.error("SLACK_BOT_TOKEN and SLACK_APP_TOKEN must be set")
        raise SystemExit(1)

    log.info("Starting KB Slack bot...")
    app = create_app()
    handler = SocketModeHandler(app, settings.slack_app_token)
    handler.start()


if __name__ == "__main__":
    main()
