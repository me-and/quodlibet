# Copyright 2005 Joe Wreschnig, Michael Urman
#
# This program is free software; you can redistribute it and/or modify
# it under the terms of the GNU General Public License version 2 as
# published by the Free Software Foundation

import gobject
import gtk
import pango

from quodlibet import config
from quodlibet.qltk import get_top_parent

class TreeViewHints(gtk.Window):
    """Handle 'hints' for treeviews. This includes expansions of truncated
    columns, and in the future, tooltips."""

    # input_shape_combine_region does not work under Windows, we have
    # to pass all events to the treeview. In case it does work, this handlers
    # will never be called.
    __gsignals__ = dict.fromkeys(
        ['button-press-event', 'button-release-event',
        'motion-notify-event', 'leave-notify-event', 'scroll-event'],
        'override')

    def __init__(self):
        super(TreeViewHints, self).__init__(gtk.WINDOW_POPUP)
        self.__label = label = gtk.Label()
        label.set_alignment(0.5, 0.5)
        label.set_ellipsize(pango.ELLIPSIZE_NONE)
        self.add(label)

        self.add_events(gtk.gdk.BUTTON_MOTION_MASK |
            gtk.gdk.BUTTON_PRESS_MASK | gtk.gdk.BUTTON_RELEASE_MASK |
            gtk.gdk.KEY_PRESS_MASK | gtk.gdk.KEY_RELEASE_MASK |
            gtk.gdk.ENTER_NOTIFY_MASK | gtk.gdk.LEAVE_NOTIFY_MASK |
            gtk.gdk.SCROLL_MASK | gtk.gdk.POINTER_MOTION_MASK |
            gtk.gdk.POINTER_MOTION_HINT_MASK)

        self.set_app_paintable(True)
        self.set_resizable(False)
        self.set_name("gtk-tooltips")
        self.set_border_width(1)
        self.connect('expose-event', self.__expose)
        self.connect('leave-notify-event', self.__undisplay)

        self.__handlers = {}
        self.__current_path = self.__current_col = None
        self.__current_renderer = None
        self.__view = None

    def connect_view(self, view):
        self.__handlers[view] = [
            view.connect('motion-notify-event', self.__motion),
            view.connect('scroll-event', self.__undisplay),
            view.connect('key-press-event', self.__undisplay),
            view.connect('focus-out-event', self.__undisplay),
            view.connect('unmap', self.__undisplay),
            view.connect('destroy', self.disconnect_view),
        ]

    def disconnect_view(self, view):
        try:
            for handler in self.__handlers[view]: view.disconnect(handler)
            del self.__handlers[view]
        except KeyError: pass
        # Hide if the active treeview is going away
        if view is self.__view:
            self.__undisplay()

    def __expose(self, widget, event):
        w, h = self.get_size_request()
        self.style.paint_flat_box(self.window,
                gtk.STATE_NORMAL, gtk.SHADOW_OUT,
                None, self, "tooltip", 0, 0, w, h)

    def __motion(self, view, event):
        # trigger over row area, not column headers
        if event.window is not view.get_bin_window():
            return self.__undisplay()

        # hide if any modifier is active
        if event.state & gtk.accelerator_get_default_mod_mask():
            return self.__undisplay()

        x, y = map(int, [event.x, event.y])
        try: path, col, cellx, celly = view.get_path_at_pos(x, y)
        # no hints where no rows exist
        except TypeError: return self.__undisplay()

        # hide for partial hidden rows at the bottom
        if y > view.get_visible_rect().height:
            return self.__undisplay()

        if self.__current_path != path or self.__current_col != col:
            self.__undisplay()

        cell_offset = 0
        area = view.get_cell_area(path, col)
        renderers = col.get_cell_renderers()
        renderer = None
        if not renderers: return
        if len(renderers) == 1:
            renderer = renderers[0]
        else:
            rends = [(r.get_size(view, area), r) for r in renderers]
            rends.sort(reverse=True)
            for size, render in rends:
                if cellx >= size[0]:
                    renderer = render
                    cell_offset = size[0]
                    break

        if self.__current_renderer == renderer : return
        else: self.__undisplay()

        if not isinstance(renderer, gtk.CellRendererText): return
        if renderer.get_property('ellipsize') == pango.ELLIPSIZE_NONE: return

        model = view.get_model()
        col.cell_set_cell_data(model, model.get_iter(path), False, False)
        cellw = col.cell_get_position(renderer)[1]

        try: markup = renderer.markup
        except AttributeError:
            markup = None

        label = self.__label
        if markup is None:
            label.set_text(renderer.get_property('text'))
            w, h0 = label.get_layout().get_pixel_size()
        else:
            if isinstance(markup, int): markup = model[path][markup]
            label.set_markup(markup)
            w, h1 = label.get_layout().get_pixel_size()

        if w + 5 < cellw: return # don't display if it doesn't need expansion

        x, y, cw, h = area
        x += cell_offset
        self.__dx = x
        self.__dy = y
        y += view.get_bin_window().get_position()[1]
        ox, oy = view.window.get_origin()
        x += ox; y += oy; w += 5
        if gtk.gtk_version >= (2,8,0): w += 1 # width changed in 2.8?
        screen_width = gtk.gdk.screen_width()
        x_overflow = min([x, x + w - screen_width])
        label.set_ellipsize(pango.ELLIPSIZE_NONE)
        if x_overflow > 0:
            self.__dx -= x_overflow
            x -= x_overflow
            w = min([w, screen_width])
            label.set_ellipsize(pango.ELLIPSIZE_END)
        if not((x<=int(event.x_root) < x+w) and (y <= int(event.y_root) < y+h)):
            return # reject if cursor isn't above hint

        self.__view = view
        self.__current_renderer = renderer
        self.__edit_id = renderer.connect('editing-started', self.__undisplay)
        self.__current_path = path
        self.__current_col = col
        self.set_size_request(w, h)
        self.resize(w, h)
        self.move(x, y)
        self.show_all()

    def __undisplay(self, *args):
        if self.__current_renderer and self.__edit_id:
            self.__current_renderer.disconnect(self.__edit_id)
        self.__current_renderer = self.__edit_id = None
        self.__current_path = self.__current_col = None
        self.__view = None
        self.hide()

    def __event(self, event):
        if not self.__view:
            return True

        # hack: present the main window on key press
        if event.type == gtk.gdk.BUTTON_PRESS:
            get_top_parent(self.__view).present()

        if event.type != gtk.gdk.SCROLL:
            event.x += self.__dx
            event.y += self.__dy

        # modifying event.window is a necessary evil, made okay because
        # nobody else should tie to any TreeViewHints events ever.
        event.window = self.__view.get_bin_window()

        gtk.main_do_event(event)

        return True

    def do_button_press_event(self, event): return self.__event(event)
    def do_button_release_event(self, event): return self.__event(event)
    def do_motion_notify_event(self, event): return self.__event(event)
    def do_leave_notify_event(self, event): return self.__event(event)
    def do_scroll_event(self, event): return self.__event(event)

class BaseView(gtk.TreeView):
    def remove_paths(self, paths):
        """Remove rows and restore the selection if it got removed"""

        self.remove_iters(map(self.get_model().get_iter, paths))

    def remove_iters(self, iters):
        """Remove rows and restore the selection if it got removed"""

        self.__remove_iters(iters)

    def remove_selection(self):
        """Remove all currently selected rows and select the position
        of the first removed one."""

        selection = self.get_selection()
        mode = selection.get_mode()
        if mode in (gtk.SELECTION_SINGLE, gtk.SELECTION_BROWSE):
            model, iter_ = selection.get_selected()
            if iter_:
                self.__remove_iters([iter_], force_restore=True)
        elif mode == gtk.SELECTION_MULTIPLE:
            model, paths = selection.get_selected_rows()
            iters = map(model.get_iter, paths or [])
            self.__remove_iters(iters, force_restore=True)

    def select_by_func(self, func, scroll=True, one=False):
        """Calls func with every gtk.TreeModelRow in the model and selects
        it if func returns True. In case func never returned True,
        the selection will not be changed.

        Returns True if the selection was changed."""

        selection = self.get_selection()
        first = True
        for row in self.get_model():
            if func(row):
                if not first:
                    selection.select_path(row.path)
                    continue
                if scroll:
                    self.scroll_to_cell(row.path, use_align=True,
                                        row_align=0.5)
                self.set_cursor(row.path)
                first = False
                if one:
                    break
        return not first

    def __remove_iters(self, iters, force_restore=False):
        if not iters: return

        selection = self.get_selection()
        model = self.get_model()

        if force_restore:
             map(model.remove, iters)
        else:
            old_count = selection.count_selected_rows()
            map(model.remove, iters)
            # only restore a selection if all selected rows are gone afterwards
            if not old_count or selection.count_selected_rows():
                return

        # model.remove makes the removed iter point to the next row if possible
        # so check if the last iter is a valid one and select it or
        # simply select the last row
        if model.iter_is_valid(iters[-1]):
            selection.select_iter(iters[-1])
        elif len(model):
            selection.select_path(model[-1].path)

class MultiDragTreeView(BaseView):
    """TreeView with multirow drag support:
    * Selections don't change until button-release-event...
    * Unless they're a Shift/Ctrl modification, then they happen immediately
    * Drag icons include 3 rows/2 plus a "and more" count"""

    def __init__(self, *args):
        super(MultiDragTreeView, self).__init__(*args)
        self.connect_object(
            'button-press-event', MultiDragTreeView.__button_press, self)
        self.connect_object(
            'button-release-event', MultiDragTreeView.__button_release, self)
        self.connect_object('drag-begin', MultiDragTreeView.__begin, self)
        self.__pending_event = None

    def __button_press(self, event):
        if event.button == 1: return self.__block_selection(event)

    def __block_selection(self, event):
        x, y = map(int, [event.x, event.y])
        try: path, col, cellx, celly = self.get_path_at_pos(x, y)
        except TypeError: return True
        self.grab_focus()
        selection = self.get_selection()
        if ((selection.path_is_selected(path)
            and not (event.state & (gtk.gdk.CONTROL_MASK|gtk.gdk.SHIFT_MASK)))):
            self.__pending_event = [x, y]
            selection.set_select_function(lambda *args: False)
        elif event.type == gtk.gdk.BUTTON_PRESS:
            self.__pending_event = None
            selection.set_select_function(lambda *args: True)

    def __button_release(self, event):
        if self.__pending_event:
            selection = self.get_selection()
            selection.set_select_function(lambda *args: True)
            oldevent = self.__pending_event
            self.__pending_event = None
            if oldevent != [event.x, event.y]: return True
            x, y = map(int, [event.x, event.y])
            try: path, col, cellx, celly = self.get_path_at_pos(x, y)
            except TypeError: return True
            self.set_cursor(path, col, 0)

    def __begin(self, ctx):
        model, paths = self.get_selection().get_selected_rows()
        MAX = 3
        if paths:
            icons = map(self.create_row_drag_icon, paths[:MAX])
            height = (
                sum(map(lambda s: s.get_size()[1], icons))-2*len(icons))+2
            width = max(map(lambda s: s.get_size()[0], icons))
            final = gtk.gdk.Pixmap(icons[0], width, height)
            gc = gtk.gdk.GC(final)
            gc.copy(self.style.fg_gc[gtk.STATE_NORMAL])
            gc.set_colormap(self.window.get_colormap())
            count_y = 1
            for icon in icons:
                w, h = icon.get_size()
                final.draw_drawable(gc, icon, 1, 1, 1, count_y, w-2, h-2)
                count_y += h - 2
            if len(paths) > MAX:
                count_y -= h - 2
                bgc = gtk.gdk.GC(final)
                bgc.copy(self.style.base_gc[gtk.STATE_NORMAL])
                final.draw_rectangle(bgc, True, 1, count_y, w-2, h-2)
                more = _("and %d more...") % (len(paths) - MAX + 1)
                layout = self.create_pango_layout(more)
                attrs = pango.AttrList()
                attrs.insert(pango.AttrStyle(pango.STYLE_ITALIC, 0, len(more)))
                layout.set_attributes(attrs)
                layout.set_width(pango.SCALE * (w - 2))
                lw, lh = layout.get_pixel_size()
                final.draw_layout(gc, (w-lw)//2, count_y + (h-lh)//2, layout)

            final.draw_rectangle(gc, False, 0, 0, width-1, height-1)
            self.drag_source_set_icon(final.get_colormap(), final)
        else:
            gobject.idle_add(ctx.drag_abort, gtk.get_current_event_time())
            self.drag_source_set_icon_stock(gtk.STOCK_MISSING_IMAGE)

class RCMTreeView(BaseView):
    """Emits popup-menu when a row is right-clicked on."""

    def __init__(self, *args):
        super(RCMTreeView, self).__init__(*args)
        self.connect_object(
            'button-press-event', RCMTreeView.__button_press, self)

    def __button_press(self, event):
        if event.button == 3: return self.__check_popup(event)

    def __check_popup(self, event):
        x, y = map(int, [event.x, event.y])
        try: path, col, cellx, celly = self.get_path_at_pos(x, y)
        except TypeError: return True
        self.grab_focus()
        selection = self.get_selection()
        if not selection.path_is_selected(path):
            self.set_cursor(path, col, 0)
        else:
            col.focus_cell(col.get_cell_renderers()[0])
        self.__position_at_mouse = True
        self.emit('popup-menu')
        return True

    def ensure_popup_selection(self):
        try:
            self.__position_at_mouse
        except AttributeError:
            path, col = self.get_cursor()
            if path is None:
                return False
            self.scroll_to_cell(path, col)
            # ensure current cursor path is selected, just like right-click
            selection = self.get_selection()
            if not selection.path_is_selected(path):
                selection.unselect_all()
                selection.select_path(path)
            return True

    def popup_menu(self, menu, button, time):
        try:
            del self.__position_at_mouse
        except AttributeError:
            # suppress menu if the cursor isn't on a real path
            if not self.ensure_popup_selection():
                return False
            pos_func = self.__popup_position
        else:
            pos_func = None

        menu.popup(None, None, pos_func, button, time)
        return True

    def __popup_position(self, menu):
        path, col = self.get_cursor()
        if col is None:
            col = self.get_column(0)

        # get a rectangle describing the cell render area (assume 3 px pad)
        rect = self.get_cell_area(path, col)
        rect.x += 3
        rect.width -= 6
        rect.y += 3
        rect.height -= 6
        dx, dy = self.window.get_origin()
        dy += self.get_bin_window().get_position()[1]

        # fit menu to screen, aligned per text direction
        screen_width = gtk.gdk.screen_width()
        screen_height = gtk.gdk.screen_height()
        menu.realize()
        ma = menu.allocation
        menu_y = rect.y + rect.height + dy
        if menu_y + ma.height > screen_height and rect.y + dy - ma.height > 0:
            menu_y = rect.y + dy - ma.height
        if gtk.widget_get_default_direction() == gtk.TEXT_DIR_LTR:
            menu_x = min(rect.x + dx, screen_width - ma.width)
        else:
            menu_x = max(0, rect.x + dx - ma.width + rect.width)

        return (menu_x, menu_y, True) # x, y, move_within_screen

class HintedTreeView(BaseView):
    """A TreeView that pops up a tooltip when you hover over a cell that
    contains ellipsized text."""

    def __init__(self, *args):
        super(HintedTreeView, self).__init__(*args)
        if not config.state('disable_hints'):
            try: tvh = HintedTreeView.hints
            except AttributeError: tvh = HintedTreeView.hints = TreeViewHints()
            tvh.connect_view(self)

class TreeViewColumnButton(gtk.TreeViewColumn):
    """A TreeViewColumn that forwards its header events:
        button-press-event and popup-menu"""

    __gsignals__ = {
        'button-press-event': (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE,
                (object,)),
        'popup-menu':  (gobject.SIGNAL_RUN_LAST, gobject.TYPE_NONE, ()),
    }

    def __init__(self, title="", *args, **kw):
        super(TreeViewColumnButton, self).__init__(title, *args, **kw)
        label = gtk.Label(title)
        self.set_widget(label)
        label.show()
        label.__realize = label.connect('realize', self.__connect_menu_event)

    def __connect_menu_event(self, widget):
        widget.disconnect(widget.__realize)
        del widget.__realize
        button = widget.get_ancestor(gtk.Button)
        if button:
            button.connect('button-press-event', self.button_press_event)
            button.connect('popup-menu', self.popup_menu)

    def button_press_event(self, widget, event):
        self.emit('button-press-event', event)

    def popup_menu(self, widget):
        self.emit('popup-menu')
        return True

class RCMHintedTreeView(HintedTreeView, RCMTreeView):
    """A TreeView that has hints and a context menu."""
    pass

class AllTreeView(HintedTreeView, RCMTreeView, MultiDragTreeView):
    """A TreeView that has hints, a context menu, and multi-selection
    dragging support."""
    pass
