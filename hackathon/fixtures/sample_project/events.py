"""Event log utilities for tracking application events."""

from datetime import datetime


class EventLog:
    """A simple in-memory event log."""

    def get_events(self):
        """Return all stored events."""
        return []

    def clear(self):
        """Clear all stored events."""
        pass


def format_event(event, timestamp=None):
    """Format an event dict for display."""
    ts = timestamp or datetime.utcnow().isoformat()
    return f"[{ts}] {event}"
