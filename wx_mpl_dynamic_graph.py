"""
GP:
Changed datasource, title, and refresh interval to use
as a poor man's Arduino oscilliscope.

This demo demonstrates how to draw a dynamic mpl (matplotlib) 
plot in a wxPython application.

It allows "live" plotting as well as manual zooming to specific
regions.

Both X and Y axes allow "auto" or "manual" settings. For Y, auto
mode sets the scaling of the graph to see all the data points.
For X, auto mode makes the graph "follow" the data. Set it X min
to manual 0 to always see the whole data from the beginning.

Note: press Enter in the 'manual' text box to make a new value 
affect the plot.

Eli Bendersky (eliben@gmail.com)
License: this code is in the public domain
Last modified: 31.07.2008
"""
import os
import pprint
import random
import sys
import wx

DEFAULT_X_RANGE = 200

# The recommended way to use wx with mpl is with the WXAgg
# backend. 
#
import matplotlib
matplotlib.use('WXAgg')
from matplotlib.figure import Figure
from matplotlib.backends.backend_wxagg import \
    FigureCanvasWxAgg as FigCanvas, \
    NavigationToolbar2WxAgg as NavigationToolbar
import numpy as np
import pylab
#Data comes from here
from Arduino_Monitor import SerialData as DataGen

def apply_over_nested_list(fn, lst, min_x=0):
    return fn([fn(sublist[min_x:]) for sublist in lst])

class BoundControlBox(wx.Panel):
    """ A static box with a couple of radio buttons and a text
        box. Allows to switch between an automatic mode and a 
        manual mode with an associated value.
    """
    def __init__(self, parent, ID, label, initval):
        wx.Panel.__init__(self, parent, ID)
        
        self.value = initval
        
        box = wx.StaticBox(self, -1, label)
        sizer = wx.StaticBoxSizer(box, wx.VERTICAL)
        
        self.radio_auto = wx.RadioButton(self, -1, 
            label="Auto", style=wx.RB_GROUP)
        self.radio_manual = wx.RadioButton(self, -1,
            label="Manual")
        self.manual_text = wx.TextCtrl(self, -1, 
            size=(35,-1),
            value=str(initval),
            style=wx.TE_PROCESS_ENTER)
        
        #self.Bind(wx.EVT_UPDATE_UI, self.on_update_manual_text, self.manual_text)
        self.Bind(wx.EVT_TEXT_ENTER, self.on_text_enter, self.manual_text)
        
        manual_box = wx.BoxSizer(wx.HORIZONTAL)
        manual_box.Add(self.radio_manual, flag=wx.ALIGN_CENTER_VERTICAL)
        manual_box.Add(self.manual_text, flag=wx.ALIGN_CENTER_VERTICAL)
        
        sizer.Add(self.radio_auto, 0, wx.ALL, 10)
        sizer.Add(manual_box, 0, wx.ALL, 10)
        
        self.SetSizer(sizer)
        sizer.Fit(self)
    
    def on_update_manual_text(self, event):
        self.manual_text.Enable(self.radio_manual.GetValue())
    
    def on_text_enter(self, event):
        self.value = self.manual_text.GetValue()
    
    def is_auto(self):
        return self.radio_auto.GetValue()
        
    def manual_value(self):
        return self.value


class GraphFrame(wx.Frame):
    """ The main frame of the application
    """
    title = 'Demo: dynamic matplotlib graph'
    
    def __init__(self, datagen, poll_interval):
        wx.Frame.__init__(self, None, -1, self.title)
        
        self.datagen = datagen
        self.data = []
        self.paused = False
        self.autoscale_min_x = 0
        
        self.create_menu()
        self.create_status_bar()
        self.create_main_panel()
        
        self.redraw_timer = wx.Timer(self)
        self.Bind(wx.EVT_TIMER, self.on_redraw_timer, self.redraw_timer)        
        self.redraw_timer.Start(poll_interval)

    def create_menu(self):
        self.menubar = wx.MenuBar()
        
        menu_file = wx.Menu()
        m_expt = menu_file.Append(-1, "&Save plot\tCtrl-S", "Save plot to file")
        self.Bind(wx.EVT_MENU, self.on_save_plot, m_expt)
        menu_file.AppendSeparator()
        m_exit = menu_file.Append(-1, "E&xit\tCtrl-X", "Exit")
        self.Bind(wx.EVT_MENU, self.on_exit, m_exit)
                
        self.menubar.Append(menu_file, "&File")
        self.SetMenuBar(self.menubar)

    def create_main_panel(self):
        self.panel = wx.Panel(self)

        self.init_plot()
        self.canvas = FigCanvas(self.panel, -1, self.fig)

        self.xmin_control = BoundControlBox(self.panel, -1, "X min", 0)
        self.xmax_control = BoundControlBox(self.panel, -1, "X max", 50)
        self.ymin_control = BoundControlBox(self.panel, -1, "Y min", 0)
        self.ymax_control = BoundControlBox(self.panel, -1, "Y max", 100)
        
        self.pause_button = wx.Button(self.panel, -1, "Pause")
        self.Bind(wx.EVT_BUTTON, self.on_pause_button, self.pause_button)
        
        self.reset_button = wx.Button(self.panel, -1, "Reset AutoScale")
        self.Bind(wx.EVT_BUTTON, self.on_reset, self.reset_button)
        
        self.cb_grid = wx.CheckBox(self.panel, -1, 
            "Show Grid",
            style=wx.ALIGN_RIGHT)
        self.Bind(wx.EVT_CHECKBOX, self.on_cb_grid, self.cb_grid)
        self.cb_grid.SetValue(True)
        
        self.cb_xlab = wx.CheckBox(self.panel, -1, 
            "Show X labels",
            style=wx.ALIGN_RIGHT)
        self.Bind(wx.EVT_CHECKBOX, self.on_cb_xlab, self.cb_xlab)        
        self.cb_xlab.SetValue(True)
        
        self.hbox1 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox1.Add(self.pause_button, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self.hbox1.AddSpacer(20)
        self.hbox1.Add(self.reset_button, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self.hbox1.AddSpacer(20)
        self.hbox1.Add(self.cb_grid, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        self.hbox1.AddSpacer(10)
        self.hbox1.Add(self.cb_xlab, border=5, flag=wx.ALL | wx.ALIGN_CENTER_VERTICAL)
        
        self.hbox2 = wx.BoxSizer(wx.HORIZONTAL)
        self.hbox2.Add(self.xmin_control, border=5, flag=wx.ALL)
        self.hbox2.Add(self.xmax_control, border=5, flag=wx.ALL)
        self.hbox2.AddSpacer(24)
        self.hbox2.Add(self.ymin_control, border=5, flag=wx.ALL)
        self.hbox2.Add(self.ymax_control, border=5, flag=wx.ALL)
        
        self.send_entry = wx.TextCtrl(self.panel, -1, style=wx.TE_PROCESS_ENTER)
        self.Bind(wx.EVT_TEXT_ENTER, self.on_send, self.send_entry)
        
        self.vbox = wx.BoxSizer(wx.VERTICAL)
        self.vbox.Add(self.canvas, 1, flag=wx.LEFT | wx.TOP | wx.GROW)        
        self.vbox.Add(self.hbox1, 0, flag=wx.ALIGN_LEFT | wx.TOP)
        self.vbox.Add(self.hbox2, 0, flag=wx.ALIGN_LEFT | wx.TOP)
        self.vbox.Add(self.send_entry, 0, flag=wx.ALIGN_LEFT | wx.TOP | wx.GROW)
        
        self.panel.SetSizer(self.vbox)
        self.vbox.Fit(self)
    
    def create_status_bar(self):
        self.statusbar = self.CreateStatusBar()

    def init_plot(self):
        self.dpi = 100
        self.fig = Figure((3.0, 3.0), dpi=self.dpi)

        self.axes = self.fig.add_subplot(111)
        self.axes.set_axis_bgcolor('black')
        self.axes.set_title('Arduino Serial Data', size=12)
        
        pylab.setp(self.axes.get_xticklabels(), fontsize=8)
        pylab.setp(self.axes.get_yticklabels(), fontsize=8)
        self.plot_data = []
        colors = [(1,1,0),(1,0,0),(0,1,0),(0,0,1),(0,1,1)]
        
        for color, column in zip(colors, self.datagen.columns):
            self.data.append([])
            self.plot_data.append(
                self.axes.plot(
                        self.data[-1], 
                    linewidth=1,
                    color=color,
                )[0])

    def draw_plot(self):
        """ Redraws the plot
        """
        # when xmin is on auto, it "follows" xmax to produce a 
        # sliding window effect. therefore, xmin is assigned after
        # xmax.
        #
        if self.xmax_control.is_auto():
            xmax = max(len(self.data[0]), DEFAULT_X_RANGE)
        else:
            xmax = int(self.xmax_control.manual_value())
            
        if self.xmin_control.is_auto():            
            xmin = xmax - DEFAULT_X_RANGE
        else:
            xmin = int(self.xmin_control.manual_value())

        # for ymin and ymax, find the minimal and maximal values
        # in the data set and add a mininal margin.
        # 
        # note that it's easy to change this scheme to the 
        # minimal/maximal value in the current display, and not
        # the whole data set.
        # 
        if self.ymin_control.is_auto():
            ymin = round(apply_over_nested_list(min, self.data, self.autoscale_min_x), 0) - 1
        else:
            ymin = int(self.ymin_control.manual_value())
        
        if self.ymax_control.is_auto():
            ymax = round(apply_over_nested_list(max, self.data, self.autoscale_min_x), 0) + 1
            ymax += (ymax - ymin)/10 # so that both lines are visible if they are very far apart
        else:
            ymax = int(self.ymax_control.manual_value())

        self.axes.set_xbound(lower=xmin, upper=xmax)
        self.axes.set_ybound(lower=ymin, upper=ymax)
        
        # anecdote: axes.grid assumes b=True if any other flag is
        # given even if b is set to False.
        # so just passing the flag into the first statement won't
        # work.
        #
        if self.cb_grid.IsChecked():
            self.axes.grid(True, color='gray')
        else:
            self.axes.grid(False)

        # Using setp here is convenient, because get_xticklabels
        # returns a list over which one needs to explicitly 
        # iterate, and setp already handles this.
        #  
        pylab.setp(self.axes.get_xticklabels(), 
            visible=self.cb_xlab.IsChecked())
        
        for plot_data, data in zip(self.plot_data, self.data):
            plot_data.set_xdata(np.arange(len(data)))
            plot_data.set_ydata(np.array(data))
        
        self.canvas.draw()
    
    def on_pause_button(self, event):
        self.paused = not self.paused
        label = "Resume" if self.paused else "Pause"
        self.pause_button.SetLabel(label)
        
    def on_reset(self, event):
        self.autoscale_min_x = len(self.data[0])
    
    def on_cb_grid(self, event):
        self.draw_plot()
    
    def on_cb_xlab(self, event):
        self.draw_plot()
    
    def on_save_plot(self, event):
        file_choices = "PNG (*.png)|*.png"
        
        dlg = wx.FileDialog(
            self, 
            message="Save plot as...",
            defaultDir=os.getcwd(),
            defaultFile="plot.png",
            wildcard=file_choices,
            style=wx.SAVE)
        
        if dlg.ShowModal() == wx.ID_OK:
            path = dlg.GetPath()
            self.canvas.print_figure(path, dpi=self.dpi)
            self.flash_status_message("Saved to %s" % path)
    
    def on_redraw_timer(self, event):
        # if paused do not add data, but still redraw the plot
        # (to respond to scale modifications, grid change, etc.)
        #

        if not self.paused:
            for olddata, newdata in zip(self.data, self.datagen.next()):
                olddata.extend(newdata)
        
        self.draw_plot()
    
    def on_exit(self, event):
        self.Destroy()
    
    def flash_status_message(self, msg, flash_len_ms=1500):
        self.statusbar.SetStatusText(msg)
        self.timeroff = wx.Timer(self)
        self.Bind(
            wx.EVT_TIMER, 
            self.on_flash_status_off, 
            self.timeroff)
        self.timeroff.Start(flash_len_ms, oneShot=True)
    
    def on_flash_status_off(self, event):
        self.statusbar.SetStatusText('')
        
    def on_send(self, event):
        text = self.send_entry.GetValue()
        print "sending", text
        self.datagen.sendLine(str(text))


if __name__ == '__main__':
    columns = [0]
    
    import optparse
    parser = optparse.OptionParser()
    
    parser.add_option('-d', '--device', type='string', dest='port', default='/dev/ttyUSB0',
        help="Serial port name")
            
    parser.add_option('-t', '--poll-interval', type='int', dest='poll', default=100,
        help="Poll interval in ms")
        
    parser.add_option('-s', '--save', type='string', dest='file', default='',
        help="Save raw data to file")
    
    (options, args) = parser.parse_args()
    
    if len(args) > 0:
        columns = [int(i) for i in args]
    
    datagen = DataGen(options.port, columns, options.file)
    
    app = wx.PySimpleApp()
    app.frame = GraphFrame(datagen, options.poll)
    app.frame.Show()
    app.MainLoop()

