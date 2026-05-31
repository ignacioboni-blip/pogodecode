"""Tkinter Pokédex viewer: browse decoded GAME_MASTER data for verification.

Tabs: Pokédex (filter/sort/compare), Moves, Type chart, Weather, Items,
Leagues, Templates (generic search), Validation, and Diff (compare two files).

Run with ``python -m pogodecode.viewer`` or via the packaged ``.exe``.
"""

from __future__ import annotations

import json
import os
import queue
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .pokedex import TYPE_NAMES, diff_pokedex, load_pokedex


class ViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"PoGo Pokédex Viewer v{__version__}")
        self.root.minsize(940, 640)
        self.dex = None
        self._keys: list[str] = []
        self._sheet_cache: dict = {}
        self._compare: list[str] = []
        self._events: "queue.Queue[tuple]" = queue.Queue()

        self._build()
        self.root.after(100, self._drain)

    # -- layout -------------------------------------------------------------
    def _build(self) -> None:
        top = ttk.Frame(self.root, padding=8)
        top.pack(fill="x")
        ttk.Button(top, text="Open GAME_MASTER / JSON…", command=self._open).pack(side="left")
        self.file_lbl = ttk.Label(top, text="No file loaded")
        self.file_lbl.pack(side="left", padx=10)
        ttk.Button(top, text="Export sheets → JSON", command=self._export).pack(side="right")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_pokedex_tab()
        self._build_compare_tab()
        self._build_moves_tab()
        self._build_typechart_tab()
        self._build_weather_tab()
        self._build_items_tab()
        self._build_leagues_tab()
        self._build_templates_tab()
        self._build_validation_tab()
        self._build_diff_tab()

        self.status = ttk.Label(self.root, text="Open a GAME_MASTER file to begin.",
                                 relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

    def _sheet(self, key: str) -> dict:
        if key not in self._sheet_cache:
            self._sheet_cache[key] = self.dex.sheet(key)
        return self._sheet_cache[key]

    # -- Pokédex tab --------------------------------------------------------
    def _build_pokedex_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Pokédex")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(2, weight=1)

        bar = ttk.Frame(tab)
        bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        ttk.Label(bar, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(bar, textvariable=self.search_var, width=18).pack(side="left", padx=(2, 10))
        ttk.Label(bar, text="Type:").pack(side="left")
        self.type_var = tk.StringVar(value="All")
        type_cb = ttk.Combobox(bar, textvariable=self.type_var, width=10, state="readonly",
                               values=["All"] + [TYPE_NAMES[i] for i in range(1, 19)])
        type_cb.pack(side="left", padx=(2, 10))
        type_cb.bind("<<ComboboxSelected>>", lambda *_: self._refresh_list())
        ttk.Label(bar, text="Sort:").pack(side="left")
        self.sort_var = tk.StringVar(value="Dex #")
        sort_cb = ttk.Combobox(bar, textvariable=self.sort_var, width=10, state="readonly",
                               values=["Dex #", "Attack", "Defense", "Stamina", "Max CP"])
        sort_cb.pack(side="left", padx=2)
        sort_cb.bind("<<ComboboxSelected>>", lambda *_: self._refresh_list())

        lf = ttk.Frame(tab)
        lf.grid(row=1, column=0, rowspan=2, sticky="ns", padx=4)
        self.listbox = tk.Listbox(lf, width=30, activestyle="dotbox", exportselection=False)
        self.listbox.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        sb = ttk.Scrollbar(lf, command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)
        ttk.Button(tab, text="📌 Add to Compare", command=self._add_compare).grid(
            row=0, column=0, sticky="e", padx=4)

        self.detail = tk.Text(tab, wrap="word", state="disabled", padx=10, pady=8, width=68)
        self.detail.grid(row=1, column=1, rowspan=2, sticky="nsew", padx=4, pady=4)
        for tag, font in (("h1", ("TkDefaultFont", 14, "bold")), ("h2", ("TkDefaultFont", 11, "bold"))):
            self.detail.tag_configure(tag, font=font)
        self.detail.tag_configure("dim", foreground="#666")

    def _build_compare_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Compare")
        ttk.Button(tab, text="Clear", command=self._clear_compare).pack(anchor="w", padx=4, pady=4)
        self.compare_text = tk.Text(tab, wrap="none", state="disabled",
                                    font=("Courier New", 9), padx=8, pady=8)
        self.compare_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_moves_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Moves")
        bar = ttk.Frame(tab); bar.pack(fill="x", pady=4, padx=4)
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.move_filter = tk.StringVar()
        self.move_filter.trace_add("write", lambda *_: self._refresh_moves())
        ttk.Entry(bar, textvariable=self.move_filter, width=24).pack(side="left")
        cols = ("name", "type", "cat", "power", "energy", "dur", "dps", "eps")
        heads = ("Move", "Type", "Cat", "Power", "Energy", "Dur(s)", "DPS", "EPS")
        self.moves_tv = ttk.Treeview(tab, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.moves_tv.heading(c, text=h)
            self.moves_tv.column(c, width=170 if c == "name" else 62, anchor="w")
        self.moves_tv.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_typechart_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Type chart")
        self.chart_text = tk.Text(tab, wrap="none", state="disabled",
                                  font=("Courier New", 9), padx=8, pady=8)
        self.chart_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_weather_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Weather")
        self.weather_text = tk.Text(tab, wrap="word", state="disabled", padx=10, pady=8)
        self.weather_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_items_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Items")
        cols = ("name", "id", "category")
        self.items_tv = ttk.Treeview(tab, columns=cols, show="headings")
        for c, w in (("name", 220), ("id", 80), ("category", 100)):
            self.items_tv.heading(c, text=c.title()); self.items_tv.column(c, width=w, anchor="w")
        self.items_tv.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_leagues_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Leagues")
        cols = ("name", "cap", "restricted")
        self.leagues_tv = ttk.Treeview(tab, columns=cols, show="headings")
        for c, w in (("name", 280), ("cap", 100), ("restricted", 110)):
            self.leagues_tv.heading(c, text=c.title()); self.leagues_tv.column(c, width=w, anchor="w")
        self.leagues_tv.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_templates_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Templates")
        tab.columnconfigure(1, weight=1); tab.rowconfigure(1, weight=1)
        bar = ttk.Frame(tab); bar.grid(row=0, column=0, columnspan=2, sticky="ew", padx=4, pady=4)
        ttk.Label(bar, text="Search all templates:").pack(side="left")
        self.tmpl_filter = tk.StringVar()
        self.tmpl_filter.trace_add("write", lambda *_: self._refresh_templates())
        ttk.Entry(bar, textvariable=self.tmpl_filter, width=30).pack(side="left", padx=4)
        lf = ttk.Frame(tab); lf.grid(row=1, column=0, sticky="ns", padx=4)
        self.tmpl_list = tk.Listbox(lf, width=44, exportselection=False)
        self.tmpl_list.pack(side="left", fill="y")
        self.tmpl_list.bind("<<ListboxSelect>>", self._on_template_select)
        sb = ttk.Scrollbar(lf, command=self.tmpl_list.yview); sb.pack(side="left", fill="y")
        self.tmpl_list.configure(yscrollcommand=sb.set)
        self.tmpl_text = tk.Text(tab, wrap="none", state="disabled",
                                 font=("Courier New", 9), padx=8, pady=8)
        self.tmpl_text.grid(row=1, column=1, sticky="nsew", padx=4, pady=4)

    def _build_validation_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Validation")
        self.valid_text = tk.Text(tab, wrap="word", state="disabled", padx=10, pady=8)
        self.valid_text.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_diff_tab(self) -> None:
        tab = ttk.Frame(self.nb); self.nb.add(tab, text="Diff")
        ttk.Button(tab, text="Diff loaded file against another GAME_MASTER/JSON…",
                   command=self._run_diff).pack(anchor="w", padx=4, pady=4)
        self.diff_text = tk.Text(tab, wrap="word", state="disabled",
                                 font=("Courier New", 9), padx=8, pady=8)
        self.diff_text.pack(fill="both", expand=True, padx=4, pady=4)

    # -- loading ------------------------------------------------------------
    def _open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open GAME_MASTER or decoded JSON",
            filetypes=[("All files", "*.*"), ("JSON", "*.json")])
        if not path:
            return
        self.status.configure(text=f"Loading {os.path.basename(path)} …")
        self.file_lbl.configure(text=os.path.basename(path))
        threading.Thread(target=self._load_worker, args=(path,), daemon=True).start()

    def _load_worker(self, path: str) -> None:
        try:
            self._events.put(("loaded", load_pokedex(path)))
        except Exception:  # noqa: BLE001
            self._events.put(("error", traceback.format_exc()))

    def _drain(self) -> None:
        try:
            while True:
                kind, payload = self._events.get_nowait()
                if kind == "loaded":
                    self.dex = payload
                    self._keys = payload.pokemon_keys()
                    self._sheet_cache.clear()
                    self._compare.clear()
                    self._refresh_list()
                    self._refresh_moves()
                    self._render_type_chart()
                    self._render_weather()
                    self._refresh_items()
                    self._refresh_leagues()
                    self._refresh_templates()
                    self._render_validation()
                    self.status.configure(
                        text=f"Loaded {len(self._keys)} entries, {len(payload.moves)} moves, "
                             f"{len(payload.items())} items, {len(payload.leagues())} leagues.")
                elif kind == "diff":
                    t = self.diff_text
                    t.configure(state="normal"); t.delete("1.0", "end")
                    t.insert("end", json.dumps(payload, indent=2, ensure_ascii=False))
                    t.configure(state="disabled")
                    self.status.configure(text="Diff complete.")
                elif kind == "error":
                    messagebox.showerror("Error", payload)
                    self.status.configure(text="Error.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    # -- Pokédex list/detail ------------------------------------------------
    def _refresh_list(self) -> None:
        if not self.dex:
            return
        term = self.search_var.get().strip().lower()
        type_f = self.type_var.get()
        sort = self.sort_var.get()
        rows = []
        for key in self._keys:
            label = self.dex.list_label(key)
            if term and term not in key.lower() and term not in label.lower():
                continue
            if type_f != "All" or sort != "Dex #":
                s = self._sheet(key)
                if type_f != "All" and type_f not in s["types"]:
                    continue
                rows.append((key, label, s))
            else:
                rows.append((key, label, None))
        keymap = {"Attack": "attack", "Defense": "defense", "Stamina": "stamina"}
        if sort in keymap:
            rows.sort(key=lambda r: -r[2]["baseStats"][keymap[sort]])
        elif sort == "Max CP":
            rows.sort(key=lambda r: -(r[2]["maxCpLevel40"] or 0))
        self.listbox.delete(0, "end")
        self._visible = []
        for key, label, _ in rows:
            self.listbox.insert("end", label)
            self._visible.append(key)

    def _on_select(self, _evt) -> None:
        sel = self.listbox.curselection()
        if sel and self.dex:
            self._show_sheet(self._sheet(self._visible[sel[0]]))

    def _sheet_lines(self, s: dict) -> list:
        bs = s["baseStats"]
        lines = [
            (f"#{s['dexNumber']:04d}  {s['name']}" + ("  [Mega]" if s.get("isMega") else ""), "h1"),
            (s["templateId"], "dim"), ("", None),
            ("Typing", "h2"), ("  " + " / ".join(s["types"] or ["—"]), None),
        ]
        if s.get("weakTo"):
            lines.append(("  Weak to:      " + ", ".join(s["weakTo"]), None))
        if s.get("resistantTo"):
            lines.append(("  Resistant to: " + ", ".join(s["resistantTo"]), None))
        if s.get("boostedWeather"):
            lines.append(("  Weather boost: " + ", ".join(s["boostedWeather"]), None))
        lines += [("", None), ("Base stats", "h2"),
                  (f"  Atk {bs['attack']}   Def {bs['defense']}   Sta {bs['stamina']}", None)]
        if s.get("maxCpLevel40") is not None:
            lines.append((f"  Max CP — L40: {s['maxCpLevel40']}   "
                          f"L50: {s.get('maxCpLevel50','?')}   "
                          f"L51 (best buddy): {s.get('maxCpLevel51BestBuddy','?')}", None))
        if self.dex:
            tbl = self.dex.cp_table(bs["attack"], bs["defense"], bs["stamina"], levels=[20, 30, 40, 50])
            lines.append(("  CP @ L20/30/40/50: " + " / ".join(str(r["cp"]) for r in tbl), None))
        lines += [("", None), ("Physical / encounter", "h2"),
                  (f"  Height {s.get('heightM','?')} m   Weight {s.get('weightKg','?')} kg", None)]
        if s.get("buddyDistanceKm") is not None:
            lines.append((f"  Buddy distance: {s['buddyDistanceKm']} km/candy", None))
        if s.get("baseCaptureRate") is not None:
            lines.append((f"  Base capture rate: {s['baseCaptureRate']*100:.1f}%", None))
        lines.append(("", None))
        for title, key in (("Fast moves", "fastMoves"), ("Charge moves", "chargeMoves")):
            lines.append((title, "h2"))
            if not s[key]:
                lines.append(("  —", None))
            for m in s[key]:
                extra = (f"  power {m['power']:g}, energy {m['energy']}, "
                         f"{m['durationMs']/1000:g}s, DPS {m.get('dps','?')}") if "power" in m else ""
                lines.append((f"  {m['name']} ({m.get('type','?')}){extra}", None))
            lines.append(("", None))
        if s.get("evolution"):
            lines.append(("Evolution", "h2"))
            for e in s["evolution"]:
                lines.append((f"  → {e.get('evolvesTo') or e.get('evolvesToId')}"
                              f" ({e.get('candyCost','?')} candy)", None))
        return lines

    def _show_sheet(self, s: dict) -> None:
        t = self.detail
        t.configure(state="normal"); t.delete("1.0", "end")
        for text, tag in self._sheet_lines(s):
            t.insert("end", text + "\n", tag or ())
        t.configure(state="disabled")

    # -- compare ------------------------------------------------------------
    def _add_compare(self) -> None:
        sel = self.listbox.curselection()
        if not sel or not self.dex:
            return
        key = self._visible[sel[0]]
        if key not in self._compare:
            self._compare.append(key)
            self._compare = self._compare[-4:]
        self._render_compare()
        self.nb.select(1)

    def _clear_compare(self) -> None:
        self._compare.clear(); self._render_compare()

    def _render_compare(self) -> None:
        t = self.compare_text
        t.configure(state="normal"); t.delete("1.0", "end")
        if not self._compare:
            t.insert("end", "Select a Pokémon in the Pokédex tab and click 'Add to Compare'.")
            t.configure(state="disabled"); return
        sheets = [self._sheet(k) for k in self._compare]

        def row(label, vals):
            return label.ljust(20) + "".join(str(v).ljust(20) for v in vals) + "\n"
        t.insert("end", row("", [s["name"] for s in sheets]))
        t.insert("end", row("Type", [" / ".join(s["types"]) for s in sheets]))
        t.insert("end", row("Attack", [s["baseStats"]["attack"] for s in sheets]))
        t.insert("end", row("Defense", [s["baseStats"]["defense"] for s in sheets]))
        t.insert("end", row("Stamina", [s["baseStats"]["stamina"] for s in sheets]))
        t.insert("end", row("Max CP L40", [s["maxCpLevel40"] for s in sheets]))
        t.insert("end", row("Capture %", [round((s.get("baseCaptureRate") or 0)*100, 1) for s in sheets]))
        t.insert("end", row("Buddy km", [s.get("buddyDistanceKm") for s in sheets]))
        t.insert("end", row("Weak to", [",".join(s.get("weakTo", []))[:18] for s in sheets]))
        t.configure(state="disabled")

    # -- other tabs ---------------------------------------------------------
    def _refresh_moves(self) -> None:
        term = self.move_filter.get().strip().lower()
        self.moves_tv.delete(*self.moves_tv.get_children())
        for m in self.dex.all_moves():
            if term and term not in m["name"].lower() and term not in m["type"].lower():
                continue
            self.moves_tv.insert("", "end", values=(
                m["name"], m["type"], m["category"], f"{m['power']:g}",
                m["energy"], f"{m['durationMs']/1000:g}", m["dps"], m["eps"]))

    def _render_type_chart(self) -> None:
        chart = self.dex.type_chart_named()
        defs = [TYPE_NAMES[i] for i in range(1, 19)]
        t = self.chart_text
        t.configure(state="normal"); t.delete("1.0", "end")
        t.insert("end", "ATK\\DEF".ljust(10) + "".join(d[:4].rjust(6) for d in defs) + "\n")
        for atk in defs:
            r = chart.get(atk, {})
            t.insert("end", atk.ljust(10) + "".join(f"{r.get(d,1.0):6.2f}" for d in defs) + "\n")
        t.insert("end", "\n1.60 super-effective · 0.625 not-very · 0.391 double-resist\n")
        t.configure(state="disabled")

    def _render_weather(self) -> None:
        t = self.weather_text
        t.configure(state="normal"); t.delete("1.0", "end")
        for w, types in self.dex.weather_summary().items():
            t.insert("end", f"{w:<16}{', '.join(types)}\n")
        t.configure(state="disabled")

    def _refresh_items(self) -> None:
        self.items_tv.delete(*self.items_tv.get_children())
        for it in self.dex.items():
            self.items_tv.insert("", "end", values=(it["name"], it["itemId"], it["category"]))

    def _refresh_leagues(self) -> None:
        self.leagues_tv.delete(*self.leagues_tv.get_children())
        for lg in self.dex.leagues():
            self.leagues_tv.insert("", "end", values=(
                lg["name"], lg["cpCap"] or "—", lg["restrictedCount"]))

    def _refresh_templates(self) -> None:
        if not self.dex:
            return
        term = self.tmpl_filter.get().strip()
        ids = self.dex.search_templates(term) if term else self.dex.template_ids()[:500]
        self.tmpl_list.delete(0, "end")
        for tid in ids:
            self.tmpl_list.insert("end", tid)

    def _on_template_select(self, _evt) -> None:
        sel = self.tmpl_list.curselection()
        if not sel:
            return
        tid = self.tmpl_list.get(sel[0])
        t = self.tmpl_text
        t.configure(state="normal"); t.delete("1.0", "end")
        t.insert("end", json.dumps(self.dex.template(tid), indent=2, ensure_ascii=False))
        t.configure(state="disabled")

    def _render_validation(self) -> None:
        t = self.valid_text
        t.configure(state="normal"); t.delete("1.0", "end")
        t.insert("end", json.dumps(self.dex.validate(), indent=2, ensure_ascii=False))
        t.configure(state="disabled")

    def _run_diff(self) -> None:
        if not self.dex:
            messagebox.showinfo("Nothing loaded", "Open a GAME_MASTER file first.")
            return
        other = filedialog.askopenfilename(title="Choose the OTHER GAME_MASTER / JSON",
                                           filetypes=[("All files", "*.*"), ("JSON", "*.json")])
        if not other:
            return
        self.status.configure(text="Diffing…")
        threading.Thread(target=self._diff_worker, args=(other,), daemon=True).start()

    def _diff_worker(self, other: str) -> None:
        try:
            report = diff_pokedex(self.dex, load_pokedex(other))
            self._events.put(("diff", report))
        except Exception:  # noqa: BLE001
            self._events.put(("error", traceback.format_exc()))

    # -- export -------------------------------------------------------------
    def _export(self) -> None:
        if not self.dex:
            messagebox.showinfo("Nothing loaded", "Open a GAME_MASTER file first.")
            return
        path = filedialog.asksaveasfilename(title="Export Pokédex sheets",
                                            defaultextension=".json", filetypes=[("JSON", "*.json")])
        if not path:
            return
        with open(path, "w", encoding="utf-8") as fh:
            json.dump(self.dex.all_sheets(), fh, indent=2, ensure_ascii=False)
        self.status.configure(text=f"Exported {len(self._keys)} sheets → {path}")


def main() -> int:
    root = tk.Tk()
    ViewerApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
