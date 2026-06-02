"""Optional GUI theming: embed the bundled fonts and apply a modern look.

Everything here is best-effort and wrapped in try/except -- if a font cannot be
registered or a style cannot be applied, the app silently falls back to Tk's
defaults rather than failing. Nothing in this module is required for the CLI or
the library (it is only imported by the Tkinter apps).
"""

import glob
import os
import platform
import sys

# Bundled font families (see pogodecode/assets/fonts, SIL OFL).
UI_FONT = "Google Sans Flex"     # default UI font
DISPLAY_FONT = "Quicksand"       # used for headings / the app title

# Windows-only backdrop applied via pywinstyles. "acrylic" gives the translucent,
# blurred system backdrop with a dark title bar (Windows 10/11). Other options:
# "mica", "aero", "transparent", "dark", "light". Acrylic implies a dark chrome.
WINDOW_STYLE = "acrylic"

# Light and dark palettes. Keys are referenced by apply_theme().
PALETTES = {
    "light": {
        "bg": "#f4f5f7", "surface": "#ffffff", "field": "#ffffff",
        "text": "#1f2329", "muted": "#6b7280", "border": "#d6d9de",
        "accent": "#2d6ed2", "accent_text": "#ffffff", "sel": "#d4e4fb",
    },
    "dark": {
        "bg": "#1e1f22", "surface": "#26282c", "field": "#2d2f34",
        "text": "#e6e6e6", "muted": "#9aa0a6", "border": "#3a3d42",
        "accent": "#4a90e2", "accent_text": "#ffffff", "sel": "#33475f",
    },
}


def _font_dir():
    """Locate the bundled fonts whether running from source or a PyInstaller build."""
    base = getattr(sys, "_MEIPASS", None)
    candidates = []
    if base:
        candidates += [os.path.join(base, "pogodecode", "assets", "fonts"),
                       os.path.join(base, "assets", "fonts")]
    candidates.append(os.path.join(os.path.dirname(__file__), "assets", "fonts"))
    for c in candidates:
        if os.path.isdir(c):
            return c
    return candidates[-1]


def _register_one(path):
    """Register a single TTF with the OS for the current process. Never raises."""
    system = platform.system()
    try:
        if system == "Windows":
            import ctypes
            FR_PRIVATE = 0x10
            n = ctypes.windll.gdi32.AddFontResourceExW(ctypes.c_wchar_p(path), FR_PRIVATE, 0)
            return n > 0
        if system == "Darwin":
            import ctypes
            import ctypes.util
            cf = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreFoundation"))
            ct = ctypes.cdll.LoadLibrary(ctypes.util.find_library("CoreText"))
            cf.CFStringCreateWithCString.restype = ctypes.c_void_p
            cf.CFStringCreateWithCString.argtypes = [ctypes.c_void_p, ctypes.c_char_p, ctypes.c_uint32]
            cf.CFURLCreateWithFileSystemPath.restype = ctypes.c_void_p
            cf.CFURLCreateWithFileSystemPath.argtypes = [
                ctypes.c_void_p, ctypes.c_void_p, ctypes.c_int, ctypes.c_bool]
            ct.CTFontManagerRegisterFontsForURL.restype = ctypes.c_bool
            ct.CTFontManagerRegisterFontsForURL.argtypes = [
                ctypes.c_void_p, ctypes.c_int, ctypes.c_void_p]
            s = cf.CFStringCreateWithCString(None, path.encode("utf-8"), 0x08000100)
            url = cf.CFURLCreateWithFileSystemPath(None, s, 0, False)
            return bool(ct.CTFontManagerRegisterFontsForURL(url, 1, None))  # process scope
        # Linux / other: install into the user font dir (best effort).
        import shutil
        dest_dir = os.path.expanduser("~/.local/share/fonts")
        os.makedirs(dest_dir, exist_ok=True)
        dest = os.path.join(dest_dir, os.path.basename(path))
        if not os.path.exists(dest):
            shutil.copy2(path, dest)
            os.system("fc-cache -f >/dev/null 2>&1")
        return True
    except Exception:
        return False


def register_fonts():
    """Register every bundled TTF. Returns the number registered (0 on failure)."""
    count = 0
    for ttf in sorted(glob.glob(os.path.join(_font_dir(), "*.ttf"))):
        if _register_one(ttf):
            count += 1
    return count


def _family_available(root, family):
    try:
        from tkinter import font as tkfont
        return family in tkfont.families(root)
    except Exception:
        return False


def apply_theme(root, dark=False, font=None):
    """Register fonts and apply the theme to ``root``. Best-effort; never raises.

    ``font`` optionally overrides the UI font family with any font installed on
    the machine (see :func:`list_font_families`); it falls back to the bundled
    font, then to the Tk default. Returns the resolved family.
    """
    from tkinter import font as tkfont
    from tkinter import ttk

    try:
        register_fonts()
    except Exception:
        pass

    # Resolve the UI font: user choice -> bundled Google Sans Flex -> Tk default.
    ui = None
    for candidate in (font, UI_FONT):
        if candidate and _family_available(root, candidate):
            ui = candidate
            break
    display = DISPLAY_FONT if _family_available(root, DISPLAY_FONT) else ui
    pal = PALETTES["dark" if dark else "light"]

    # Make every standard named font use the bundled UI font.
    if ui:
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                     "TkTooltipFont", "TkIconFont", "TkSmallCaptionFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family=ui)
            except Exception:
                pass
        try:
            root.option_add("*Font", (ui, 10))
        except Exception:
            pass

    # ttk palette via the themeable 'clam' base.
    try:
        style = ttk.Style(root)
        try:
            style.theme_use("clam")
        except Exception:
            pass
        style.configure(".", background=pal["bg"], foreground=pal["text"],
                        fieldbackground=pal["field"], bordercolor=pal["border"])
        style.configure("TFrame", background=pal["bg"])
        style.configure("TLabelframe", background=pal["bg"], bordercolor=pal["border"])
        style.configure("TLabelframe.Label", background=pal["bg"], foreground=pal["muted"])
        style.configure("TLabel", background=pal["bg"], foreground=pal["text"])
        style.configure("TButton", background=pal["surface"], foreground=pal["text"],
                        bordercolor=pal["border"], focuscolor=pal["accent"], padding=6)
        # clam overrides configure() with per-state colors, so the base look must
        # be pinned via the ("!disabled", ...) state too -- otherwise dark mode
        # leaves entries/buttons light.
        style.map("TButton",
                  background=[("pressed", pal["accent"]), ("active", pal["sel"]),
                              ("!disabled", pal["surface"])],
                  foreground=[("pressed", pal["accent_text"]), ("!disabled", pal["text"])])
        style.configure("Accent.TButton", background=pal["accent"],
                        foreground=pal["accent_text"], padding=6)
        style.map("Accent.TButton",
                  background=[("active", pal["accent"]), ("!disabled", pal["accent"])],
                  foreground=[("!disabled", pal["accent_text"])])
        style.configure("TEntry", fieldbackground=pal["field"], foreground=pal["text"],
                        bordercolor=pal["border"])
        style.map("TEntry",
                  fieldbackground=[("readonly", pal["field"]), ("disabled", pal["field"]),
                                   ("!disabled", pal["field"])],
                  foreground=[("!disabled", pal["text"])])
        style.configure("TCombobox", fieldbackground=pal["field"], foreground=pal["text"])
        style.map("TCombobox",
                  fieldbackground=[("readonly", pal["field"]), ("!disabled", pal["field"])],
                  foreground=[("!disabled", pal["text"])])
        root.option_add("*TCombobox*Listbox.background", pal["surface"])
        root.option_add("*TCombobox*Listbox.foreground", pal["text"])
        style.configure("TNotebook", background=pal["bg"], bordercolor=pal["border"])
        style.configure("TNotebook.Tab", background=pal["bg"], foreground=pal["muted"],
                        padding=(10, 5))
        style.map("TNotebook.Tab",
                  background=[("selected", pal["surface"])],
                  foreground=[("selected", pal["accent"])])
        style.configure("Treeview", background=pal["surface"], fieldbackground=pal["surface"],
                        foreground=pal["text"], bordercolor=pal["border"], rowheight=22)
        style.configure("Treeview.Heading", background=pal["bg"], foreground=pal["muted"])
        style.map("Treeview", background=[("selected", pal["accent"])],
                  foreground=[("selected", pal["accent_text"])])
        style.configure("TCheckbutton", background=pal["bg"], foreground=pal["text"])
        style.configure("TScrollbar", background=pal["bg"], troughcolor=pal["bg"],
                        bordercolor=pal["border"])
        style.configure("Status.TLabel", background=pal["border"], foreground=pal["text"])
        style.configure("Title.TLabel", background=pal["bg"], foreground=pal["text"],
                        font=(display or ui or "TkHeadingFont", 16, "bold"))
    except Exception:
        pass

    # Root + classic (tk, non-ttk) widget defaults.
    try:
        root.configure(background=pal["bg"])
        root.option_add("*background", pal["bg"])
        root.option_add("*foreground", pal["text"])
        root.option_add("*Listbox.background", pal["surface"])
        root.option_add("*Listbox.foreground", pal["text"])
        root.option_add("*Listbox.selectBackground", pal["accent"])
        root.option_add("*Listbox.selectForeground", pal["accent_text"])
        root.option_add("*Text.background", pal["surface"])
        root.option_add("*Text.foreground", pal["text"])
        root.option_add("*Text.insertBackground", pal["text"])
    except Exception:
        pass

    _retheme_classic(root, pal)
    _apply_window_chrome(root, dark)
    return ui or "TkDefaultFont"


def _retheme_classic(widget, pal):
    """Recolor classic (non-ttk) Text / Listbox / Canvas widgets in the tree so
    a live light/dark switch updates them too. Best-effort per widget."""
    try:
        cls = widget.winfo_class()
        if cls in ("Text", "Listbox"):
            widget.configure(background=pal["surface"], foreground=pal["text"],
                             highlightbackground=pal["border"])
            try:
                widget.configure(insertbackground=pal["text"],
                                 selectbackground=pal["accent"],
                                 selectforeground=pal["accent_text"])
            except Exception:
                pass
        elif cls == "Canvas":
            widget.configure(background=pal["bg"], highlightthickness=0)
    except Exception:
        pass
    for child in getattr(widget, "winfo_children", lambda: [])():
        _retheme_classic(child, pal)


def text_widget_colors(dark=False):
    """Palette colors for ad-hoc tk.Text / tk.Listbox created after theming."""
    pal = PALETTES["dark" if dark else "light"]
    return {"bg": pal["surface"], "fg": pal["text"], "muted": pal["muted"],
            "accent": pal["accent"], "sel": pal["sel"]}


def _apply_window_chrome(root, dark):
    """Windows-only backdrop/title-bar styling via pywinstyles (optional).

    Applies the configured WINDOW_STYLE (acrylic by default). pywinstyles needs a
    realized window, so it runs once via ``after``. Everything is guarded; on
    non-Windows or without pywinstyles it is a no-op and the app is unaffected.
    """
    if platform.system() != "Windows":
        return

    def _do():
        try:
            import pywinstyles
        except Exception:
            return  # pywinstyles not installed / not Windows -> plain look
        # Acrylic's translucency only reads well over dark content -- over a light
        # UI it washes everything out and bleeds the desktop through. So the
        # translucent backdrop is dark-mode only; light mode stays a clean,
        # opaque window with a flat light title bar.
        style = WINDOW_STYLE if dark else "light"
        try:
            pywinstyles.apply_style(root, style)
        except Exception:
            try:
                pywinstyles.apply_style(root, "dark" if dark else "light")
            except Exception:
                return
        try:
            pywinstyles.change_title_color(root, "white" if dark else "black")
        except Exception:
            pass

    try:
        root.after(0, _do)
    except Exception:
        _do()


def list_font_families(root):
    """Sorted, de-duplicated font families installed on this machine (plus the
    bundled ones). '@'-prefixed vertical CJK variants are filtered out."""
    try:
        from tkinter import font as tkfont
        seen, out = set(), []
        for fam in tkfont.families(root):
            if fam.startswith("@") or fam in seen:
                continue
            seen.add(fam)
            out.append(fam)
        return sorted(out, key=str.lower)
    except Exception:
        return []


def choose_font(root, current, on_apply):
    """Open a searchable font picker. Calls ``on_apply(family)`` when chosen."""
    import tkinter as tk
    from tkinter import ttk

    fams = list_font_families(root)
    win = tk.Toplevel(root)
    win.title("Choose font")
    win.transient(root)
    win.geometry("360x420")
    try:
        win.grab_set()
    except Exception:
        pass

    ttk.Label(win, text="Filter:").pack(anchor="w", padx=10, pady=(10, 2))
    filt = tk.StringVar()
    ttk.Entry(win, textvariable=filt).pack(fill="x", padx=10)

    mid = ttk.Frame(win)
    mid.pack(fill="both", expand=True, padx=10, pady=6)
    lb = tk.Listbox(mid, exportselection=False, activestyle="dotbox")
    lb.pack(side="left", fill="both", expand=True)
    sb = ttk.Scrollbar(mid, command=lb.yview)
    sb.pack(side="left", fill="y")
    lb.configure(yscrollcommand=sb.set)

    preview = ttk.Label(win, text="The quick brown fox — Pokémon GO 0123456789",
                        anchor="w", wraplength=330)
    preview.pack(fill="x", padx=10, pady=(0, 8))

    def populate(*_):
        term = filt.get().lower()
        lb.delete(0, "end")
        for fam in fams:
            if term in fam.lower():
                lb.insert("end", fam)
        if current in fams and (not term or term in current.lower()):
            try:
                idx = list(lb.get(0, "end")).index(current)
                lb.selection_set(idx)
                lb.see(idx)
                preview.configure(font=(current, 15))
            except ValueError:
                pass

    def on_sel(*_):
        sel = lb.curselection()
        if sel:
            preview.configure(font=(lb.get(sel[0]), 15))

    def apply_and_close():
        sel = lb.curselection()
        fam = lb.get(sel[0]) if sel else current
        on_apply(fam)
        win.destroy()

    filt.trace_add("write", populate)
    lb.bind("<<ListboxSelect>>", on_sel)
    lb.bind("<Double-Button-1>", lambda *_: apply_and_close())
    populate()

    btns = ttk.Frame(win)
    btns.pack(fill="x", padx=10, pady=(0, 10))
    ttk.Button(btns, text="Use bundled font",
               command=lambda: (on_apply(UI_FONT), win.destroy())).pack(side="left")
    ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(btns, text="Apply", command=apply_and_close).pack(side="right", padx=6)
