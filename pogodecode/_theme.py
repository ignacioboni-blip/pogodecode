"""Self-contained GUI theming for the Tkinter apps (no bundled fonts).

A pure-ttk light/dark theme that styles widgets only -- it never touches the OS
window manager and it does not ship or register any fonts, so it stays fast and
uses the platform's native system font by default. Users can still pick any
installed font via :func:`choose_font`; headings/emphasis use bold of whatever
font is active.

Everything is best-effort and wrapped in try/except: a failure falls back to Tk's
defaults rather than breaking the app. Imported only by the GUIs.
"""

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


def _family_available(root, family):
    try:
        from tkinter import font as tkfont
        return family in tkfont.families(root)
    except Exception:
        return False


def apply_theme(root, dark=False, font=None):
    """Apply the theme to ``root``. Best-effort; never raises.

    ``font`` optionally overrides the UI font with any installed family (see
    :func:`list_font_families`). When ``None`` (the default), the platform's
    native system font is used unchanged -- nothing is registered, so there is no
    startup or per-draw cost. Returns the resolved family ("" = system default).
    """
    from tkinter import font as tkfont
    from tkinter import ttk

    ui = font if (font and _family_available(root, font)) else None
    p = PALETTES["dark" if dark else "light"]

    if ui:
        # Only when the user explicitly chose a font: change the *family* of the
        # standard named fonts (never the size -> keep each platform's native
        # point size). TkFixedFont is left as the platform monospace so the
        # aligned text panes (type chart, JSON) stay aligned.
        for name in ("TkDefaultFont", "TkTextFont", "TkMenuFont", "TkHeadingFont",
                     "TkTooltipFont", "TkIconFont", "TkSmallCaptionFont", "TkCaptionFont"):
            try:
                tkfont.nametofont(name).configure(family=ui)
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
        # Headings/emphasis: bold of whatever font is active (system or chosen).
        st.configure("Title.TLabel", background=p["bg"], foreground=p["text"],
                     font=("TkHeadingFont", 15, "bold"))
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
    return ui or ""


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


# ---------------------------------------------------------------------------
# Font picker (system fonts; default is the platform font)
# ---------------------------------------------------------------------------

def list_font_families(root):
    """Sorted, de-duplicated font families installed on this machine.
    '@'-prefixed vertical CJK variants are filtered out."""
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
    """Open a searchable font picker. Calls ``on_apply(family)`` when chosen, or
    ``on_apply(None)`` for "Use system default"."""
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
    ttk.Button(btns, text="Use system default",
               command=lambda: (on_apply(None), win.destroy())).pack(side="left")
    ttk.Button(btns, text="Cancel", command=win.destroy).pack(side="right")
    ttk.Button(btns, text="Apply", command=apply_and_close).pack(side="right", padx=6)
