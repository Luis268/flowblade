"""
    Flowblade Movie Editor is a nonlinear video editor.
    Copyright 2012 Janne Liljeblad.

    This file is part of Flowblade Movie Editor <http://code.google.com/p/flowblade>.

    Flowblade Movie Editor is free software: you can redistribute it and/or modify
    it under the terms of the GNU General Public License as published by
    the Free Software Foundation, either version 3 of the License, or
    (at your option) any later version.

    Flowblade Movie Editor is distributed in the hope that it will be useful,
    but WITHOUT ANY WARRANTY; without even the implied warranty of
    MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
    GNU General Public License for more details.

    You should have received a copy of the GNU General Public License
    along with Flowblade Movie Editor.  If not, see <http://www.gnu.org/licenses/>.
"""
import cairo
import gtk
import mlt
import pango
import pangocairo

from cairoarea import CairoDrawableArea
import editorstate
import guiutils
import utils

SLOT_W = 60
METER_SLOT_H = 416
CONTROL_SLOT_H = 300

DASH_INK = 5.0
DASH_SKIP = 2.0
DASHES = [DASH_INK, DASH_SKIP, DASH_INK, DASH_SKIP]

METER_LIGHTS = 57
METER_HEIGHT = METER_LIGHTS * DASH_INK + (METER_LIGHTS - 1) * DASH_SKIP
METER_WIDTH = 10

# These are calculated using IEC_Scale function in MLT
DB_IEC_MINUS_2 = 0.95
DB_IEC_MINUS_4 = 0.9
DB_IEC_MINUS_6 = 0.85
DB_IEC_MINUS_10 = 0.75
DB_IEC_MINUS_12 = 0.70

PEAK_FRAMES = 5

RED_1 = (0, 1, 0, 0, 1)
RED_2 = (1 - DB_IEC_MINUS_4, 1, 0, 0, 1)
YELLOW_1 = (1 - DB_IEC_MINUS_4 + 0.001, 1, 1, 0, 1)
YELLOW_2 = (1 - DB_IEC_MINUS_12, 1, 1, 0, 1)
GREEN_1 = (1 - DB_IEC_MINUS_12 + 0.001, 0, 1, 0, 1)
GREEN_2 = (1, 0, 1, 0, 1)

LEFT_CHANNEL = "_audio_level.0"
RIGHT_CHANNEL = "_audio_level.1"

MONITORING_AVAILABLE = False

_monitor_window = None
_update_ticker = None
_level_filters = [] # 0 master, 1 - (len - 1) editable tracks
_audio_levels = [] # 0 master, 1 - (len - 1) editable tracks

def IEC_Scale(dB):
    fScale = 1.0

    if (dB < -70.0):
        fScale = 0.0
    elif (dB < -60.0):
        fScale = (dB + 70.0) * 0.0025
    elif (dB < -50.0):
        fScale = (dB + 60.0) * 0.005 + 0.025
    elif (dB < -40.0):
        fScale = (dB + 50.0) * 0.0075 + 0.075
    elif (dB < -30.0):
        fScale = (dB + 40.0) * 0.015 + 0.15
    elif (dB < -20.0):
        fScale = (dB + 30.0) * 0.02 + 0.3
    elif (dB < -0.001 or dB > 0.001):
        fScale = (dB + 20.0) * 0.025 + 0.5

    return fScale
    
def init():
    audio_level_filter = mlt.Filter(self.profile, "audiolevel")
    print DB_IEC_MINUS_2, DB_IEC_MINUS_6, IEC_Scale(12)

    global MONITORING_AVAILABLE
    if audio_level_filter != None:
        MONITORING_AVAILABLE = True
    else:
        MONITORING_AVAILABLE = False
    
def show_audio_monitor():
    print DB_IEC_MINUS_2, DB_IEC_MINUS_6, IEC_Scale(-12)
    global _monitor_window
    if _monitor_window != None:
        return
    
    _init_level_filters()

    _monitor_window = AudioMonitorWindow()
        
    global _update_ticker
    _update_ticker = utils.Ticker(_audio_monitor_update, 0.04)
    _update_ticker.start_ticker()

def _init_level_filters():
    # We're attaching level filters only to MLT objects and adding nothing to python objects,
    # so when Sequence is saved these filters will automatically be removed.
    # Filters are not part of sequence.Sequence object because they just used for monitoring,
    #
    # Track/master gain values are persistant, they're also editing desitions 
    # and are therefpre part of Sequence objects.
    global _level_filters
    _level_filters = []
    seq = editorstate.current_sequence()
    # master level filter
    _level_filters.append(_add_audio_level_filter(seq.tractor, seq.profile))
    # editable track level filters
    for i in range(1, len(seq.tracks) - 1):
        _level_filters.append(_add_audio_level_filter(seq.tracks[i], seq.profile))

def _add_audio_level_filter(producer, profile):
    audio_level_filter = mlt.Filter(profile, "audiolevel")
    producer.attach(audio_level_filter)
    return audio_level_filter

def _audio_monitor_update():
    global _audio_levels
    _audio_levels = []
    for i in range(0, len(_level_filters)):
        audio_level_filter = _level_filters[i]
        l_val = _get_channel_value(audio_level_filter, LEFT_CHANNEL)
        r_val = _get_channel_value(audio_level_filter, RIGHT_CHANNEL)
        _audio_levels.append((l_val, r_val))

    _monitor_window.meters_area.widget.queue_draw()


def _get_channel_value(audio_level_filter, channel_property):
    level_value = audio_level_filter.get(channel_property)
    if level_value == None:
        level_value  = "0.0"

    try:
        level_float = float(level_value)
    except Exception:
        level_float = 0.0

    return level_float
        
class AudioMonitorWindow(gtk.Window):
    def __init__(self):
        gtk.Window.__init__(self)
        seq = editorstate.current_sequence()
        meters_count = 1 + (len(seq.tracks) - 2) # master + editable tracks
        self.gain_controls = []
        
        self.meters_area = MetersArea(meters_count)
        gain_control_area = gtk.HBox(False, 0)
        for i in range(0, meters_count):
            if i == 0:
                name = "Master"
            else:
                name = utils.get_track_name(seq.tracks[i], seq)
            gain = GainControl(name)
            if i == 0:
                tmp = gain
                gain = gtk.EventBox()
                gain.add(tmp)
                gain.modify_bg(gtk.STATE_NORMAL, gtk.gdk.Color(red=0.8, green=0.8, blue=0.8))
            self.gain_controls.append(gain)
            gain_control_area.pack_start(gain, False, False, 0)

        meters_frame = gtk.Frame()
        meters_frame.add(self.meters_area.widget)

        pane = gtk.VBox(False, 1)
        pane.pack_start(meters_frame, True, True, 0)
        pane.pack_start(gain_control_area, True, True, 0)

        align = gtk.Alignment()
        align.set_padding(12, 12, 4, 4)
        align.add(pane)

        # Set pane and show window
        self.add(align)
        self.show_all()
        self.set_resizable(False)

class MetersArea:
    def __init__(self, meters_count):
        w = SLOT_W * meters_count
        h = METER_SLOT_H
        
        self.widget = CairoDrawableArea(w,
                                        h, 
                                        self._draw)
        
        self.audio_meters = [] # displays both l_Value and r_value
        for i in range(0, meters_count):
            self.audio_meters.append(AudioMeter(METER_HEIGHT))
            
    def _draw(self, event, cr, allocation):
        x, y, w, h = allocation

        cr.set_source_rgb(0,0,0)
        cr.rectangle(0, 0, w, h)
        cr.fill()

        grad = cairo.LinearGradient (0, 0, 0, METER_HEIGHT)
        grad.add_color_stop_rgba(*RED_1)
        grad.add_color_stop_rgba(*RED_2)
        grad.add_color_stop_rgba(*YELLOW_1)
        grad.add_color_stop_rgba(*YELLOW_2)
        grad.add_color_stop_rgba(*GREEN_1)
        grad.add_color_stop_rgba(*GREEN_2)

        for i in range(0, len(_audio_levels)):
            meter = self.audio_meters[i]
            l_value, r_value = _audio_levels[i]
            x = i * SLOT_W
            meter.display_value(cr, x, l_value, r_value, grad)

class AudioMeter:
    def __init__(self, height):
        self.left_channel = ChannelMeter(height, "L")
        self.right_channel = ChannelMeter(height, "R")

    def display_value(self, cr, x, value_left, value_right, grad):
        cr.set_source(grad)
        cr.set_dash(DASHES, 0) 
        cr.set_line_width(METER_WIDTH)
        self.left_channel.display_value(cr, x + 18, value_left)

        cr.set_source(grad)
        cr.set_dash(DASHES, 0) 
        cr.set_line_width(METER_WIDTH)
        self.right_channel.display_value(cr, x + SLOT_W / 2 + 6, value_right)
        
class ChannelMeter:
    def __init__(self, height, channel_text):
        self.height = height
        self.channel_text = channel_text
        self.peak = 0.0
        self.countdown = 0

    def display_value(self, cr, x, value):
        top = self.get_meter_y_for_value(value)
        
        cr.move_to(x, self.height)
        cr.line_to(x, top)
        cr.stroke()
        
        if value > self.peak:
            self.peak = value
            self.countdown = PEAK_FRAMES
        
        if self.peak > value:
            cr.rectangle(x - METER_WIDTH / 2, 
                         self.get_meter_y_for_value(self.peak) + DASH_SKIP * 2 + DASH_INK, # this y is just empirism, looks right
                         METER_WIDTH,
                         DASH_INK)
            cr.fill()

        self.countdown = self.countdown - 1
        if self.countdown <= 0:
             self.peak = 0

        self.draw_channel_identifier(cr, x)
        
        #cr.set_dash(DASHES, 0) 
        #cr.set_line_width(1.0)
        #self.draw_value_line(cr, x, DB_IEC_MINUS_4)
        #self.draw_value_line(cr, x, DB_IEC_MINUS_12)
        
    def get_meter_y_for_value(self, value):
        y = self.get_y_for_value(value)
        dash_sharp_pad = (self.height - y) % (DASH_INK + DASH_SKIP)
        return y + dash_sharp_pad

    def get_y_for_value(self, value):
        return self.height - (value * self.height)
    
    def draw_value_line(self, cr, x, value):
        y = self.get_y_for_value(value)
        cr.move_to(x, y)
        cr.line_to(x + 10, y)
        cr.stroke()
    
    def draw_channel_identifier(self, cr, x):
        pango_context = pangocairo.CairoContext(cr)
        layout = pango_context.create_layout()
        layout.set_text(self.channel_text)
        desc = pango.FontDescription("Sans Bold 8")
        layout.set_font_description(desc)

        pango_context.set_source_rgb(1, 1, 1)
        pango_context.move_to(x - 4, self.height + 2)
        pango_context.update_layout(layout)
        pango_context.show_layout(layout)
        

class GainControl(gtk.Frame):
    def __init__(self, name):
        gtk.Frame.__init__(self)
        self.adjustment = gtk.Adjustment(value=100, lower=0, upper=100, step_incr=1)
        self.slider = gtk.VScale()
        self.slider.set_adjustment(self.adjustment)
        self.slider.set_size_request(SLOT_W - 10, CONTROL_SLOT_H - 105)
        self.slider.set_inverted(True)

        self.pan_adjustment = gtk.Adjustment(value=0, lower=-100, upper=100, step_incr=1)
        self.pan_slider = gtk.HScale()
        self.pan_slider.set_adjustment(self.pan_adjustment)
        self.pan_slider.set_sensitive(False)
        
        self.pan_button = gtk.ToggleButton("Pan")
        self.pan_button.connect("toggled", self.pan_active_toggled)

        label = guiutils.bold_label(name)

        vbox = gtk.VBox(False, 0)
        vbox.pack_start(guiutils.get_pad_label(5,5), False, False, 0)
        vbox.pack_start(label, False, False, 0)
        vbox.pack_start(guiutils.get_pad_label(5,5), False, False, 0)
        vbox.pack_start(self.slider, False, False, 0)
        vbox.pack_start(self.pan_button, False, False, 0)
        vbox.pack_start(self.pan_slider, False, False, 0)
        vbox.pack_start(guiutils.get_pad_label(5,5), False, False, 0)

        self.add(vbox)
        self.set_size_request(SLOT_W, CONTROL_SLOT_H)
        
    def pan_active_toggled(self, widget):
        if widget.get_active():
            self.pan_slider.set_sensitive(True)
        else:
            self.pan_slider.set_sensitive(False)
        
        self.pan_slider.set_value(0.0)
        
        
        