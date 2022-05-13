'''Toggles background of views between white and non_white'''
'''Updated 2019-08-19 to add dialog for custom color selection'''
'''Updated 2019-09-10 to deal with hex colors'''

__authors__ = 'Brett Beckemeyer (bbeckemeyer@cannondesign.com)'

__context__ = 'zero-doc'

__title__ = 'BG\nToggle'

from pyrevit import DB, script
from pyrevit.coreutils.ribbon import ICON_MEDIUM

# for timing -------------------------------------------------------------------
#from pyrevit.coreutils import Timer
#timer = Timer()
# ------------------------------------------------------------------------------

app = __revit__.Application

def __selfinit__(script_cmp, ui_button_cmp, __rvt__):
	try:
		abc = app.BackgroundColor
		bg_check1 = color_to_rgb(abc)
		if bg_check1 == check_white:
			#print('Background is white!')
			bg_state = True
		else:
			#print('Background is not white!')
			bg_state = False
		script.toggle_icon(bg_state)
		return True
	except:
		return False

def toggle_state():
	abc = app.BackgroundColor
	bg_check2 = color_to_rgb(abc)
	if bg_check2 == check_white:
		app.BackgroundColor = color_non_white
		bg_state = False
	else:
		app.BackgroundColor = color_white
		bg_state = True
	script.toggle_icon(bg_state)

def hex_to_rgb(value):
	value = value.lstrip('#')
	lv = len(value)
	return tuple(int(value[i:i + lv // 3], 16) for i in range(0, lv, lv // 3))

def color_to_rgb(abc):
	rgb = (abc.Red, abc.Green, abc.Blue)
	return rgb

#-----------GET CONFIG DATA-------------------
my_config = script.get_config()
selected_color = my_config.get_option('selected_color', default_value='#FF000000')
#---------------------------------------------

selected_color_R = 0
selected_color_G = 0
selected_color_B = 0
num = 1

if selected_color:
	if selected_color[:1] == '#':
		selected_color = hex_to_rgb(selected_color)
		if len(selected_color) == 3:
			num = 0
	selected_color_R = selected_color[num]
	num = num+1
	selected_color_G = selected_color[num]
	num = num+1
	selected_color_B = selected_color[num]

#----------SETUP COLORS FOR CHECKING----------
check_non_white = []
check_white = []
bg_check = []

color_non_white = DB.Color(selected_color_R,selected_color_G,selected_color_B)
color_white = DB.Color(255,255,255)

check_non_white = (color_non_white.Red, color_non_white.Green, color_non_white.Blue)
check_white = (color_white.Red, color_white.Green, color_white.Blue)

if __name__ == '__main__':
	toggle_state()

# for timing -------------------------------------------------------------------
#endtime = timer.get_time()
#print(endtime)
# ------------------------------------------------------------------------------
