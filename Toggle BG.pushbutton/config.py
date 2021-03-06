"""Configuration window for Background Toggle."""
__author__ = 'Brett Beckemeyer (bbeckemeyer@cannondesign.com)'

#from pyrevit import revit
from pyrevit import forms
from pyrevit import script

app = __revit__.Application

def color_to_rgb(abc):
	rgb = (abc.Red,abc.Green,abc.Blue)
	return rgb

def rgb_to_hex(rgb):
	return '%02x%02x%02x' % rgb

#Get current background color for default
abc = app.BackgroundColor
rgb_color = color_to_rgb(abc)
if rgb_color == (255,255,255):
	def_color = '#FF000000'
else:
	hex_color = rgb_to_hex(rgb_color)
	def_color = '#FF' + hex_color

color = forms.ask_for_color(default=def_color)

if not (color is None):
	_config = script.get_config()
	_config.selected_color = color
	script.save_config()
