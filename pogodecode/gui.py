"""Tkinter desktop UI for the GAME_MASTER decoder.

Pick a GAME_MASTER file, decode it, and export clean JSON. Decoding runs on a
background thread so the window stays responsive on large files.

Run directly with ``python -m pogodecode.gui`` or via the packaged ``.exe``.
"""

from __future__ import annotations

import os
import queue
import threading
import time
import traceback

import tkinter as tk
from tkinter import filedialog, messagebox, ttk

from . import __version__, _config, _icon, _theme, write_json
from .gamemaster import decode_game_master
from .protobuf_decoder import ProtobufDecodeError


class DecoderApp:
    def __init__(self, root: tk.Tk) -> None:
        self.root = root
        self.root.title(f"PoGo GAME_MASTER Decoder v{__version__}")
        self.root.minsize(640, 460)
        _icon.apply_icon(root)
        self._dark = tk.BooleanVar(value=bool(_config.load().get("dark", False)))
        _theme.apply_theme(root, dark=self._dark.get())

        self.input_path = tk.StringVar()
        self.output_path = tk.StringVar()
        self.minify = tk.BooleanVar(value=False)
        self._events: "queue.Queue[tuple]" = queue.Queue()
        self._worker: threading.Thread | None = None

        self._build_menu()
        self._build_widgets()
        self.root.after(100, self._drain_events)

    def _build_menu(self) -> None:
        menubar = tk.Menu(self.root)
        viewm = tk.Menu(menubar, tearoff=0)
        viewm.add_checkbutton(label="Dark mode", variable=self._dark,
                              command=self._toggle_dark)
        menubar.add_cascade(label="View", menu=viewm)
        helpm = tk.Menu(menubar, tearoff=0)
        helpm.add_command(label="About", command=self._about)
        menubar.add_cascade(label="Help", menu=helpm)
        self.root.config(menu=menubar)

    def _toggle_dark(self) -> None:
        dark = self._dark.get()
        _theme.apply_theme(self.root, dark=dark)
        data = _config.load(); data["dark"] = dark; _config.save(data)

    def _about(self) -> None:
        from tkinter import messagebox
        messagebox.showinfo(
            "About",
            f"PoGo GAME_MASTER Decoder\nVersion {__version__}\n\n"
            "Schema-free decoder for the Pokémon GO GAME_MASTER file. MIT licensed.\n"
            "Not affiliated with Niantic, Nintendo, or The Pokémon Company.\n"
            "Ships no game data — it only decodes a file you already have.")

    # -- layout -------------------------------------------------------------
    def _build_widgets(self) -> None:
        pad = {"padx": 8, "pady": 4}
        frm = ttk.Frame(self.root, padding=12)
        frm.pack(fill="both", expand=True)
        frm.columnconfigure(1, weight=1)

        ttk.Label(frm, text="GAME_MASTER file:").grid(row=0, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.input_path).grid(row=0, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse...", command=self._pick_input).grid(row=0, column=2, **pad)

        ttk.Label(frm, text="Save JSON to:").grid(row=1, column=0, sticky="w", **pad)
        ttk.Entry(frm, textvariable=self.output_path).grid(row=1, column=1, sticky="ew", **pad)
        ttk.Button(frm, text="Browse...", command=self._pick_output).grid(row=1, column=2, **pad)

        opts = ttk.Frame(frm)
        opts.grid(row=2, column=0, columnspan=3, sticky="w", **pad)
        ttk.Checkbutton(opts, text="Minify JSON (smaller file)", variable=self.minify).pack(side="left")

        self.decode_btn = ttk.Button(frm, text="Decode → JSON", command=self._start_decode)
        self.decode_btn.grid(row=3, column=0, columnspan=3, sticky="ew", **pad)

        self.progress = ttk.Progressbar(frm, mode="indeterminate")
        self.progress.grid(row=4, column=0, columnspan=3, sticky="ew", **pad)

        ttk.Label(frm, text="Log:").grid(row=5, column=0, sticky="w", **pad)
        self.log = tk.Text(frm, height=12, wrap="word", state="disabled")
        self.log.grid(row=6, column=0, columnspan=3, sticky="nsew", **pad)
        frm.rowconfigure(6, weight=1)

        scroll = ttk.Scrollbar(frm, command=self.log.yview)
        scroll.grid(row=6, column=3, sticky="ns")
        self.log.configure(yscrollcommand=scroll.set)

        self.status = ttk.Label(self.root, text="Ready.", relief="sunken", anchor="w")
        self.status.pack(fill="x", side="bottom")

        self._log("Select a GAME_MASTER file and click Decode.")
        self._log("Output is schema-free JSON: template ids are exact; settings "
                  "use numeric protobuf field numbers as keys.")

    # -- file pickers -------------------------------------------------------
    def _pick_input(self) -> None:
        path = filedialog.askopenfilename(
            title="Select GAME_MASTER file",
            initialdir=_config.last_dir() or None,
            filetypes=[("All files", "*.*"), ("GAME_MASTER", "*GAME_MASTER*")],
        )
        if path:
            _config.set_last_dir(path)
            self.input_path.set(path)
            if not self.output_path.get():
                self.output_path.set(os.path.splitext(path)[0] + ".json"
                                     if os.path.splitext(path)[1] else path + ".json")

    def _pick_output(self) -> None:
        path = filedialog.asksaveasfilename(
            title="Save decoded JSON",
            initialdir=_config.last_dir() or None,
            defaultextension=".json",
            filetypes=[("JSON", "*.json"), ("All files", "*.*")],
        )
        if path:
            _config.set_last_dir(path)
            self.output_path.set(path)

    # -- logging / status ---------------------------------------------------
    def _log(self, message: str) -> None:
        self.log.configure(state="normal")
        self.log.insert("end", message + "\n")
        self.log.see("end")
        self.log.configure(state="disabled")

    def _set_status(self, text: str) -> None:
        self.status.configure(text=text)

    # -- decode workflow ----------------------------------------------------
    def _start_decode(self) -> None:
        if self._worker and self._worker.is_alive():
            return
        in_path = self.input_path.get().strip()
        out_path = self.output_path.get().strip()
        if not in_path:
            messagebox.showwarning("No file", "Please choose a GAME_MASTER file first.")
            return
        if not os.path.isfile(in_path):
            messagebox.showerror("Not found", f"File does not exist:\n{in_path}")
            return
        if not out_path:
            out_path = in_path + ".json"
            self.output_path.set(out_path)

        self.decode_btn.configure(state="disabled")
        self.progress.start(12)
        self._set_status("Decoding...")
        self._log(f"Decoding {in_path} ...")

        self._worker = threading.Thread(
            target=self._decode_worker,
            args=(in_path, out_path, self.minify.get()),
            daemon=True,
        )
        self._worker.start()

    def _decode_worker(self, in_path: str, out_path: str, minify: bool) -> None:
        try:
            started = time.time()
            result = decode_game_master(in_path)
            write_json(result, out_path, pretty=not minify)
            elapsed = time.time() - started
            self._events.put(("done", result["meta"], out_path, elapsed))
        except ProtobufDecodeError as exc:
            self._events.put(("error", f"This does not look like a GAME_MASTER protobuf:\n{exc}"))
        except Exception:  # noqa: BLE001 - surface anything to the UI
            self._events.put(("error", traceback.format_exc()))

    def _drain_events(self) -> None:
        try:
            while True:
                event = self._events.get_nowait()
                kind = event[0]
                if kind == "done":
                    _, meta, out_path, elapsed = event
                    self.progress.stop()
                    self.decode_btn.configure(state="normal")
                    self._log(
                        f"Done in {elapsed:.2f}s: {meta['templateCount']} templates, "
                        f"{meta['categoryCount']} categories, "
                        f"{meta['skippedEntries']} skipped."
                    )
                    self._log(f"Saved JSON -> {out_path}")
                    self._set_status(f"Decoded {meta['templateCount']} templates.")
                    messagebox.showinfo(
                        "Decoded",
                        f"Decoded {meta['templateCount']} templates to:\n{out_path}",
                    )
                elif kind == "error":
                    _, message = event
                    self.progress.stop()
                    self.decode_btn.configure(state="normal")
                    self._log("ERROR:\n" + message)
                    self._set_status("Error.")
                    messagebox.showerror("Decode failed", message)
        except queue.Empty:
            pass
        self.root.after(100, self._drain_events)


def main() -> int:
    root = tk.Tk()
    DecoderApp(root)
    root.mainloop()
    return 0


if __name__ == "__main__":  # pragma: no cover
    raise SystemExit(main())
