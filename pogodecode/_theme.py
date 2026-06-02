"""Self-contained GUI theming + bundled-font support for the Tkinter apps.

This is a **pure-ttk** theme: it styles widgets only, and never touches the OS
window manager (no DWM/acrylic/native hacks), so it renders the same on Windows,
macOS and Linux with no platform surprises. A light and a dark variant are
provided; both are fully opaque and high-contrast.

Everything is best-effort and wrapped in try/except -- if a font can't be
registered or a style can't be applied, the app falls back to Tk's defaults
rather than breaking. This module is imported only by the GUIs; the CLI and
library never import it (so they stay headless and dependency-free).
"""

import glob
import os
import platform
import sys

# Bundled font families (see pogodecode/assets/fonts, SIL OFL).
UI_FONT = "Google Sans Flex"     # default UI font
DISPLAY_FONT = "Quicksand"       # used for headings / the app title

# Two hand-tuned, fully-opaque palettes.
PALETTES = {
    "light": {
        "bg": "#eef0f3", "surface": "#ffffff", "field": "#ffffff",
        "text": "#1f2430", "muted": "#5b6470", "border": "#cdd2da",
        "accent": "#2563eb", "accent_text": "#ffffff",
        "sel": "#2563eb", "sel_text": "#ffffff", "hover": "#e3e8f0",
        "heading": "#e7eaf0",
    },
    "dark": {
        "bg": "#1d1f24", "surface": "#272a31", "field": "#2e323a",
        "text": "#e6e8ec", "muted": "#9aa1ad", "border": "#3a3f48",
        "accent": "#4f8cff", "accent_text": "#0b1020",
        "sel": "#3a5bd9", "sel_text": "#ffffff", "hover": "#31353e",
        "heading": "#22252b",
    },
}


# ---------------------------------------------------------------------------
# Font registration (so the bundled TTFs are usable by family name)
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# The theme
# ---------------------------------------------------------------------------

def apply_theme(root, dark=False, font=None):
    """Apply the theme + fonts to ``root``. Best-effort; never raises.

    ``font`` optionally overrides the UI font with any installed family (see
    :func:`list_font_families`); falls back to the bundled font, then the Tk
    default. Returns the resolved family.
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
    p = PALETTES["dark" if dark else "light"]

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

    try:
        st = ttk.Style(root)
        try:
            st.theme_use("clam")   # the only fully re-stylable built-in theme
        except Exception:
            pass

        st.configure(".", background=p["bg"], foreground=p["text"],
                     fieldbackground=p["field"], bordercolor=p["border"],
                     lightcolor=p["bg"], darkcolor=p["bg"], focuscolor=p["accent"],
                     troughcolor=p["heading"], insertcolor=p["text"])

        st.configure("TFrame", background=p["bg"])
        st.configure("TLabel", background=p["bg"], foreground=p["text"])
        st.configure("Muted.TLabel", background=p["bg"], foreground=p["muted"])
        st.configure("Title.TLabel", background=p["bg"], foreground=p["text"],
                     font=(display or ui or "TkHeadingFont", 15, "bold"))
        st.configure("Status.TLabel", background=p["heading"], foreground=p["muted"],
                     padding=4)
        st.configure("TLabelframe", background=p["bg"], bordercolor=p["border"])
        st.configure("TLabelframe.Label", background=p["bg"], foreground=p["muted"])

        # Buttons -- clam overrides configure() per state, so pin every look via map.
        st.configure("TButton", background=p["surface"], foreground=p["text"],
                     bordercolor=p["border"], padding=(10, 5), relief="flat")
        st.map("TButton",
               background=[("pressed", p["accent"]), ("active", p["hover"]),
                           ("disabled", p["bg"]), ("!disabled", p["surface"])],
               foreground=[("pressed", p["accent_text"]), ("disabled", p["muted"]),
                           ("!disabled", p["text"])],
               bordercolor=[("focus", p["accent"]), ("!focus", p["border"])])
        st.configure("Accent.TButton", background=p["accent"],
                     foreground=p["accent_text"], padding=(12, 6), relief="flat")
        st.map("Accent.TButton",
               background=[("pressed", p["sel"]), ("active", p["accent"]),
                           ("!disabled", p["accent"])],
               foreground=[("!disabled", p["accent_text"])])

        st.configure("TCheckbutton", background=p["bg"], foreground=p["text"])
        st.map("TCheckbutton", background=[("active", p["bg"])],
               indicatorcolor=[("selected", p["accent"]), ("!selected", p["field"])])
        st.configure("TRadiobutton", background=p["bg"], foreground=p["text"])
        st.map("TRadiobutton", background=[("active", p["bg"])])

        # Entry / Combobox / Spinbox fields.
        for cls in ("TEntry", "TCombobox", "TSpinbox"):
            st.configure(cls, fieldbackground=p["field"], foreground=p["text"],
                         bordercolor=p["border"], insertcolor=p["text"],
                         arrowcolor=p["muted"], padding=3)
            st.map(cls,
                   fieldbackground=[("readonly", p["field"]), ("disabled", p["bg"]),
                                    ("!disabled", p["field"])],
                   foreground=[("disabled", p["muted"]), ("!disabled", p["text"])],
                   bordercolor=[("focus", p["accent"]), ("!focus", p["border"])])
        root.option_add("*TCombobox*Listbox.background", p["surface"])
        root.option_add("*TCombobox*Listbox.foreground", p["text"])
        root.option_add("*TCombobox*Listbox.selectBackground", p["accent"])
        root.option_add("*TCombobox*Listbox.selectForeground", p["accent_text"])

        # Notebook tabs.
        st.configure("TNotebook", background=p["bg"], bordercolor=p["border"],
                     tabmargins=(4, 4, 4, 0))
        st.configure("TNotebook.Tab", background=p["bg"], foreground=p["muted"],
                     padding=(12, 6), bordercolor=p["border"])
        st.map("TNotebook.Tab",
               background=[("selected", p["surface"]), ("active", p["hover"])],
               foreground=[("selected", p["accent"]), ("active", p["text"])])

        # Treeview (the tables).
        st.configure("Treeview", background=p["surface"], fieldbackground=p["surface"],
                     foreground=p["text"], bordercolor=p["border"], rowheight=23,
                     relief="flat")
        st.map("Treeview",
               background=[("selected", p["sel"])],
               foreground=[("selected", p["sel_text"])])
        st.configure("Treeview.Heading", background=p["heading"], foreground=p["muted"],
                     relief="flat", padding=4)
        st.map("Treeview.Heading", background=[("active", p["hover"])])

        # Scrollbars + progress.
        for cls in ("Vertical.TScrollbar", "Horizontal.TScrollbar", "TScrollbar"):
            st.configure(cls, background=p["heading"], troughcolor=p["bg"],
                         bordercolor=p["bg"], arrowcolor=p["muted"], relief="flat")
            st.map(cls, background=[("active", p["border"])])
        st.configure("TProgressbar", background=p["accent"], troughcolor=p["heading"],
                     bordercolor=p["border"])
        st.configure("TSeparator", background=p["border"])
        st.configure("TPanedwindow", background=p["bg"])
    except Exception:
        pass

    # Root window + classic (tk, non-ttk) widget defaults.
    try:
        root.configure(background=p["bg"])
        root.option_add("*background", p["bg"])
        root.option_add("*foreground", p["text"])
        root.option_add("*Listbox.background", p["surface"])
        root.option_add("*Listbox.foreground", p["text"])
        root.option_add("*Listbox.selectBackground", p["accent"])
        root.option_add("*Listbox.selectForeground", p["accent_text"])
        root.option_add("*Listbox.highlightThickness", 0)
        root.option_add("*Text.background", p["surface"])
        root.option_add("*Text.foreground", p["text"])
        root.option_add("*Text.insertBackground", p["text"])
        root.option_add("*Text.highlightThickness", 0)
        root.option_add("*Menu.background", p["surface"])
        root.option_add("*Menu.foreground", p["text"])
        root.option_add("*Menu.activeBackground", p["accent"])
        root.option_add("*Menu.activeForeground", p["accent_text"])
    except Exception:
        pass

    _retheme_classic(root, p)
    return ui or "TkDefaultFont"


def _retheme_classic(widget, p):
    """Recolor classic (non-ttk) Text / Listbox / Canvas widgets already created,
    so a live light/dark switch updates them too. Best-effort per widget."""
    try:
        cls = widget.winfo_class()
        if cls in ("Text", "Listbox"):
            widget.configure(background=p["surface"], foreground=p["text"],
                             highlightthickness=0)
            try:
                widget.configure(insertbackground=p["text"],
                                 selectbackground=p["accent"],
                                 selectforeground=p["accent_text"])
            except Exception:
                pass
        elif cls == "Canvas":
            widget.configure(background=p["bg"], highlightthickness=0)
    except Exception:
        pass
    for child in getattr(widget, "winfo_children", lambda: [])():
        _retheme_classic(child, p)


def text_widget_colors(dark=False):
    """Palette colors for ad-hoc tk.Text / tk.Listbox created after theming."""
    p = PALETTES["dark" if dark else "light"]
    return {"bg": p["surface"], "fg": p["text"], "muted": p["muted"],
            "accent": p["accent"], "sel": p["sel"]}


# ---------------------------------------------------------------------------
# Font picker
# ---------------------------------------------------------------------------

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
    win.geometry("360x430")
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
