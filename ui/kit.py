"""Shared building blocks mixed into the App window."""
import threading, time, tkinter
from tkinter import messagebox, ttk
import customtkinter as ctk
from core.i18n import t
from .theme import (ACCENT, ACCENT_H, BG, BORDER, CARD, CARD2, FONT, HOVER2, MUTED, ON_ACCENT, SEG_SEL, SEL, SEL_H, TABLE, TEXT,
                    MODE, F, IF, icon)

TIPS = {"on": True}  # tooltips can be turned off on the About page

TIP_TEXT = {}  # widget path -> text (or a function returning text)

class Tooltips:
    """One tooltip for the whole window. Every 120 ms it looks at the widget under the pointer (and its parents);
    if one of them has a tip and the pointer rests there for 0.45 s, the tip pops up next to the pointer.
    This does not depend on <Enter>/<Leave> events, which customtkinter widgets do not deliver reliably."""
    def __init__(self, root):
        self.root, self.owner, self.since, self.win = root, None, 0.0, None
        self._poll()

    def _find(self):
        try:
            x, y = self.root.winfo_pointerxy()
            w = self.root.winfo_containing(x, y)
        except (KeyError, tkinter.TclError):  # pointer over a menu or a destroyed widget
            return None
        while w is not None:
            if str(w) in TIP_TEXT:
                return w
            w = getattr(w, "master", None)
        return None

    def _poll(self):
        w = self._find() if TIPS["on"] else None
        if w is not self.owner:
            self._hide()
            self.owner, self.since = w, time.monotonic()
        elif w is not None and self.win is None and time.monotonic() - self.since > 0.45:
            self._show(w)
        self.root.after(120, self._poll)

    def _show(self, w):
        text = TIP_TEXT.get(str(w))
        text = text() if callable(text) else text
        if not text:
            return
        self.win = tw = tkinter.Toplevel(self.root)
        tw.wm_overrideredirect(True)
        tw.attributes("-topmost", True)
        tw.configure(bg=BORDER)
        tkinter.Label(tw, text=text, justify="left", wraplength=380, bg=CARD2, fg=TEXT, font=(FONT[0], 10),
                      padx=10, pady=7).pack(padx=1, pady=1)
        tw.update_idletasks()
        x, y = self.root.winfo_pointerx() + 14, self.root.winfo_pointery() + 18
        sw, sh = tw.winfo_screenwidth(), tw.winfo_screenheight()
        if x + tw.winfo_reqwidth() > sw:
            x = max(0, x - tw.winfo_reqwidth() - 28)
        if y + tw.winfo_reqheight() > sh:
            y = max(0, y - tw.winfo_reqheight() - 36)
        tw.geometry(f"+{x}+{y}")

    def _hide(self):
        if self.win is not None:
            self.win.destroy()
            self.win = None

def tip(widget, text):
    """Attach a tooltip (text or a function returning text) to a widget; it also covers the widget's children."""
    if text:
        key = str(widget)
        if key not in TIP_TEXT:  # forget the tip with the widget (Tk reuses widget names)
            tkinter.Misc.bind(widget, "<Destroy>", lambda e: TIP_TEXT.pop(key, None) if str(e.widget) == key else None,
                              "+")
        TIP_TEXT[key] = text
    return widget

# Lists and text boxes scroll themselves; the page must not scroll with them.
_valid = ctk.CTkScrollableFrame._check_if_valid_scroll
def _check(self, widget):
    if isinstance(widget, (ttk.Treeview, tkinter.Text, tkinter.Listbox)) or getattr(widget, "own_scroll", False):
        return False
    return _valid(self, widget) if hasattr(widget, "master") else False
ctk.CTkScrollableFrame._check_if_valid_scroll = _check

class Kit:
    # ---- threading ----
    def ui(self, fn):
        self.q.put(fn)

    def bg(self, work, done=None, fail=None):
        def run():
            try:
                import pythoncom
                pythoncom.CoInitialize()  # WMI needs COM in every thread
            except Exception:
                pass
            try:
                r = work()
                if done:
                    self.ui(lambda: done(r))
            except Exception as e:
                msg = str(e)
                self.ui(lambda: fail(msg) if fail else messagebox.showerror(t("Error"), msg))
        threading.Thread(target=run, daemon=True).start()

    def cached(self, key, fn, default=None):
        """Last result of fn (a slow reading such as GPU counters) without waiting for it: fn runs in a worker
        thread and the next call gets the new value, so a timer never blocks the window."""
        c = self.__dict__.setdefault("_cache", {})
        val, busy = c.get(key, (default, False))
        if not busy:
            c[key] = (val, True)
            def run():
                try:
                    import pythoncom
                    pythoncom.CoInitialize()
                except Exception:
                    pass
                try:
                    v = fn()
                except Exception:
                    v = val
                c[key] = (v, False)
            threading.Thread(target=run, daemon=True).start()
        return val

    def moving(self):
        """True while the window is being dragged or resized (and briefly after), when timers skip their work so
        the window follows the mouse smoothly."""
        return time.monotonic() - getattr(self, "_moved_at", 0) < 0.4

    def every(self, ms, fn, alive, page=None):
        """Run fn every ms while `alive` exists, only when `page` is the visible page."""
        def tick():
            if not alive.winfo_exists():
                return
            if self.moving():
                self.after(200, tick)
                return
            if page is None or self.current == page:
                try:
                    fn()
                except Exception:
                    pass
            self.after(ms, tick)
        self.after(50, tick)

    # ---- widgets ----
    def card(self, parent, title, sub=None, actions=(), tooltip=None):
        """A settings card. `sub` (the long explanation) is shown as a tooltip on the title and the (i) icon."""
        c = ctk.CTkFrame(parent, fg_color=CARD, corner_radius=14)
        grid_cell = hasattr(parent, "wid")  # dashboard widget: fill the grid cell so a row lines up
        c.pack(fill="both" if grid_cell else "x", expand=grid_cell, padx=4, pady=3)
        head = ctk.CTkFrame(c, fg_color="transparent")
        head.pack(fill="x", padx=16, pady=(12, 0))
        title_lbl = ctk.CTkLabel(head, text=title, font=F(15, "bold"), text_color=TEXT)
        title_lbl.pack(side="left")
        if sub or tooltip:
            info = ctk.CTkLabel(head, text=icon("info") or "ⓘ", font=IF(13), text_color=MUTED, cursor="question_arrow")
            info.pack(side="left", padx=(6, 0))
            tip(info, tooltip or sub)
            tip(title_lbl, tooltip or sub)
        for text, cmd in reversed(actions):
            ctk.CTkButton(head, text=text, width=30, height=26, corner_radius=8, font=F(14), fg_color="transparent",
                          hover_color=HOVER2, text_color=MUTED, command=cmd).pack(side="right", padx=1)
        body = ctk.CTkFrame(c, fg_color="transparent", height=1)
        body.pack(fill="both", expand=True, padx=16, pady=(8, 14))
        c.head = head
        return body

    def details(self, parent, text=None):
        """Collapsible 'Advanced settings' section; returns the inner frame."""
        from core.i18n import t as _t
        holder = ctk.CTkFrame(parent, fg_color="transparent", height=1)
        holder.pack(fill="x", pady=(6, 0))
        inner = ctk.CTkFrame(holder, fg_color="transparent", height=1)
        label = text or _t("Advanced settings")
        def toggle():
            if inner.winfo_ismapped():
                inner.pack_forget()
                btn.configure(text="▸ " + label)
            else:
                inner.pack(fill="x", pady=(4, 0))
                btn.configure(text="▾ " + label)
        btn = ctk.CTkButton(holder, text="▸ " + label, command=toggle, height=28, anchor="w", font=F(13),
                            fg_color="transparent", hover_color=HOVER2, text_color=MUTED, corner_radius=8)
        btn.pack(anchor="w")
        return inner

    def row(self, parent, pady=0):
        r = ctk.CTkFrame(parent, fg_color="transparent", height=1)  # empty rows must not keep the 200 px default
        r.pack(fill="x", pady=pady)
        return r

    def label(self, parent, text="", size=13, bold=False, muted=False, wrap=0, **kw):
        kw.setdefault("text_color", MUTED if muted else TEXT)
        return ctk.CTkLabel(parent, text=text, font=F(size, "bold" if bold else "normal"), wraplength=wrap,
                            justify="left", **kw)

    def button(self, parent, text, cmd, primary=True, tooltip=None, **kw):
        b = ctk.CTkButton(parent, text=text, command=cmd, height=34, corner_radius=8, font=F(13, "bold" if primary else "normal"),
                          fg_color=ACCENT if primary else CARD2, hover_color=ACCENT_H if primary else HOVER2,
                          text_color=ON_ACCENT if primary else TEXT, border_width=0 if primary else 1,
                          text_color_disabled=ON_ACCENT if primary else MUTED,
                          border_color=BORDER, **kw)
        if tooltip:
            tip(b, tooltip)
        return b

    def seg(self, parent, values, command=None):
        return ctk.CTkSegmentedButton(parent, values=values, command=command, height=32, font=F(13), corner_radius=8,
                                      fg_color=CARD2, unselected_color=CARD2, unselected_hover_color=HOVER2,
                                      selected_color=SEG_SEL, selected_hover_color=SEG_SEL, text_color=TEXT,
                                      text_color_disabled=MUTED)

    def console(self, parent, h=200):
        box = ctk.CTkTextbox(parent, height=h, fg_color=TABLE, text_color=TEXT, font=("Consolas", 12), corner_radius=8,
                             border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True, pady=(8, 0))
        return box

    def write(self, box, msg, clear=False):
        def f():
            if clear:
                box.delete("1.0", "end")
            box.insert("end", msg + "\n")
            box.see("end")
        self.ui(f)

    def switch_row(self, parent, title, desc, value, on_change, glyph=None):
        """Title on the left, switch on the right; `desc` becomes the row's tooltip."""
        r = self.row(parent, 4)
        if glyph and icon(glyph):
            ctk.CTkLabel(r, text=icon(glyph), font=IF(16), text_color=TEXT, width=28).pack(side="left", padx=(0, 8))
        lbl = self.label(r, title, 14)
        lbl.pack(side="left")
        sw = ctk.CTkSwitch(r, text="", progress_color=ACCENT, button_color="#ffffff" if MODE[0] == "light" else TEXT,
                           fg_color="#8a8a8a" if MODE[0] == "light" else HOVER2, width=44)
        sw.pack(side="right")
        if value:
            sw.select()
        sw.configure(command=lambda: on_change(bool(sw.get())))
        if desc:
            tip(r, desc)
        return sw

    def table_style(self):
        st = ttk.Style()
        st.theme_use("clam")
        st.configure("D.Treeview", background=TABLE, fieldbackground=TABLE, foreground=TEXT, rowheight=30,
                     borderwidth=0, bordercolor=BORDER, lightcolor=TABLE, darkcolor=TABLE, font=(FONT[0], 10))
        st.configure("D.Treeview.Heading", background=CARD, foreground=MUTED, relief="flat", borderwidth=0,
                     bordercolor=BORDER, lightcolor=CARD, darkcolor=CARD, font=(FONT[0], 10))
        st.map("D.Treeview", background=[("selected", SEL_H)], foreground=[("selected", TEXT)])
        st.map("D.Treeview.Heading", background=[("active", HOVER2)])

    def table(self, parent, cols, widths, height=8, tags=None, scroll=True):
        """cols: [(key, heading)]. The list scrolls on its own (the page does not move with it)."""
        box = ctk.CTkFrame(parent, fg_color=TABLE, corner_radius=8, border_width=1, border_color=BORDER)
        box.pack(fill="both", expand=True, pady=(8, 0))
        tree = ttk.Treeview(box, columns=[c for c, _ in cols], show="headings", style="D.Treeview", height=height)
        for (c, h), w in zip(cols, widths):
            tree.heading(c, text=h, anchor="w")
            tree.column(c, width=w, minwidth=min(w, 60), anchor="w")
        for tag, color in (tags or {}).items():
            tree.tag_configure(tag, foreground=color)
        if scroll:
            bar = ctk.CTkScrollbar(box, command=tree.yview, width=12, button_color=HOVER2,
                                   button_hover_color=MUTED)
            bar.pack(side="right", fill="y", padx=(0, 2), pady=2)
            tree.configure(yscrollcommand=bar.set)
        tree.pack(side="left", fill="both", expand=True, padx=1, pady=1)
        return tree

    def scroll_box(self, parent, max_h=280):
        """A list area that scrolls on its own (the page stays put). It stays hidden until fit_scroll() is called
        with content in it, and then takes only the height it needs (up to max_h)."""
        box = ctk.CTkScrollableFrame(parent, fg_color="transparent", height=max_h, corner_radius=0,
                                     scrollbar_button_color=HOVER2, scrollbar_button_hover_color=MUTED)
        box.max_h = max_h
        return box

    def fit_scroll(self, box):
        if not box.winfo_children():
            box.pack_forget()
            return
        if not box._parent_frame.winfo_ismapped():
            box.pack(fill="x", pady=(6, 0))
        def fit():
            if box.winfo_exists():
                box.update_idletasks()
                box.configure(height=max(20, min(box.max_h, box.winfo_reqheight())))
        box.after(30, fit)

    def tip(self, widget, text):
        return tip(widget, text)

    def ask(self, title, msg, warn=False):
        return messagebox.askyesno(title, msg, icon="warning" if warn else "question", default="no" if warn else "yes")

    def info(self, title, msg):
        messagebox.showinfo(title, msg)
