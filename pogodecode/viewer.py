"""Tkinter Pokédex viewer: browse decoded GAME_MASTER data for verification.

Tabs:
  * Pokédex   - searchable list + info sheet (stats, typing, weaknesses,
                moves, evolution/shadow costs, Mega forms, max CP, CP table)
  * Moves     - every move with type / power / energy / duration / DPS / EPS
  * Type chart- the full 18x18 attack-effectiveness matrix
  * Validation- a sanity-check report over the whole file

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
from .pokedex import TYPE_NAMES, load_pokedex


class ViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"PoGo Pokédex Viewer v{__version__}")
        self.root.minsize(900, 600)
        self.dex = None
        self._keys: list[str] = []
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
        ttk.Button(top, text="Export Pokédex sheets → JSON", command=self._export).pack(side="right")

        self.nb = ttk.Notebook(self.root)
        self.nb.pack(fill="both", expand=True, padx=8, pady=(0, 8))
        self._build_pokedex_tab()
        self._build_moves_tab()
        self._build_typechart_tab()
        self._build_validation_tab()

        self.status = ttk.Label(self.root, text="Open a GAME_MASTER file to begin.",
                                 relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

    def _build_pokedex_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Pokédex")
        tab.columnconfigure(1, weight=1)
        tab.rowconfigure(1, weight=1)

        search = ttk.Frame(tab)
        search.grid(row=0, column=0, sticky="ew", pady=4, padx=4)
        ttk.Label(search, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(search, textvariable=self.search_var, width=22).pack(side="left", fill="x", expand=True)

        lf = ttk.Frame(tab)
        lf.grid(row=1, column=0, sticky="ns", padx=4)
        self.listbox = tk.Listbox(lf, width=32, activestyle="dotbox", exportselection=False)
        self.listbox.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        sb = ttk.Scrollbar(lf, command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)

        self.detail = tk.Text(tab, wrap="word", state="disabled", padx=10, pady=8, width=70)
        self.detail.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=4, pady=4)
        self.detail.tag_configure("h1", font=("TkDefaultFont", 14, "bold"))
        self.detail.tag_configure("h2", font=("TkDefaultFont", 11, "bold"))
        self.detail.tag_configure("dim", foreground="#666")

    def _build_moves_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Moves")
        bar = ttk.Frame(tab)
        bar.pack(fill="x", pady=4, padx=4)
        ttk.Label(bar, text="Filter:").pack(side="left")
        self.move_filter = tk.StringVar()
        self.move_filter.trace_add("write", lambda *_: self._refresh_moves())
        ttk.Entry(bar, textvariable=self.move_filter, width=24).pack(side="left")

        cols = ("name", "type", "cat", "power", "energy", "dur", "dps", "eps")
        heads = ("Move", "Type", "Cat", "Power", "Energy", "Dur(s)", "DPS", "EPS")
        self.moves_tv = ttk.Treeview(tab, columns=cols, show="headings")
        for c, h in zip(cols, heads):
            self.moves_tv.heading(c, text=h)
            self.moves_tv.column(c, width=90 if c == "name" else 60, anchor="w")
        self.moves_tv.column("name", width=170)
        self.moves_tv.pack(fill="both", expand=True, padx=4, pady=4)

    def _build_typechart_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Type chart")
        self.chart_text = tk.Text(tab, wrap="none", state="disabled",
                                  font=("Courier New", 9), padx=8, pady=8)
        self.chart_text.pack(fill="both", expand=True, padx=4, pady=4)
        xsb = ttk.Scrollbar(tab, orient="horizontal", command=self.chart_text.xview)
        xsb.pack(fill="x")
        self.chart_text.configure(xscrollcommand=xsb.set)

    def _build_validation_tab(self) -> None:
        tab = ttk.Frame(self.nb)
        self.nb.add(tab, text="Validation")
        self.valid_text = tk.Text(tab, wrap="word", state="disabled", padx=10, pady=8)
        self.valid_text.pack(fill="both", expand=True, padx=4, pady=4)

    # -- loading ------------------------------------------------------------
    def _open(self) -> None:
        path = filedialog.askopenfilename(
            title="Open GAME_MASTER or decoded JSON",
            filetypes=[("All files", "*.*"), ("JSON", "*.json")],
        )
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
                    self._refresh_list()
                    self._refresh_moves()
                    self._render_type_chart()
                    self._render_validation()
                    self.status.configure(
                        text=f"Loaded {len(self._keys)} entries, "
                             f"{len(payload.moves)} moves, "
                             f"{len(payload.type_chart)} type rows, "
                             f"{len(payload.cp_multipliers)} CP levels."
                    )
                elif kind == "error":
                    messagebox.showerror("Load failed", payload)
                    self.status.configure(text="Load failed.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    # -- pokedex list/detail ------------------------------------------------
    def _refresh_list(self) -> None:
        if not self.dex:
            return
        term = self.search_var.get().strip().lower()
        self.listbox.delete(0, "end")
        self._visible: list[str] = []
        for key in self._keys:
            label = self.dex.list_label(key)
            if term and term not in key.lower() and term not in label.lower():
                continue
            self.listbox.insert("end", label)
            self._visible.append(key)

    def _on_select(self, _evt) -> None:
        sel = self.listbox.curselection()
        if not sel or not self.dex:
            return
        self._show_sheet(self.dex.sheet(self._visible[sel[0]]))

    def _show_sheet(self, s: dict) -> None:
        t = self.detail
        t.configure(state="normal")
        t.delete("1.0", "end")
        tag = "  [Mega]" if s.get("isMega") else ""
        t.insert("end", f"#{s['dexNumber']:04d}  {s['name']}{tag}\n", "h1")
        t.insert("end", f"{s['templateId']}\n\n", "dim")

        t.insert("end", "Typing\n", "h2")
        t.insert("end", "  " + " / ".join(s["types"] or ["—"]) + "\n")
        if s.get("weakTo"):
            t.insert("end", "  Weak to:      " + ", ".join(s["weakTo"]) + "\n")
        if s.get("resistantTo"):
            t.insert("end", "  Resistant to: " + ", ".join(s["resistantTo"]) + "\n")
        t.insert("end", "\n")

        bs = s["baseStats"]
        t.insert("end", "Base stats\n", "h2")
        t.insert("end", f"  Attack {bs['attack']}   Defense {bs['defense']}   Stamina {bs['stamina']}\n")
        if s.get("maxCpLevel40") is not None:
            t.insert("end", f"  Max CP (Level 40, perfect IV): {s['maxCpLevel40']}\n")
        if self.dex:
            tbl = self.dex.cp_table(bs["attack"], bs["defense"], bs["stamina"],
                                    levels=[20, 30, 40, 50])
            t.insert("end", "  CP @ L20/30/40/50: "
                     + " / ".join(str(r["cp"]) for r in tbl) + "\n")
        t.insert("end", "\n")

        t.insert("end", "Physical / encounter\n", "h2")
        t.insert("end", f"  Height {s.get('heightM','?')} m    Weight {s.get('weightKg','?')} kg\n")
        if s.get("baseCaptureRate") is not None:
            t.insert("end", f"  Base capture rate: {s['baseCaptureRate']*100:.1f}%\n")
        t.insert("end", "\n")

        self._render_moves_block(t, "Fast moves", s["fastMoves"])
        self._render_moves_block(t, "Charge moves", s["chargeMoves"])

        if s.get("evolution"):
            e = s["evolution"]
            t.insert("end", "Evolution\n", "h2")
            t.insert("end", f"  Candy to evolve: {e.get('candyCost','?')}\n\n")
        if s.get("secondChargeMove"):
            sm = s["secondChargeMove"]
            t.insert("end", "Second charge move unlock\n", "h2")
            t.insert("end", f"  {sm.get('stardust','?')} stardust + {sm.get('candy','?')} candy\n\n")
        if s.get("shadow"):
            sh = s["shadow"]
            t.insert("end", "Shadow / purification\n", "h2")
            t.insert("end", f"  Purify: {sh.get('purificationStardust','?')} stardust "
                            f"+ {sh.get('purificationCandy','?')} candy\n\n")
        t.configure(state="disabled")

    def _render_moves_block(self, t: tk.Text, title: str, moves: list) -> None:
        t.insert("end", f"{title}\n", "h2")
        if not moves:
            t.insert("end", "  —\n\n")
            return
        for m in moves:
            line = f"  {m['name']}  ({m.get('type','?')})"
            if "power" in m:
                line += (f"  —  power {m['power']:g}, energy {m['energy']}, "
                         f"{m['durationMs']/1000:g}s, DPS {m.get('dps','?')}")
            t.insert("end", line + "\n")
        t.insert("end", "\n")

    # -- moves tab ----------------------------------------------------------
    def _refresh_moves(self) -> None:
        if not self.dex:
            return
        term = self.move_filter.get().strip().lower()
        self.moves_tv.delete(*self.moves_tv.get_children())
        for m in self.dex.all_moves():
            if term and term not in m["name"].lower() and term not in m["type"].lower():
                continue
            self.moves_tv.insert("", "end", values=(
                m["name"], m["type"], m["category"], f"{m['power']:g}",
                m["energy"], f"{m['durationMs']/1000:g}", m["dps"], m["eps"],
            ))

    # -- type chart tab -----------------------------------------------------
    def _render_type_chart(self) -> None:
        if not self.dex:
            return
        chart = self.dex.type_chart_named()
        defenders = [TYPE_NAMES[i] for i in range(1, 19)]
        t = self.chart_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "ATK \\ DEF".ljust(10) + "".join(d[:4].rjust(6) for d in defenders) + "\n")
        for atk in defenders:
            row = chart.get(atk, {})
            line = atk.ljust(10) + "".join(f"{row.get(d,1.0):6.2f}" for d in defenders)
            t.insert("end", line + "\n")
        t.insert("end", "\n1.60 = super effective, 0.625 = not very, 0.391 = double resist.\n")
        t.configure(state="disabled")

    # -- validation tab -----------------------------------------------------
    def _render_validation(self) -> None:
        if not self.dex:
            return
        r = self.dex.validate()
        t = self.valid_text
        t.configure(state="normal")
        t.delete("1.0", "end")
        t.insert("end", "Validation report\n", )
        t.insert("end", json.dumps(r, indent=2, ensure_ascii=False))
        t.configure(state="disabled")

    # -- export -------------------------------------------------------------
    def _export(self) -> None:
        if not self.dex:
            messagebox.showinfo("Nothing loaded", "Open a GAME_MASTER file first.")
            return
        path = filedialog.asksaveasfilename(
            title="Export Pokédex sheets", defaultextension=".json",
            filetypes=[("JSON", "*.json")],
        )
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
