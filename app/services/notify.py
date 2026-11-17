"""Notification service (R9.1, R9.3).

Delivers notifications through a pluggable provider interface so a real
email/SMS provider can drop in later without touching callers. Every send
also persists a ``notifications`` row (the in-app inbox is the system of
record and the default channel), then hands the message to the provider
registered for the requested channel.

Channels: 'email' | 'sms' | 'ics' | 'inapp' (design.md s4). The default
provider for every channel is the in-app recorder, which is a no-op beyond
the persisted row; swapping in a real provider is a single register_provider()
call at startup. Stdlib only; no network calls (INTEGRATIONS_ONLY).
"""

from app import db

CHANNELS = ("email", "sms", "ics", "inapp")


class Provider:
    """Base notification provider. Subclasses implement deliver()."""

    def deliver(self, conn, user_id, subject, body, meta=None):
        """Deliver one message. Return True on success.

        The default implementation is a no-op success: the persisted inbox row
        is the delivery. A real email/SMS provider overrides this to call out
        to its transport (not available offline).
        """
        return True


class InAppProvider(Provider):
    """Default provider: the persisted notifications row is the delivery."""


# Channel -> provider instance. All channels default to the in-app recorder so
# the demo degrades gracefully without external transports; register_provider()
# replaces one at startup when a real transport is wired in.
_PROVIDERS = {channel: InAppProvider() for channel in CHANNELS}


def register_provider(channel, provider):
    """Register a Provider for a channel (pluggable interface, design.md s4)."""
    if channel not in CHANNELS:
        raise ValueError("unknown channel: %r" % channel)
    if not isinstance(provider, Provider):
        raise TypeError("provider must be a notify.Provider")
    _PROVIDERS[channel] = provider


def send(conn, user_id, channel="inapp", subject="", body="", kind=None, meta=None):
    """Persist a notification row and deliver it through the channel provider.

    Returns True when the provider reports success. `kind` labels the lifecycle
    event (favorite_invite, match_published, ...) and defaults to the channel.
    The persisted row always uses the real channel so the inbox can show how a
    message was delivered.
    """
    if channel not in CHANNELS:
        raise ValueError("unknown channel: %r" % channel)
    db.create_notification(
        conn, user_id, kind=kind or channel, channel=channel,
        subject=subject, body=body,
    )
    provider = _PROVIDERS.get(channel, _PROVIDERS["inapp"])
    try:
        return bool(provider.deliver(conn, user_id, subject, body, meta=meta))
    except Exception:  # pragma: no cover - a provider must not break the flow
        return False


def notify(conn, user_id, kind, subject="", body="", channel="inapp"):
    """Backward-compatible wrapper used by lifecycle callers (routes through send).

    Preserves the FEAT-003/004 call shape (`kind` positional) while delivering
    through the channel provider. Returns True on success.
    """
    return send(conn, user_id, channel=channel, subject=subject, body=body, kind=kind)
