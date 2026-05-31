"""Embedded application icon (base64 PNG) so the window icon works even from a
PyInstaller one-file build where ``assets/`` is not on disk."""

import base64
import tkinter as tk

_ICON_B64 = (
    "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"
)


def apply_icon(root: tk.Tk) -> None:
    """Best-effort: set the window/taskbar icon. Never raises."""
    try:
        img = tk.PhotoImage(data=base64.b64decode(_ICON_B64))
        root.iconphoto(True, img)
        root._icon_ref = img  # keep a reference so it is not garbage-collected
    except Exception:
        pass
