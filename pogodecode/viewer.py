"""Tkinter Pokedex viewer: browse decoded GAME_MASTER data for verification.

Load a raw GAME_MASTER file (or a JSON exported by the decoder), search the
Pokemon list, and read a formatted info sheet: types, base stats, height/weight,
catch rate, fast/charge moves with power/energy/duration, evolution cost, shadow
costs, and max CP at level 40.

Run with ``python -m pogodecode.viewer`` or via the packaged ``.exe``.
"""

from __future__ import annotations

import os
import queue
import threading
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__
from .pokedex import load_pokedex


class ViewerApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"PoGo Pokedex Viewer v{__version__}")
        self.root.minsize(820, 560)
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
        ttk.Button(top, text="Export all sheets → JSON", command=self._export).pack(side="right")

        body = ttk.Frame(self.root, padding=(8, 0, 8, 8))
        body.pack(fill="both", expand=True)
        body.columnconfigure(0, weight=0)
        body.columnconfigure(1, weight=1)
        body.rowconfigure(1, weight=1)

        # left: search + list
        search = ttk.Frame(body)
        search.grid(row=0, column=0, sticky="ew", pady=(0, 4))
        ttk.Label(search, text="Search:").pack(side="left")
        self.search_var = tk.StringVar()
        self.search_var.trace_add("write", lambda *_: self._refresh_list())
        ttk.Entry(search, textvariable=self.search_var, width=24).pack(side="left", fill="x", expand=True)

        list_frame = ttk.Frame(body)
        list_frame.grid(row=1, column=0, sticky="ns")
        self.listbox = tk.Listbox(list_frame, width=34, activestyle="dotbox", exportselection=False)
        self.listbox.pack(side="left", fill="y")
        self.listbox.bind("<<ListboxSelect>>", self._on_select)
        sb = ttk.Scrollbar(list_frame, command=self.listbox.yview)
        sb.pack(side="left", fill="y")
        self.listbox.configure(yscrollcommand=sb.set)

        # right: detail
        self.detail = tk.Text(body, wrap="word", state="disabled", padx=10, pady=8)
        self.detail.grid(row=0, column=1, rowspan=2, sticky="nsew", padx=(8, 0))
        self.detail.tag_configure("h1", font=("TkDefaultFont", 14, "bold"))
        self.detail.tag_configure("h2", font=("TkDefaultFont", 11, "bold"))
        self.detail.tag_configure("dim", foreground="#666")

        self.status = ttk.Label(self.root, text="Open a GAME_MASTER file to begin.",
                                 relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

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
            dex = load_pokedex(path)
            self._events.put(("loaded", dex))
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
                    self.status.configure(
                        text=f"Loaded {len(self._keys)} Pokémon entries, "
                             f"{len(payload.moves)} moves, "
                             f"{len(payload.cp_multipliers)} CP-multiplier levels."
                    )
                elif kind == "error":
                    messagebox.showerror("Load failed", payload)
                    self.status.configure(text="Load failed.")
        except queue.Empty:
            pass
        self.root.after(100, self._drain)

    # -- list ---------------------------------------------------------------
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
        key = self._visible[sel[0]]
        self._show_sheet(self.dex.sheet(key))

    # -- detail rendering ---------------------------------------------------
    def _show_sheet(self, s: dict) -> None:
        t = self.detail
        t.configure(state="normal")
        t.delete("1.0", "end")

        t.insert("end", f"#{s['dexNumber']:04d}  {s['name']}\n", "h1")
        t.insert("end", f"{s['templateId']}\n", "dim")
        if s.get("form"):
            t.insert("end", f"Form id: {s['form']}\n", "dim")
        t.insert("end", "\n")

        t.insert("end", "Typing\n", "h2")
        t.insert("end", "  " + " / ".join(s["types"] or ["—"]) + "\n\n")

        bs = s["baseStats"]
        t.insert("end", "Base stats\n", "h2")
        t.insert("end", f"  Attack {bs['attack']}   Defense {bs['defense']}   Stamina {bs['stamina']}\n")
        if s.get("maxCpLevel40") is not None:
            t.insert("end", f"  Max CP (Level 40, perfect IV): {s['maxCpLevel40']}\n")
        t.insert("end", "\n")

        t.insert("end", "Physical / encounter\n", "h2")
        t.insert("end", f"  Height {s.get('heightM','?')} m    Weight {s.get('weightKg','?')} kg\n")
        if s.get("baseCaptureRate") is not None:
            t.insert("end", f"  Base capture rate: {s['baseCaptureRate']*100:.1f}%\n")
        t.insert("end", "\n")

        self._render_moves(t, "Fast moves", s["fastMoves"])
        self._render_moves(t, "Charge moves", s["chargeMoves"])

        if s.get("evolution"):
            e = s["evolution"]
            t.insert("end", "Evolution\n", "h2")
            t.insert("end", f"  Candy to evolve: {e.get('candyCost','?')}"
                            f"   (to species id {e.get('evolvesToId','?')})\n\n")
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

    def _render_moves(self, t: tk.Text, title: str, moves: list) -> None:
        t.insert("end", f"{title}\n", "h2")
        if not moves:
            t.insert("end", "  —\n\n")
            return
        for m in moves:
            line = f"  {m['name']}  ({m.get('type','?')})"
            if "power" in m:
                line += f"  —  power {m['power']:g}, energy {m['energy']}, {m['durationMs']/1000:g}s"
            t.insert("end", line + "\n")
        t.insert("end", "\n")

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
        import json
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
