import os
import sys
import pickle

import numpy as np
import wx
import wx.lib.filebrowsebutton as filebrowse
from wx.lib.expando import ExpandoTextCtrl, EVT_ETC_LAYOUT_NEEDED

from omnivore.utils.processutil import which
from omnivore.utils.textutil import text_to_int
from omnivore.utils.wx.dropscroller import ReorderableList, PickledDropTarget, PickledDataObject
from omnivore.utils.wx.dialogs import DictEditDialog


class EmulatorDialog(DictEditDialog):
    border = 5
    
    def __init__(self, parent, title, default=None):
        fields = [
            ('file', 'exe', 'Executable: '),
            ('text', 'args', 'Args: '),
            ('static spacer below', None, "(use %s as placeholder for the data file or it will be added at the end)"),
            ('text', 'name', 'Display Name: '),
            ]
        self.user_changed = False
        DictEditDialog.__init__(self, parent, title, "Enter emulator information:", fields, default)

    def on_text_changed(self, evt):
        if evt.GetEventObject() == self.controls['name']:
            self.user_changed = True
        elif not self.user_changed:
            self.set_automatic_name()
    
    def set_automatic_name(self):
        name = os.path.basename(self.controls['exe'].GetValue())
        args = self.controls['args'].GetValue()
        if args:
            name += " " + args
        self.controls['name'].ChangeValue(name)

    def on_path_changed(self, evt):
        if not self.user_changed:
            self.set_automatic_name()
        self.ok_btn.Enable(self.can_submit())
        
    def can_submit(self):
        path = self.controls['exe'].GetValue()
        return bool(which(path))

def prompt_for_emulator(parent, title, default_emu=None):
    d = EmulatorDialog(parent, title, default_emu)
    return d.show_and_get_value()


class AssemblerDialog(DictEditDialog):
    border = 5
    
    def __init__(self, parent, title, default=None):
        fields = [
            ('text', 'name', 'Name: '),
            ('text', 'origin', 'Origin Directive: '),
            ('text', 'data byte', 'Data Byte Directive: '),
            ('text', 'comment char', 'Comment Char: '),
            ]
        DictEditDialog.__init__(self, parent, title, "Enter assembler information:", fields, default)
    
    def can_submit(self):
        control = self.controls['name']
        return len(control.GetValue()) > 0

def prompt_for_assembler(parent, title, default=None):
    d = AssemblerDialog(parent, title, default)
    return d.show_and_get_value()


def get_file_dialog_wildcard(name, extension_list):
    # Using only the first extension
    wildcards = []
    if extension_list:
        ext = extension_list[0]
        wildcards.append("%s (*%s)|*%s" % (name, ext, ext))
    return "|".join(wildcards)


class SegmentOrderDialog(wx.Dialog):
    border = 5
    instructions = "Drag segments to the right-hand list to create the output segment order"
    dest_list_title = "Segments in Executable"
    
    def __init__(self, parent, title, segments, list_title=None, credits=False):
        wx.Dialog.__init__(self, parent, -1, title, style=wx.DEFAULT_DIALOG_STYLE|wx.RESIZE_BORDER)
        
        self.segment_map = {k:v for k,v in enumerate(segments)}
        
        sizer = wx.BoxSizer(wx.VERTICAL)
        self.SetSizer(sizer)
        
        t = wx.StaticText(self, -1, self.instructions)
        sizer.Add(t, 0, wx.ALL|wx.EXPAND, self.border)
        
        hbox = wx.BoxSizer(wx.HORIZONTAL)
        
        vbox1 = wx.BoxSizer(wx.VERTICAL)
        t = wx.StaticText(self, -1, "All Segments")
        vbox1.Add(t, 0, wx.ALL|wx.EXPAND, self.border)
        self.source = ReorderableList(self, self.segment_map.keys(), self.get_item_text, columns=["Origin", "Size", "Name"], resize_column=3, allow_drop=False, size=(400,300))
        vbox1.Add(self.source, 1, wx.ALL|wx.EXPAND, self.border)
        hbox.Add(vbox1, 1, wx.ALL|wx.EXPAND, 0)

        vbox2 = wx.BoxSizer(wx.VERTICAL)
        if list_title is None:
            list_title = self.dest_list_title
        t = wx.StaticText(self, -1, list_title)
        vbox2.Add(t, 0, wx.ALL|wx.EXPAND, self.border)
        self.dest = ReorderableList(self, [], self.get_item_text, columns=["Origin", "Size", "Name"], resize_column=3, size=(400,300))
        vbox2.Add(self.dest, 1, wx.ALL|wx.EXPAND, self.border)
        hbox.Add(vbox2, 1, wx.ALL|wx.EXPAND, 0)
        
        vbox = wx.BoxSizer(wx.VERTICAL)
        
        self.add_command_area(vbox, credits)
        
        vbox.AddStretchSpacer()
        
        btnsizer = wx.StdDialogButtonSizer()
        self.ok_btn = wx.Button(self, wx.ID_OK)
        self.ok_btn.SetDefault()
        btnsizer.AddButton(self.ok_btn)
        btn = wx.Button(self, wx.ID_CANCEL)
        btnsizer.AddButton(btn)
        btnsizer.Realize()
        vbox.Add(btnsizer, 0, wx.ALL|wx.EXPAND, self.border)
        hbox.Add(vbox, 0, wx.EXPAND, 0)
        sizer.Add(hbox, 1, wx.EXPAND, 0)
        
        self.Bind(wx.EVT_BUTTON, self.on_button)
        self.Bind(wx.EVT_TEXT, self.on_text_changed)
        
        # Don't call self.Fit() otherwise the dialog buttons are zero height
        sizer.Fit(self)
        self.check_enable()
    
    def add_command_area(self, vbox, credits):
        t = wx.StaticText(self, -1, "Run Address")
        vbox.Add(t, 0, wx.LEFT|wx.RIGHT|wx.TOP|wx.EXPAND, self.border)
        self.run_addr = wx.TextCtrl(self, -1, size=(-1, -1))
        vbox.Add(self.run_addr, 0, wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.EXPAND, self.border)
        
        if credits:
            t = wx.StaticText(self, -1, "Title (20 chars)")
            vbox.Add(t, 0, wx.LEFT|wx.RIGHT|wx.TOP|wx.EXPAND, self.border)
            self.title_20 = wx.TextCtrl(self, -1, size=(-1, -1))
            self.title_20.SetMaxLength(20)
            vbox.Add(self.title_20, 0, wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.EXPAND, self.border)

            t = wx.StaticText(self, -1, "Author (20 chars)")
            vbox.Add(t, 0, wx.LEFT|wx.RIGHT|wx.TOP|wx.EXPAND, self.border)
            self.author_20 = wx.TextCtrl(self, -1, size=(-1, -1))
            self.author_20.SetMaxLength(20)
            vbox.Add(self.author_20, 0, wx.LEFT|wx.RIGHT|wx.BOTTOM|wx.EXPAND, self.border)
        else:
            self.title_20 = self.author_20 = None

        vbox.AddSpacer(50)
        
        self.clear = b = wx.Button(self, wx.ID_DOWN, 'Clear List', size=(90, -1))
        b.Bind(wx.EVT_BUTTON, self.on_clear)
        vbox.Add(b, 0, wx.ALL|wx.EXPAND, self.border)
    
    def get_item_text(self, sid):
        s = self.segment_map[sid]
        return "%x" % s.start_addr, "%x" % len(s), s.name
        
    def on_button(self, evt):
        if evt.GetId() == wx.ID_OK:
            self.EndModal(wx.ID_OK)
        else:
            self.EndModal(wx.ID_CANCEL)
        evt.Skip()

    def on_text_changed(self, evt):
        self.ok_btn.Enable(self.can_submit())

    def on_clear(self, evt):
        self.dest.clear()

    def on_resize(self, event):
        self.Fit()
    
    def get_run_addr(self):
        text = self.run_addr.GetValue()
        try:
            addr = text_to_int(text, "hex")
            if addr < 0 or addr > 0xffff:
                addr = None
        except (ValueError, TypeError), e:
            addr = None
        return addr
    
    def can_submit(self):
        return self.get_run_addr() is not None and self.dest.GetItemCount() > 0
    
    def check_enable(self):
        self.ok_btn.Enable(self.can_submit())
    
    def get_segments(self):
        s = []
        for sid in self.dest.items:
            s.append(self.segment_map[sid])
        return s

    def get_bytes(self):
        segments = self.get_segments()
        total = 2
        for s in segments:
            total += 4 + len(s)
        total += 6
        bytes = np.zeros([total], dtype=np.uint8)
        bytes[0:2] = 0xff # FFFF header
        i = 2
        for s in segments:
            words = bytes[i:i+4].view(dtype='<u2')
            words[0] = s.start_addr
            words[1] = s.start_addr + len(s) - 1
            i += 4
            bytes[i:i + len(s)] = s[:]
            i += len(s)
        words = bytes[i:i+6].view(dtype='<u2')
        words[0] = 0x2e0
        words[1] = 0x2e1
        words[2] = self.get_run_addr()
        return bytes

    def get_extra_text(self):
        lines = []
        if self.title_20 is not None:
            lines.append(self.title_20.GetValue())
        if self.author_20 is not None:
            lines.append(self.author_20.GetValue())
        return lines


class SegmentInterleaveDialog(SegmentOrderDialog):
    instructions = "Drag segments to the right-hand list to determine interleave order. Then, choose interleave factor in bytes."
    dest_list_title = "Interleave Order"

    def add_command_area(self, vbox):
        t = wx.StaticText(self, -1, "Interleave Bytes")
        vbox.Add(t, 0, wx.ALL|wx.EXPAND, self.border)
        self.intervleave = wx.TextCtrl(self, -1, size=(-1, -1))
        vbox.Add(self.intervleave, 0, wx.ALL|wx.EXPAND, self.border)
        
        vbox.AddSpacer(50)
        
        self.clear = b = wx.Button(self, wx.ID_DOWN, 'Clear List', size=(90, -1))
        b.Bind(wx.EVT_BUTTON, self.on_clear)
        vbox.Add(b, 0, wx.ALL|wx.EXPAND, self.border)
    
    def get_length(self):
        segments = self.get_segments()
        if len(segments) == 0:
            return -1
        common = len(segments[0])
        for s in segments[1:]:
            if len(s) != common:
                return -1
        return common
    
    def get_interleave(self):
        text = self.intervleave.GetValue()
        length = self.get_length()
        try:
            num = text_to_int(text, "hex")
            if num < 0 or num > length:
                num = 0
        except (ValueError, TypeError), e:
            num = 0
        return num
    
    def can_submit(self):
        return self.get_length() > 0 and self.get_interleave() > 0


if __name__ == "__main__":
    app = wx.PySimpleApp()

    frame = wx.Frame(None, -1, "Dialog test")
#    dialog = EmulatorDialog(frame, "Test")
#    dialog.ShowModal()
#    dlg = ListReorderDialog(frame, [chr(i + 65) for i in range(26)], lambda a:str(a))
    # dlg = CheckItemDialog(frame, [chr(i + 65) for i in range(26)], lambda a:str(a))
    # if dlg.ShowModal() == wx.ID_OK:
    #     print dlg.get_checked_items()
    dlg = ChooseOnePlusCustomDialog(frame, ["one", "two"], "instructions")
    if dlg.ShowModal() == wx.ID_OK:
        print "Selected", dlg.get_selected()
    dlg.Destroy()

    app.MainLoop()
