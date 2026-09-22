"""Exceptions raised while driving the Pangram web app."""


class PangramError(Exception):
    """Base class for errors from the Pangram browser client."""


class AuthenticationError(PangramError):
    """No saved session, or the saved session no longer works."""


class QuotaExceededError(PangramError):
    """Pangram refused the scan because the plan's word or scan limit is spent."""


class ScanFailedError(PangramError):
    """The scan was submitted but no result came back."""


class InvalidInputError(PangramError):
    """A caller-supplied argument is unusable; the message says how to fix it."""


class BrowserNotInstalledError(PangramError):
    """Patchright's Chromium is missing."""
