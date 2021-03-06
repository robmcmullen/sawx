""" Simple menubar & tabbed window framework
"""
import wx

from sawx import SawxApp, SawxEditor, SawxAction, SawxActionRadioMixin, errors
from sawx.editor import find_editor_class_by_name

import logging
logging.basicConfig(level=logging.WARNING)


class paste_as_text(SawxAction):
    def calc_name(self, action_key):
        return "Paste As Text"

class document_list(SawxAction):
    def calc_name(self, action_key):
        return action_key.replace("_", " ").title()

    def calc_menu_sub_keys(self, action_key):
        return ["document_list1", "document_list2", "document_list3"]

class text_counting(SawxAction):
    def init_from_editor(self):
        self.counts = list(range(5, 25, 5))

    def calc_name(self, action_key):
        return action_key.replace("_", " ").title()

    def calc_menu_sub_keys(self, action_key):
        self.count_map = {f"text_count_{c}":c for c in self.counts}
        return [f"text_count_{c}" for c in self.counts]

    def sync_menu_item_from_editor(self, action_key, menu_item):
        count = self.editor.control.GetLastPosition()
        menu_item.Enable(count >= self.count_map[action_key])

class text_last_digit(SawxActionRadioMixin, SawxAction):
    def calc_name(self, action_key):
        return action_key.replace("_", " ").title()

    def calc_menu_sub_keys(self, action_key):
        self.count_map = {f"text_last_digit_{c}":c for c in range(10)}
        return [f"text_last_digit_{c}" for c in range(10)]

    def sync_menu_item_from_editor(self, action_key, menu_item):
        count = self.editor.control.GetLastPosition()
        divisor = self.count_map[action_key]
        menu_item.Check(count % 10 == divisor)

    calc_tool_sub_keys = calc_menu_sub_keys

    def sync_tool_item_from_editor(self, action_key, toolbar_control, id):
        count = self.editor.control.GetLastPosition()
        divisor = self.count_map[action_key]
        toolbar_control.ToggleTool(id, count % 10 == divisor)

class text_last_digit_dyn(SawxAction):
    def init_from_editor(self):
        self.count = (self.editor.control.GetLastPosition() % 10) + 1

    def calc_name(self, action_key):
        return action_key.replace("_", " ").title()

    def calc_menu_sub_keys(self, action_key):
        self.count_map = {f"text_last_digit_dyn{c}":c for c in range(self.count)}
        return [f"text_last_digit_dyn{c}" for c in range(self.count)]

    def sync_menu_item_from_editor(self, action_key, menu_item):
        count = (self.editor.control.GetLastPosition() % 10) + 1
        if count != self.count:
            raise errors.RecreateDynamicMenuBar

class text_size(SawxAction):
    def init_from_editor(self):
        self.counts = list(range(5, 25, 5))

    def calc_name(self, action_key):
        size = self.editor.control.GetLastPosition()
        return f"Text Size: {size}"

    def sync_menu_item_from_editor(self, action_key, menu_item):
        name = self.calc_name(action_key)
        menu_item.SetItemLabel(name)

class DemoEditor(SawxEditor):
    name = "demo_editor"

    menubar_desc = [
    ["File", ["New", "new_file"], "open_file", None, "save_file", "save_as", None, "quit"],
    ["Edit", "undo", "redo", None, "copy", "cut", "paste", "paste_rectangular", ["Paste Special", "paste_as_text", "paste_as_hex"], None, "prefs"],
    ["Text", None, None, None, "text_counting", None, None, None, "text_last_digit", None, "text_size"],
    ["Dynamic", "text_last_digit_dyn"],
    ["Document", "document_list"],
    ["Help", "about"],
    ]

    toolbar_desc = [
    "new_file", "open_file", "save_file", None, "undo", "redo", None, "copy", "cut", "paste", "paste_as_text", "paste_as_hex",
    ]

    @property
    def is_dirty(self):
        return not self.control.IsEmpty()

    @property
    def can_copy(self):
        return self.control.CanCopy()

    @property
    def can_paste(self):
        return self.control.CanPaste()

    @property
    def can_undo(self):
        return False

    @property
    def can_redo(self):
        return False

    def create_control(self, parent):
        return wx.TextCtrl(parent, -1, style=wx.TE_MULTILINE)


if __name__ == "__main__":
    import sys
    import sawx.editor
    app = SawxApp(False)
    frame = app.new_frame()

    action_factory_lookup = {
         "text_counting": text_counting,
         "text_last_digit": text_last_digit,
         "text_last_digit_dyn": text_last_digit_dyn,
         "text_size": text_size,
    }
    args = sys.argv[1:]
    while len(args) > 0:
        path = args.pop(0)

        if path == "demo":
            editor1 = DemoEditor()
            editor2 = DemoEditor(action_factory_lookup=action_factory_lookup)
            editor2.toolbar_desc = [
            "new_file", "open_file", "save_file", None, "text_last_digit",
            ]
            editor2.tab_name = "Editor 2"
            editor3 = DemoEditor(action_factory_lookup=action_factory_lookup)
            editor3.tab_name = "Editor 3"
            frame.add_editor(editor1)
            frame.add_editor(editor2)
            frame.add_editor(editor3)
        elif path == "text":
            editor_cls = find_editor_class_by_name("text_editor")
            if editor_cls:
                e = editor_cls(action_factory_lookup=action_factory_lookup)
                e.toolbar_desc = ["text_last_digit"]
                frame.add_editor(e)
        elif path == "debug":
            editor_cls = find_editor_class_by_name("debug")
            if editor_cls:
                e = editor_cls()
                frame.add_editor(e)
        else:
            frame.load_file(path)
    frame.Show()

    app.MainLoop()
