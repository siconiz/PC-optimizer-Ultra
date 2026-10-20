"""A picture of the user's choice behind the whole window: open areas show it, and cards and the sidebar show it
frosted (mixed with the card color) so text stays readable.

Tk widgets cannot be see-through, so every surface gets its own copy of the picture, shifted so that together they
look like one picture fixed behind the window: customtkinter widgets draw themselves on a canvas (the picture goes
into that canvas), plain frames get a picture label, and text labels show the matching piece behind their text."""
import os, tkinter
from . import theme

STRENGTH = 0.35   # default: 35% picture in open areas
GLASS = 0.5       # cards and the sidebar show the picture at half that strength
BLUR = 6          # softens the picture so small details do not fight with the text

def cfg(app):
    return app.cfg.setdefault("background", {"path": "", "strength": STRENGTH})

def downloads():
    p = os.path.join(os.path.expanduser("~"), "Downloads")
    return p if os.path.isdir(p) else os.path.expanduser("~")

class Background:
    def __init__(self, app):
        self.app, self.src = app, None
        self.img, self.photo = {}, {}       # kind ('open' / 'glass') -> PIL image / PhotoImage of the whole window
        self.layers, self.items, self.texts, self.cards, self.fills = {}, {}, {}, {}, {}
        app.bind("<Configure>", lambda e: self._later(self._build, 250) if e.widget is app else None, add="+")
        self._tick()

    # ---------- settings ----------
    def set(self, path, strength=None):
        c = cfg(self.app)
        c["path"] = path or ""
        if strength is not None:
            c["strength"] = strength
        self.app.save()
        self.src = None
        self._build()
        from core.i18n import t
        for lbl in getattr(self.app, "_bg_names", []):
            if lbl.winfo_exists():
                lbl.configure(text=os.path.basename(c["path"]) or t("None"))

    def _later(self, fn, ms=30):
        key = fn.__name__
        jobs = self.__dict__.setdefault("jobs", {})
        if jobs.get(key):
            self.app.after_cancel(jobs[key])
        jobs[key] = self.app.after(ms, lambda: (jobs.pop(key, None), fn()))

    def _tick(self):
        """Widgets added later (lists, results) get the picture too: look at the visible page every second."""
        if self.photo and not self.app.moving():
            page = getattr(self.app, "pages", {}).get(getattr(self.app, "current", None))
            if page is not None:
                self.paint(page, quiet=True)
        self.app.after(1000, self._tick)

    # ---------- the picture ----------
    def _build(self):
        """Scale the picture to cover the window, blur it, and make the open and the frosted version."""
        c = cfg(self.app)
        if not c["path"] or not os.path.isfile(c["path"]):
            return self.clear()
        from PIL import Image, ImageFilter, ImageTk
        w, h = self.app.winfo_width(), self.app.winfo_height()
        if w < 100 or h < 100:  # the window is not laid out yet
            return self._later(self._build, 300)
        if self.src is None:
            try:
                self.src = Image.open(c["path"]).convert("RGB")
            except Exception:
                return self.clear()
        sw, sh = self.src.size
        k = max(w / sw, h / sh)
        img = self.src.resize((max(w, int(sw * k)), max(h, int(sh * k))), Image.LANCZOS)
        left, top = (img.width - w) // 2, (img.height - h) // 2
        img = img.crop((left, top, left + w, top + h)).filter(ImageFilter.GaussianBlur(BLUR))
        s = float(c.get("strength", STRENGTH))
        self.img = {"open": Image.blend(Image.new("RGB", (w, h), theme.BG), img, s),
                    "glass": Image.blend(Image.new("RGB", (w, h), theme.CARD), img, s * GLASS)}
        self.photo = {k: ImageTk.PhotoImage(v) for k, v in self.img.items()}
        for frame, (lbl, kind) in self.layers.items():
            if lbl.winfo_exists():
                lbl.configure(image=self.photo[kind])
        for cv, (item, top, kind) in self.items.items():
            if cv.winfo_exists():
                cv.itemconfigure(item, image=self.photo[kind])
        self.texts = {w: (inner, kind, None) for w, (inner, kind, _) in self.texts.items()}
        self.cards = {w: (item, None) for w, (item, _) in self.cards.items()}
        self.fills = {w: (kind, None) for w, (kind, _) in self.fills.items()}
        self.paint(self.app)

    def clear(self):
        for lbl, _ in self.layers.values():
            if lbl.winfo_exists():
                lbl.destroy()
        for cv, (item, _, _) in self.items.items():
            if cv.winfo_exists():
                cv.delete(item)
        for card, (item, _) in self.cards.items():
            if card.winfo_exists():
                card._canvas.delete(item)
        for inner, _, _ in self.texts.values():
            if inner.winfo_exists():
                inner.configure(bg=inner._bg_orig) if inner._bg_plain else inner.configure(image="")
        self.layers, self.items, self.texts, self.cards, self.img, self.photo = {}, {}, {}, {}, {}, {}
        self.fills = {}

    # ---------- finding the surfaces ----------
    def _kind_of(self, w):
        while w is not None:
            if self._is_card(w):
                return "glass"
            w = getattr(w, "master", None)
        return "open"

    @staticmethod
    def _is_card(w):
        import customtkinter as ctk
        return type(w) is ctk.CTkFrame and w.cget("fg_color") in (theme.CARD, theme.SIDE)

    def paint(self, root, quiet=False):
        """Give every surface under root its piece of the picture."""
        if not self.photo:
            return
        import customtkinter as ctk
        from customtkinter.windows.widgets.core_widget_classes import CTkBaseClass
        mine = {lbl for lbl, _ in self.layers.values()}
        new = []
        def walk(w, kind):
            if w in mine:
                return
            if isinstance(w, ctk.CTkScrollableFrame):  # a page or list that scrolls: the picture follows scrolling
                self._layer(w, kind)
                self._canvas(w._parent_canvas, True, kind)
                self._canvas(w._parent_frame._canvas, True, kind)
                if not getattr(w, "_bg_hooked", False):
                    w._bg_hooked = True
                    bar = w._scrollbar
                    w._parent_canvas.configure(yscrollcommand=lambda a, b: (bar.set(a, b), self._later(self.place, 1)))
            elif isinstance(w, ctk.CTkFrame):
                fg = w.cget("fg_color")
                if self._is_card(w):  # card / sidebar: frosted picture inside the rounded shape
                    self._canvas(w._canvas, False, kind)
                    if w not in self.cards:
                        self.cards[w] = (None, None)
                        new.append(w)
                    kind = "glass"
                elif fg in ("transparent", theme.BG) or w is self.app.content:
                    self._canvas(w._canvas, True, kind)  # over the frame's own fill; children are windows above
                else:  # tiles, tables and segmented buttons stay solid; only their corners
                    self._canvas(w._canvas, False, kind)
                    return
            elif isinstance(w, ctk.CTkLabel):
                clear = w.cget("fg_color") == "transparent"
                self._canvas(w._canvas, clear, kind)  # a transparent label fills its canvas with the parent color
                if clear and not w.cget("image"):
                    self._text(w._label, kind)
                return
            elif isinstance(w, tkinter.Label):
                if not w.cget("image"):
                    self._text(w, kind, plain=True)
                return
            elif isinstance(w, tkinter.Tk):
                self._layer(w, kind)
            elif isinstance(w, tkinter.Toplevel):
                return  # overlay boxes, tooltips and dialogs keep their own look
            elif isinstance(w, tkinter.Canvas):
                if not any(isinstance(c, ctk.CTkScrollableFrame) for c in w.winfo_children()):
                    return  # graphs and other drawings are left alone
                self._canvas(w, True, kind)  # the scrolling canvas of a page
            elif isinstance(w, tkinter.Frame) and not isinstance(w, CTkBaseClass):
                self._layer(w, kind)
            else:
                if isinstance(w, CTkBaseClass):  # the widget's own frame shows around its canvas: match its color
                    self.fills.setdefault(w, (kind, None))
                if hasattr(w, "_canvas"):  # buttons, switches, entries, menus: picture under their rounded corners
                    try:
                        clear = isinstance(w, ctk.CTkButton) and w.cget("fg_color") == "transparent"
                    except Exception:
                        clear = False
                    self._canvas(w._canvas, clear, kind)  # a transparent button: picture over its plain fill
                    if isinstance(w, ctk.CTkButton) and not getattr(w, "_bg_button", False):
                        w._bg_button = True  # its fill changes on hover and selection: follow it
                        cv = w._canvas
                        cv._bg_owner, cv._bg_hover = w, False
                        def hover(on, cv=cv):
                            cv._bg_hover = on
                            self._restack(cv)
                            if not on:  # ctk paints the label with the plain color again after hover: recolor it
                                self._later(self.place, 20)
                        for part in (w._canvas, w._text_label):
                            if part is not None:
                                tkinter.Misc.bind(part, "<Enter>", lambda e, h=hover: h(True), "+")
                                tkinter.Misc.bind(part, "<Leave>", lambda e, h=hover: h(False), "+")
                    if isinstance(w, ctk.CTkButton) and getattr(w, "_text_label", None) is not None:
                        self._text(w._text_label, kind, plain=True)  # colored only while the button is transparent
                return
            for child in w.winfo_children():
                walk(child, kind)
        walk(root, self._kind_of(root))
        if new or not quiet:
            self.app.after_idle(self.place)
            self.app.after(400, self.place)  # again once the new widgets have their final size

    def _layer(self, frame, kind):
        """Plain Tk frame (the window, the inside of a scrolling page): a label with the picture under its children."""
        if frame in self.layers and self.layers[frame][0].winfo_exists():
            return
        lbl = tkinter.Label(frame, image=self.photo[kind], bd=0, highlightthickness=0)
        lbl.place(x=0, y=0)
        lbl.lower()
        self.layers[frame] = (lbl, kind)
        frame.bind("<Configure>", lambda e: self._later(self.place, 60), add="+")  # content grew or shrank

    def _canvas(self, cv, top, kind):
        if cv not in self.items:
            self.items[cv] = (cv.create_image(0, 0, image=self.photo[kind], anchor="nw"), top, kind)
        item, top, _ = self.items[cv]
        (cv.tag_raise if top else cv.tag_lower)(item)

    def _restack(self, cv):
        """Picture over the shapes (open areas, transparent buttons) or under them (corners only). A transparent
        button that is hovered or selected shows its own fill again."""
        if cv not in self.items or not cv.winfo_exists():
            return
        item, top, kind = self.items[cv]
        owner = getattr(cv, "_bg_owner", None)
        if owner is not None:
            top = owner.cget("fg_color") == "transparent" and not self._hovered(owner, cv)
        (cv.tag_raise if top else cv.tag_lower)(item)
        lbl = getattr(owner, "_text_label", None) if owner is not None else None
        if lbl is not None and lbl in self.texts:
            self.texts[lbl] = (lbl, kind, None)  # customtkinter recolors it on every redraw: color it again

    def _hovered(self, owner, cv):
        """Is the pointer on this button right now? (Enter / Leave can be missed, so check the real position.)"""
        if not cv._bg_hover:
            return False
        try:
            w = self.app.winfo_containing(*self.app.winfo_pointerxy())
        except (KeyError, tkinter.TclError):
            w = None
        while w is not None and w is not owner:
            w = getattr(w, "master", None)
        cv._bg_hover = w is owner
        return cv._bg_hover

    def _text(self, inner, kind, plain=False):
        """Text labels: customtkinter's label shows the matching piece of the picture behind its text; plain Tk labels
        (sized in characters, where a picture would change their size) take the average color of that piece."""
        if inner not in self.texts:
            inner._bg_plain = plain
            if plain:
                inner._bg_orig = inner.cget("bg")
            self.texts[inner] = (inner, kind, None)

    def _mask(self, w, h, r):
        """Rounded-rectangle alpha mask like the card's shape (corners drawn 3x larger for smooth edges)."""
        from PIL import Image, ImageDraw
        masks = self.__dict__.setdefault("masks", {})
        if (w, h, r) not in masks:
            m = Image.new("L", (w, h), 255)
            c = Image.new("L", (r * 3, r * 3), 0)
            ImageDraw.Draw(c).pieslice((0, 0, r * 6, r * 6), 180, 270, fill=255)
            c = c.resize((r, r), Image.BILINEAR)
            for img, xy in ((c, (0, 0)), (c.transpose(Image.FLIP_LEFT_RIGHT), (w - r, 0)),
                            (c.transpose(Image.FLIP_TOP_BOTTOM), (0, h - r)), (c.transpose(Image.ROTATE_180), (w - r, h - r))):
                m.paste(img, xy)
            if len(masks) > 200:
                masks.clear()
            masks[(w, h, r)] = m
        return masks[(w, h, r)]

    # ---------- keeping the pieces in place ----------
    def place(self):
        """Shift each copy so the picture stays put behind the window (after scrolling and resizing)."""
        if not self.photo:
            return
        from PIL import Image, ImageDraw, ImageTk
        ox, oy = self.app.winfo_rootx(), self.app.winfo_rooty()
        H = self.app.winfo_height()
        for frame, (lbl, kind) in list(self.layers.items()):
            if not frame.winfo_exists() or not lbl.winfo_exists():
                del self.layers[frame]
                continue
            lbl.place(x=ox - frame.winfo_rootx(), y=oy - frame.winfo_rooty())
        for cv, (item, top, kind) in list(self.items.items()):
            if not cv.winfo_exists():
                del self.items[cv]
                continue
            cv.coords(item, cv.canvasx(ox - cv.winfo_rootx()), cv.canvasy(oy - cv.winfo_rooty()))
            self._restack(cv)  # customtkinter may restack its shapes on redraw
        for card, (item, last) in list(self.cards.items()):
            if not card.winfo_exists():
                del self.cards[card]
                continue
            x, y, w, h = card.winfo_rootx() - ox, card.winfo_rooty() - oy, card.winfo_width(), card.winfo_height()
            cv = card._canvas
            if w > 2 and h > 2 and y + h > 0 and y < H and (x, y, w, h) != last:
                r = int(card.cget("corner_radius") * card._get_widget_scaling())
                piece = self.img["glass"].crop((x, y, x + w, y + h)).convert("RGBA")
                if r:
                    piece.putalpha(self._mask(w, h, r))
                card._bg_photo = ImageTk.PhotoImage(piece)
                if item is None:
                    item = cv.create_image(0, 0, image=card._bg_photo, anchor="nw")
                else:
                    cv.itemconfigure(item, image=card._bg_photo)
                self.cards[card] = (item, (x, y, w, h))
            if item is not None:
                cv.tag_raise(item)
                cv.tag_raise("border_parts")  # the accent border in widget edit mode stays visible
        def avg(kind, x, y, w, h):
            r, g, b = self.img[kind].crop((x, y, x + max(1, w), y + max(1, h))).resize((1, 1), Image.BOX).getpixel((0, 0))
            return "#%02x%02x%02x" % (r, g, b)
        for wdg, (kind, last) in list(self.fills.items()):
            if not wdg.winfo_exists():
                del self.fills[wdg]
                continue
            x, y, w, h = wdg.winfo_rootx() - ox, wdg.winfo_rooty() - oy, wdg.winfo_width(), wdg.winfo_height()
            if (x, y, w, h) != last and y + h > 0 and y < H:
                tkinter.Frame.configure(wdg, bg=avg(kind, x, y, w, h))
                self.fills[wdg] = (kind, (x, y, w, h))
        for inner, (_, kind, last) in list(self.texts.items()):
            if not inner.winfo_exists():
                del self.texts[inner]
                continue
            owner = getattr(inner.master, "_canvas", None)
            if owner is not None and getattr(owner, "_bg_owner", None) is not None and (
                    self._hovered(owner._bg_owner, owner) or owner._bg_owner.cget("fg_color") != "transparent"):
                self.texts[inner] = (inner, kind, None)
                continue  # hovered / selected button: customtkinter colors its label
            x, y = inner.winfo_rootx() - ox, inner.winfo_rooty() - oy
            w, h = inner.winfo_width(), inner.winfo_height()
            if (x, y, w, h) == last or y + h < 0 or y > H:  # unchanged or off screen
                continue
            self.texts[inner] = (inner, kind, (x, y, w, h))
            piece = self.img[kind].crop((x, y, x + max(1, w), y + max(1, h)))
            if inner._bg_plain or w < 3:
                r, g, b = piece.resize((1, 1), Image.BOX).getpixel((0, 0))
                inner.configure(bg="#%02x%02x%02x" % (r, g, b))
            else:
                inner._bg_photo = ImageTk.PhotoImage(piece)
                inner.configure(image=inner._bg_photo, compound="center")
