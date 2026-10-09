"""Validate Maya assets against pipeline rules and publish them to USD.

The core (scene model, checks, runner, USD writer) is pure Python and runs
without Maya. ``maya_adapter`` builds the scene model from a live Maya
session and applies fixes there; ``ui`` provides a Qt checklist dialog.

"""

__version__ = "1.0.0"
