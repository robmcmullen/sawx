# Standard library imports.
import sys
import os
import functools

# Major package imports.
import wx
import numpy as np

# Enthought library imports.
from traits.api import on_trait_change, Any, Bool, Int, Str, List, Event, Enum, Instance, File, Unicode, Property, provides, Undefined, CArray

# Local imports.
from omnivore.utils.command import Overlay
from omnivore8bit.utils.drawutil import get_bounds
from ..byte_edit.commands import ChangeByteCommand
from ..clipboard_commands import PasteCommand, PasteRectCommand
from omnivore.framework.mouse_mode import MouseMode

from .map_commands import *

import logging
log = logging.getLogger(__name__)


class NormalSelectMode(MouseMode):
    def init_post_hook(self):
        self.last_mouse_event = -1, -1
        self.event_modifiers = None

    def process_mouse_motion_up(self, evt):
        log.debug("NormalSelectMode: process_mouse_motion_up")
        cg = self.control
        input_row, input_cell = cg.main.get_row_cell_from_event(evt)
        if (input_row, input_cell) == self.last_mouse_event:
            # only process if mouse has moved to a new cell; no sub-cell
            # events!
            return
        col = cg.main.cell_to_col(input_cell)
        cg.handle_motion_update_status(evt, input_row, col)
        self.last_mouse_event = (input_row, input_cell)

    def process_left_down(self, evt):
        log.debug("NormalSelectMode: process_left_down")
        cg = self.control
        flags = cg.create_mouse_event_flags()
        input_row, input_cell = cg.main.get_row_cell_from_event(evt)
        self.event_modifiers = evt.GetModifiers()
        cg.main.process_motion_scroll(input_row, input_cell, flags)
        self.last_mouse_event = (input_row, input_cell)
        cg.handle_select_start(evt, cg.main.current_caret_row, cg.main.current_caret_col, flags)

    def process_mouse_motion_down(self, evt):
        log.debug("NormalSelectMode: process_mouse_motion_down")
        cg = self.control
        input_row, input_cell = cg.main.get_row_cell_from_event(evt)
        if (input_row, input_cell) == self.last_mouse_event:
            # only process if mouse has moved to a new cell; no sub-cell
            # events!
            return
        flags = cg.create_mouse_event_flags()
        last_row, last_col = cg.main.current_caret_row, cg.main.current_caret_col
        cg.main.handle_user_caret(input_row, input_cell, flags)
        if last_row != cg.main.current_caret_row or last_col != cg.main.current_caret_col:
            cg.handle_select_motion(evt, cg.main.current_caret_row, cg.main.current_caret_col, flags)
        self.last_mouse_event = (input_row, input_cell)

    def process_left_up(self, evt):
        log.debug("NormalSelectMode: process_left_up")
        cg = self.control
        cg.main.scroll_timer.Stop()
        self.event_modifiers = None
        cg.handle_select_end(evt, cg.main.current_caret_row, cg.main.current_caret_col)

    def process_left_dclick(self, evt):
        log.debug("NormalSelectMode: process_left_dclick")
        evt.Skip()

    def calc_popup_data(self, evt):
        c = self.control
        row, col = c.get_row_col_from_event(evt)
        index, _ = c.table.get_index_range(row, col)
        inside = True  # fixme
        style = c.table.segment.style[index] if inside else 0
        popup_data = {
            'index': index,
            'in_selection': style&0x80,
            'row': row,
            'col': col,
            'inside': inside,
            }
        return popup_data

    def calc_popup_actions(self, evt, popup_data):
        actions = self.calc_mode_popup_actions(popup_data)
        if not actions:
            actions = self.control.calc_popup_actions(popup_data)
        if actions:
            self.segment_viewer.popup_context_menu_from_actions(actions, popup_data)

    def calc_mode_popup_actions(self, popup_data):
        return []

    def show_popup(self, actions):
        self.control.viewer.popup_context_menu_from_actions(actions)

    def zoom_in(self, evt, amount):
        self.control.zoom_in()

    def zoom_out(self, evt, amount):
        self.control.zoom_out()


class RectangularSelectMode(NormalSelectMode):
    icon = "select.png"
    menu_item_name = "Select"
    menu_item_tooltip = "Select rectangular regions"

    def display_coords(self, evt, extra=None):
        log.debug("display_coords")
        c = self.control
        e = c.editor
        if e is not None:
            index, bit, inside = c.event_coords_to_byte(evt)
            r0, c0 = c.index_to_row_col(index)
            msg = "x=$%x y=$%x index=$%x" % (c0, r0, index)
            if extra:
                msg += " " + extra
            e.show_status_message(msg)


class EyedropperMode(RectangularSelectMode):
    icon = "eyedropper.png"
    menu_item_name = "Pick Item"
    menu_item_tooltip = "Pick an item from the grid and use as the current draw item"

    def process_left_down(self, evt):
        log.debug("EyedropperMode: process_left_down")
        cg = self.control
        input_row, input_cell = cg.main.get_row_cell_from_event(evt)
        if (input_row, input_cell) == self.last_mouse_event:
            # only process if mouse has moved to a new cell; no sub-cell
            # events!
            return
        self.last_mouse_event = (input_row, input_cell)
        row, col = cg.get_row_col_from_event(evt)
        index, _ = cg.table.get_index_range(row, col)
        value = cg.segment_viewer.segment[index]
        cg.segment_viewer.set_draw_pattern(value)
        log.debug("draw_pattern=%x at index=%d %d,%d" % (value, index, row, col))
        # self.display_coords(evt, "tile=%d" % value)

    def process_mouse_motion_down(self, evt):
        self.process_left_down(evt)

    def process_left_up(self, evt):
        self.last_mouse_event = None, None


class DrawMode(RectangularSelectMode):
    icon = "shape_freehand.png"
    menu_item_name = "Draw"
    menu_item_tooltip = "Draw with current tile"

    def draw(self, evt, start=False):
        c = self.control
        v = c.segment_viewer
        pattern = c.segment_viewer.draw_pattern
        if start:
            self.batch = DrawBatchCommand()
        byte, bit, inside = c.event_coords_to_byte(evt)
        if inside:
            v.linked_base.set_caret(byte, False)
            index = v.linked_base.caret_index
            cmd = ChangeByteCommand(e.segment, index, index+len(pattern), pattern, False, True)
            v.editor.process_command(cmd, self.batch)

    def process_left_down(self, evt):
        self.draw(evt, True)
        self.display_coords(evt)

    def process_mouse_motion_down(self, evt):
        self.draw(evt)
        self.display_coords(evt)

    def process_left_up(self, evt):
        c = self.control
        v = c.segment_viewer
        v.editor.end_batch()
        self.batch = None


class OverlayMode(RectangularSelectMode):
    command = None

    def get_display_rect(self, index):
        c = self.control
        i1 = self.start_index
        i2 = index
        if i2 < i1:
            i1, i2 = i2, i1
        (x1, y1), (x2, y2) = get_bounds(i1, i2, c.bytes_per_row)
        extra = None
        w = x2 - x1 + 1
        h = y2 - y1 + 1
        if w > 0 or h > 0:
            extra = "rectangle: $%x x $%x" % (w, h)
        return extra

    def draw(self, evt, start=False):
        c = self.control
        v = c.segment_viewer
        pattern = v.draw_pattern
        byte, bit, inside = c.event_coords_to_byte(evt)
        if inside:
            if start:
                self.batch = Overlay()
                self.start_index = byte
            v.linked_base.set_caret(byte, False)
            index = byte
            cmd = self.command(v.segment, self.start_index, index, pattern, c.bytes_per_row)
            v.editor.process_command(cmd, self.batch)
            self.display_coords(evt, self.get_display_rect(index))

    def process_left_down(self, evt):
        self.draw(evt, True)

    def process_mouse_motion_down(self, evt):
        self.draw(evt)

    def process_left_up(self, evt):
        c = self.control
        v = c.segment_viewer
        v.editor.end_batch()
        self.batch = None


class LineMode(OverlayMode):
    icon = "shape_line.png"
    menu_item_name = "Line"
    menu_item_tooltip = "Draw line with current tile"
    command = LineCommand


class SquareMode(OverlayMode):
    icon = "shape_hollow_square.png"
    menu_item_name = "Square"
    menu_item_tooltip = "Draw square with current tile"
    command = SquareCommand


class FilledSquareMode(OverlayMode):
    icon = "shape_filled_square.png"
    menu_item_name = "Filled Square"
    menu_item_tooltip = "Draw filled square with current tile"
    command = FilledSquareCommand
