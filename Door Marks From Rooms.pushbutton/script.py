# coding: utf8
__doc__ =   'This tool sets door Mark parameter to match room numbers.' \
			'Various processes exclude certain doors from the process.' \
			'In addition, the tool evaluates proper room to attribute the ' \
			'doors to based on room priorities and assigns suffixes where ' \
			'required to the door Mark.'

__title__ = 'Door Marks From Rooms'

__authors__ = 'Brett Beckemeyer (bbeckemeyer@cannondesign.com)'

#__beta__ = '0.9'

'''Updated 2022-05-18: Added fix for to/from rooms not in same phase as doors'''

from os import path

# import itertools # not used?
from collections import defaultdict
import csv

#import codecs # not used?
#import rpw
#from rpw import revit
#import pyCD - CANNOT GET THIS MODULE TO LOAD

#from System import Guid, Enum # not used?

#from Autodesk.Revit import Exceptions
#from Autodesk.Revit.DB import ParameterType

from pyrevit import revit, DB
from pyrevit import script
from pyrevit import coreutils
from pyrevit import forms
from pyrevit.script import get_logger


#from pyrevitmep.parameter import SharedParameter

#from System.Collections.ObjectModel import ObservableCollection
#from System.Windows.Controls import DataGrid
#from System.ComponentModel import ListSortDirection, SortDescription

logger = get_logger()

#----------CONSOLE WINDOW AND ELEMENT STYLES--------
if logger.get_level() <= 10: 
	console = script.get_output()
	console.set_width(1200)
	console.set_height(480)
	console.lock_size()

	report_title = 'Door Numbering Tool'
	report_date = coreutils.current_date()

	# setup element styling
	console.add_style(
		'table { border-collapse: collapse; width:100% }'
		'table, th, td { border-bottom: 1px solid #aaa; padding: 5px;}'
		'th { background-color: #545454; color: white; }'
		'tr:nth-child(odd) {background-color: #f2f2f2}'
		)

	console.insert_divider()
#--------END CONSOLE AND STYLES-----------------------

#--------DIALOG BOX HANDLING BEGIN-------------------

# ListItem class is for calling values from dictionary into format for WPF DataGrid
class ListItem(object):
	def __init__(self, given_item, values):
		self._item = given_item
		self.check = values['check']
		self.mk_org = values['mark_org']
		self.mk_new = values['mark_new']
		self.rm_own_num = values['rm_own_num']
		self.own_rsn = values['own_rsn']
		self.rm_to_num = values['rm_to_num']
		self.rm_to_nam = values['rm_to_nam']
		self.rm_to_keycheck = values['rm_to_keychk']
		self.rm_to_prty = values['rm_to_prty']
		self.rm_frm_num = values['rm_frm_num']
		self.rm_frm_nam = values['rm_frm_nam']
		self.rm_frm_keycheck = values['rm_frm_keychk']
		self.rm_frm_prty = values['rm_frm_prty']
		self.prty_backup = values['priority_bkp']

	@property
	def revit_item(self):
		return revit.doc.GetElement(self._item)

class PriorityItem(object):
	def __init__(self, given_item, value):
		self.match_text = given_item
		self.order_index = value

# ListWindow class handles all functions pertaining to the WPF form proper
class ListWindow(forms.WPFWindow):
	def __init__(self, xaml_file_name):
		#Initiate form
		forms.WPFWindow.__init__(self, xaml_file_name)
		#Set up default values in dialog
		self._setup_defaults()

# this function sets up defult values in dialog box
	def _setup_defaults(self):
		default_appear_param = 'Appear In Schedule' # default value to set door filter parameter name in dialog
		default_room_character = '.' # default value to set room number character textbox in dialog
		default_suffix = 'A'
		self._set_reasons() # sets up reasons for table
		self.room_name_rb.IsChecked = True # by default, parameter for determining priority is set to room name
		self._setup_phase_combobox()
		self._setup_levels_combobox()
		self._set_param_textbox(default_appear_param)
		self._set_roomno_textbox(default_room_character)
		#2022-05-18: Added parameters to handle suffix options in dialog
		self._set_default_suffix(default_suffix)
		self.function_interior_b.IsChecked = True # by derault, checkbox to filter out exterior doors is checked
		self.error_filter = False # filter error default value is false, will be changed to true is needed by script
		#Function to define default priority file path
		self._define_default_priority()


#---Properties

	@property
	def _items_list(self):
		return self.items_dg.ItemsSource or []

	@_items_list.setter
	def _items_list(self, value):
		self.items_dg.ItemsSource = value

	@property
	def priorities_list(self):
		return self.priorities_dg.ItemsSource or []

	@priorities_list.setter
	def priorities_list(self, value):
		self.priorities_dg.ItemsSource = value
		# update oder indices
		self._update_order_indices()

	@property
	def phase(self):
		selected = self.phases_cb.SelectedItem
		return self.phases_dict[selected]

	@property
	def default_priority_file(self):
		return self.default_priority_cb.IsChecked

	@property
	def filter_function(self):
		return self.function_interior_b.IsChecked

	@property
	def filter_appear_param(self):
		return self.appear_param_cb.IsChecked

	@property
	def param_appear(self):
		return self.appear_param_tb.Text

#2022-05-18: Added parameters to handle suffix options in dialog
	@property
	def default_suffix(self):
		return self.default_suffix_tb.Text

	@property
	def suffix_separator(self):
		return self.suffix_separator_tb.Text

	@property
	def rooms_exclude(self):
		return self.room_exclude_cb.IsChecked

	@property
	def roomno_exclude_char(self):
		return self.roomno_character_tb.Text

	@property
	def bip_room_name(self):
		return DB.BuiltInParameter.ROOM_NAME

	@property
	def bip_room_number(self):
		return DB.BuiltInParameter.ROOM_NUMBER

	@property
	def rm_header(self):
		string = str(self.priority_param)
		list = str.split('.')

	@property
	def priority_param(self):
		if self.room_name_rb.IsChecked:
			return DB.BuiltInParameter.ROOM_NAME
		elif self.room_dept_rb.IsChecked:
			return DB.BuiltInParameter.ROOM_DEPARTMENT
		elif self.room_occ_rb.IsCecked:
			return DB.BuiltInParameter.ROOM_OCCUPANCY

	@property
	def default_text(self): #property to use as default text for priority list
		return 'DEFAULT'

	@property
	def mark_nochange(self): #property to use when there is no change to the Mark of doors
		return '~~~' #uses tilde because it sorts at the end of alphanumeric characters

	@property
	def check_default(self): #property to use as default value for checkboxes
		return True

# not currently used
	def _insert_list_in_list(self, src_list, dest_list, index):
		max_index = len(dest_list)
		if index < 0:
			index = 0

		if index > max_index:
			index = max_index

		for item in reversed(src_list):
			dest_list.insert(index, item)

		return dest_list



#---Functions that control WPF button handling

	def cancel(self, sender, args): #Cancel button handling
		self.Close()

	def select_all(self, sender, args):
		for item in self._items_list:
			item.check = True

	def deselect_all(self, sender, args):
		for item in self._items_list:
			item.check = False

	def button_select_all(self, sender, e):
		self.select_mode(mode='all')

	def button_select_none(self, sender, e):
		self.select_mode(mode='none')

	def selection_changed(self, sender, args):
		self.populate_b_activate()

	def ap_cb_selection_changed(self, sender, args):
		self.populate_b_activate()
		if not self.appear_param_cb.IsChecked:
			self.appear_param_tb.IsEnabled = False
		else:
			self.appear_param_tb.IsEnabled = True


#	Priorities list buttons
	def _pl_add_row(self, sender, args):
		existing_items = self.priorities_list
		existing_items.reverse()
		existing_items.append(PriorityItem('newitem',0))
		self.priorities_list = []
		existing_items.reverse()
		self.priorities_list = existing_items
		self.populate_b_activate()

	def _pl_move_top(self, sender, args):
		selected, non_selected = self._get_selected_nonselected()
		new_list = self._insert_list_in_list(selected, non_selected, 0)
		self.priorities_list = new_list
		self.populate_b_activate()

	def _pl_move_1up(self, sender, args):
		selected, non_selected = self._get_selected_nonselected()
		index = self.priorities_dg.ItemsSource.index(selected[0])
		new_list = self._insert_list_in_list(selected, non_selected, index - 1)
		self.priorities_list = new_list
		self.populate_b_activate()

	def _pl_move_1down(self, sender, args):
		selected, non_selected = self._get_selected_nonselected()
		index = self.priorities_dg.ItemsSource.index(selected[0])
		new_list = self._insert_list_in_list(selected, non_selected, index + 1)
		self.priorities_list = new_list
		self.populate_b_activate()

	def _pl_move_bottom(self, sender, args):
		selected, non_selected = self._get_selected_nonselected()
		new_list = self._insert_list_in_list(selected,
											 non_selected,
											 len(non_selected))
		self.priorities_list = new_list
		self.populate_b_activate()

	def b_open_file(self, sender, args): #Open priority external file button handling
		file_path = forms.pick_file(file_ext='txt',
									multi_file=False)
		if file_path:
			self._create_priority_dict(file_path)

	def b_save_file(self, sender, args):
		csv_path = forms.save_file(file_ext='txt')
		if csv_path:
			with open(csv_path, 'w') as file:
				writer = csv.writer(file, delimiter='\t')
				for i in self.priorities_list:
					key = i.match_text
					index = i.order_index
					writer.writerow([key, index])


#	Checkbox controls for DG
	def toggle_all(self, sender, args):    #pylint: disable=W0613
		'''Handle toggle all button to toggle state of all check boxes.'''
		self._set_states(flip=True)

	def check_all(self, sender, args):    #pylint: disable=W0613
		'''Handle check all button to mark all check boxes as checked.'''
		self._set_states(state=True)

	def uncheck_all(self, sender, args):    #pylint: disable=W0613
		'''Handle uncheck all button to mark all check boxes as un-checked.'''
		self._set_states(state=False)

	def check_selected(self, sender, args):    #pylint: disable=W0613
		'''Mark selected checkboxes as checked.'''
		self._set_states(state=True, selected=True)

	def uncheck_selected(self, sender, args):    #pylint: disable=W0613
		'''Mark selected checkboxes as unchecked.'''
		self._set_states(state=False, selected=True)

	def filter_error_check(self):
		if self.error_filter:
			res = forms.alert('Filter parameter not found on at least one element.', yes=False, no=False, ok=True)

# function to take master dictionary and format items for the WPF DataGrid
	def populate_dg(self, sender, args):
		self._get_selected_levels()
		self._list_priorities = self.priorities_list #set a parameter containing priorities from property
		self._create__master_dict() #creates the master dictionary used to populate the DG
		self._items_list = [ListItem(item, values) for item, values in sorted(self._master_dict.iteritems(), key = lambda x: x[1])]
		self.filter_error_check()
		self._post_populate()

# function that checks and sets the state of the populate button
	def _post_populate(self):
		self.populate_b.IsEnabled = False
		self.populate_b.Content = 'Refresh Table'
		if len(self._items_list) > 0:
			self.apply_b.IsEnabled = True

	def populate_b_activate(self):
		self.populate_b.IsEnabled = True

# function called by "apply changes" button in WPF form - sparks transaction in Revit
	def apply_changes(self, sender, args):
		filtered_list = [x for x in self._items_list if x.mk_new <> self.mark_nochange and x.check]
		self.undo_list = []
		self.error_list = []
		qty_total = len(filtered_list)
		qty_success = qty_error = 0
		confirm = forms.alert('This will change door Marks for: ' + str(qty_total) + ' elements. \n\nDo you wish to proceed?',
						yes=True, no=True, ok=False)
		if confirm:
			self.Close()
			with revit.Transaction('Apply Changes'):
				for item in filtered_list:
					rvt_item = item.revit_item
					mk_param = rvt_item.get_Parameter(DB.BuiltInParameter.DOOR_NUMBER)
					if mk_param:
						logger.debug('door mark: '+ mk_param.AsString())
						check_item = [rvt_item.Id.IntegerValue, mk_param.AsString()]
						try:
							mk_param.Set(item.mk_new)
							self.undo_list.append(check_item)
						except:
							self.error_list.append(check_item)
			qty_success = len(self.undo_list)
			qty_error = len(self.error_list)
			if qty_success > 0:
				dialog_done = forms.alert('Process completed with: \n\n' + str(qty_success) + ' elements changed \n' + str(qty_error) + ' elements unchanged',
						yes=False, no=False, ok=True)
				if qty_error > 0:
					#logger.info('Error List:')
					#logger.info(self.error_list)
					console = script.get_output()
					print('List of elements that were not changed!')
					print(' # | Element | Desired Mark')
					for i, item in enumerate(self.error_list):
						elid = DB.ElementId(item[0])
						print(' {}   {} - {}'.format(i+1, console.linkify(elid),item[1]))
						#print('{}: {} - {}'.format(i+1, item[0],item[1]))
			# print lines below should be set in if debugg
			# future functionality: the lists below should be saved out to external files for review
			logger.debug('Undo List: ')
			logger.debug(self.undo_list)
			logger.debug('---------------')
			logger.debug('Error List: ')
			logger.debug(self.error_list)

# not currently used
	def _refresh(self, sender, args):
		existing_items = self.priorities_list
		self.priorities_list = []
		self.priorities_list = existing_items

# not currently used
	def _get_selected_nonselected(self):
		selected = list(self.priorities_dg.SelectedItems)
		nonselected = []
		for item in self.priorities_list:
			if item not in selected:
				nonselected.append(item)
		return selected, nonselected

	def _set_states(self, state=True, flip=False, selected=False):
		list_of_items = []
		sel_list = self.items_dg.SelectedItems
		current_list = self.items_dg.ItemsSource
		for item in current_list:
			logger.debug(item.check)
			if selected:
				if item in sel_list:
					item.check = state
			else:
				item.check = state
			list_of_items.append(item)
		#self.items_dg.ItemsSource = None
		self.items_dg.ItemsSource = list_of_items

#---Functions that interface with WPF form, either filling data or responding to buttons'''

#	this function sets a default path for a priority text file (used if the default priority file config option is selected)
	def _define_default_priority(self):
		self._priority_folder = script.get_script_path()
		self._priority_file_name = 'priorities.txt'
		self._default_priority_path = path.join(self._priority_folder, self._priority_file_name)
		self._create_priority_dict(self._default_priority_path)

	def _setup_phase_combobox(self):
		phases = revit.doc.Phases
		if phases:
			self.phases_dict = {p.Name:p for p in phases}
			self.phases_cb.ItemsSource = sorted(self.phases_dict, reverse = True, key=lambda key: self.phases_dict[key])
			self.phases_cb.SelectedIndex = 0

	def _setup_levels_combobox(self):
		self.levels = self._get_levels()
		if self.levels:
			self._levels_dict = {l.Name:l for l in self.levels}
			self._levels_dict['All Levels'] = 0
			self.levels_cb.ItemsSource = sorted(self._levels_dict, key=lambda key: self._levels_dict[key])
			self.levels_cb.SelectedIndex = (len(self._levels_dict)-1)

	def _set_param_textbox(self, name): # set the filter parameter textbox to this value
		self.appear_param_tb.Text = name

	def _set_roomno_textbox(self, name): # set the room number character textbox to this value
		self.roomno_character_tb.Text = name

	def _set_default_suffix(self, name): # set the room number character textbox to this value
		self.default_suffix_tb.Text = name

	def _set_reasons(self):
		self.reason_0 = '0. No To or From Room found'
		self.reason_1 = '1. To Room priority'
		self.reason_2 = '2. From Room priority'
		self.reason_3 = '3. No To Room found'
		self.reason_4 = '4. No From Room found'
		self.reason_5 = '5. Room Number excluded'

	def _update_priorities_list(self):
		priorities_list = [PriorityItem(item, value) for item, value in sorted(self.priority_dict.iteritems(), key = lambda x: x[1])]
		self.priorities_list = priorities_list
		self.populate_b_activate()

	def _create_priority_dict(self, filepath):
		self.priority_dict = {}
		csv_path = filepath
		if not csv_path:
			import sys
			sys.exit()
		with open(csv_path, 'r') as csvfile:
			dialect = csv.Sniffer().sniff(csvfile.read(1024))
			csvfile.seek(0)
			reader = csv.reader(csvfile, dialect, quotechar='"', delimiter='\t', quoting=csv.QUOTE_ALL, skipinitialspace=True)
			self.priority_dict = {t[0]:int(t[1]) for t in reader}
		self._update_priorities_list()

	def sorting_changed(self, sender, args):
		order_param = args.Column.SortMemberPath
		if order_param == 'order_index':
			self.priorities_list = sorted(self.priorities_list, key=lambda x: x[1])

	def _update_order_indices(self):
		last_groupid = ''
		grouping_index = 0
		grouping_range = 1000
		for idx, item in enumerate(self.priorities_list):
			item.order_index = (idx +1) * 10



#---Functions that retrieve items'''

	def _get_selected_levels(self):
		selected_item = self.levels_cb.SelectedItem
		selected = self._levels_dict[selected_item]
		self._selected_levels = []
		if selected_item == 'All Levels':
			for l in self.levels:
				self._selected_levels.append(l.Id)
		else:
			self._selected_levels.append(selected.Id)

	def _get_levels(self):
		FEC_levels = DB.FilteredElementCollector(revit.doc).OfClass(DB.Level).ToElements()
		return FEC_levels

#	returns a list of all doors that meet the criteria
	def _get_doors(self):
		FEC_doors = DB.FilteredElementCollector(revit.doc).OfCategory(DB.BuiltInCategory.OST_Doors).OfClass(DB.FamilyInstance).ToElements()
		list_ = [] #list_l will temporarily hold doors that do not get filtered out
		for door in (x for x in FEC_doors if x.LevelId in self._selected_levels):
			logger.debug('Door ID: ' + door.Id.ToString())
			# Filter out doors that are not created in selected phase
			if door.CreatedPhaseId == self.phase.Id:
				logger.debug('This door is in the selected phase')
				appear = 1 #set binary default to check if door should be included based on appear parameter
				if self.filter_appear_param:
					appear = self._door_check_filter_appear(door) #if configuration calls for it, then run check on appearance parameter value equals yes
					logger.debug('Filter appear parameter:')
					logger.debug(appear)
				function = 1 #set binary default to check if door should be included based on function
				if self.filter_function:
					function = self._door_check_filter_function(door) #if configuration calls for it, then run check on function equals interior
				logger.debug('Appear = ' + str(appear))
				logger.debug('Function = ' + str(function))
				if appear == 1 and function == 1: #only proceed if both binaries are true
					logger.debug('Attempting to add door to dictionary...')
					try:
						list_.append(door)
						logger.debug('...successfully added!')
					except:
						logger.debug('...failed to add door to dictionary!')
		return list_


#---Non-property functions that return some value'''

	def _ask_for_string(self, defl, prmpt, ttl): # function to prompt user to enter string, returns string
		value = forms.ask_for_string(default=defl, prompt=prmpt, title=ttl)
		return value

#	this function checks the Function parameter, returns 1 if interior and 0 for all others
	def _door_check_filter_function(self, door_elem):
		fam_type = revit.doc.GetElement(door_elem.GetTypeId())
		if fam_type.get_Parameter(DB.BuiltInParameter.FUNCTION_PARAM).AsInteger() == 0:
			return 1
		else:
			return 0

#	this function checks the appear in schedule parameter, returns 1 if yes and 0 for all others
	def _door_check_filter_appear(self, door_elem):
		return_value = 1
		try:
			param = door_elem.LookupParameter(self.param_appear) # first try to get instance parameter
			if param: logger.debug('found instance parameter')
		except:
			logger.debug('instance parameter not found')
		if not param: # if instance parameter isn't found, try type parameter
			fam_type = revit.doc.GetElement(door_elem.GetTypeId())
			param = fam_type.LookupParameter(self.param_appear)
			if param: logger.debug('found type parameter')
		if param:
			logger.debug('param_appear.hasvalue')
			logger.debug(param.HasValue)
			logger.debug('param.AsInteger')
			logger.debug(str(param.AsInteger()))
			if not param.HasValue or param.AsInteger() == 1: #param.HasValue checks if yes/no parameter has been set
				return_value = 1
				logger.debug('door will be included')
			else:
				logger.debug('door will NOT be included')
				return_value = 0
		else:
			logger.debug('parameter not found')
			self.error_filter = True
			return_value = 0
		return return_value


#	Given a string value, check it against the priorities list
#	returns a list of 3 items: the priority number, the key matched, and the original value
	def _priorities_keycheck(self, value):
		output_list = []
		for i in self._list_priorities:
			key = i.match_text
			index = i.order_index
			if key.upper() in value.upper():
				outputvalue = [index, key, value]
				output_list.append(outputvalue)
		if len(output_list) == 1:
			output =  output_list[0]
		elif len(output_list) > 1:
			output_list.sort(key = lambda x: x[0])
			output = output_list[0]
		else:
			output = [False, '', '']
		return output

#	retrieves the filtered door list and
#	returns: dictionary with door Id as key and door mark, to and from rooms as values
	def _doors_dict_to_from(self):
		doors = self._get_doors()
		doors_dict = {}
		for door in doors:
			try:
				mark_org = door.LookupParameter("Mark").AsString()
			except:
				mark_org = ''
				logger.debug('Current door mark could not be found')
			logger.debug('Current door mark is: ' + mark_org)
			if mark_org:
				logger.debug('Gathering door room to / from information')
				door_phase = door.Document.GetElement(door.CreatedPhaseId)
				room_to = door.ToRoom[door_phase]
				#2022-05-18: if to room not found in door's phase, then iterate through all phases starting at most recent
				if not room_to:
					logger.debug('Room to of door phase not found')
					for n, p in sorted(self.phases_dict.items(), reverse=True): #should the default be reversed? user definable?
						logger.debug('Trying phase: ' + n)
						try:
							room_to = door.ToRoom[p]
						except:
							pass
						if room_to: break
				room_from = door.FromRoom[door_phase]
				#2022-05-18: if from room not found in door's phase, then iterate through all phases starting at most recent
				if not room_from:
					logger.debug('Room from of door phase not found')
					for n, p in sorted(self.phases_dict.items(), reverse=True): #should the default be reversed? user definable?
						logger.debug('Trying phase: ' + n)
						try:
							room_from = door.FromRoom[p]
						except:
							pass
						if room_from: break
				#room_to = door.ToRoom[self.phase]
				#room_from = door.FromRoom[self.phase]
				if room_to or room_from: #if neither a to nor a from room is found, door is excluded from the dictionary
					dict_add = {'mark_org': mark_org,
								'rm_to':room_to, 
								'rm_from':room_from}
					doors_dict[door.Id] = dict_add
			dict_add = {}
			room_to = ''
			room_from = ''
			mark_org = ''
		return doors_dict



#---Functions that perform class actions (do not return anything)'''

#	if no item in priority list has text of 'default', then user is prompted for default value
	def _set_default_priority_index(self):
		default_index = False
		for i in self.priorities_list:
			key = i.match_text.upper()
			index = i.order_index
			if self.default_text in key:
				default_index = index
		if default_index:
			self.default_priority_index = default_index
		else:
			string_value = self._ask_for_string('99', 'Enter a default priority (integer):', 'Default Priority')
			if not string_value:
				self.Close()
			else:
				while not string_value.isnumeric():
					self._ask_for_string('99', 'ENTER AN INTEGER:', 'Default Priority')
				self.default_priority_index = int(string_value)

#	function that performs calculations to determine new door mark
	def _process_doors(self):
		if self.rooms_exclude and self.roomno_exclude_char <> '':
			exclude_rooms = True
		else: 
			exclude_rooms = False
		p_param = self.priority_param
		logger.debug('priority param: ')
		logger.debug(p_param)
		#doors_dict = self._doors_dict_to_from()
		self._set_default_priority_index()
		rooms_list = []
		self._rooms_dict, self._master_dict, self._doors_backup_priority_dict = defaultdict(list), {}, {}
		for id, values in self._doors_dict_to_from().iteritems():
			room_to_priority = room_from_priority = False # sets initial priority values to False, used to filter out non-matches
			priority_backup = priority_backup_backup = 0
			room_to_name = room_to_num = room_to_dept = room_to_occ = '' # sets initial room to parameters to empty values
			room_from_name = room_from_num = room_from_dept = room_from_occ = '' # sets initial room from parameters to empty values
			owned_reason = 'None' # sets default owned reason
			room_ownedby = room_ownedby_backup = room_ownedby_num = room_to_key = room_from_key = ''
			room_to, room_from, mark_org = values['rm_to'], values['rm_from'], values['mark_org'] # for each door in the dict, get room to, room from, and original mark value
			room_to_keycheck_value = room_from_keycheck_value = room_to_keycheck = room_from_keycheck = ''
			try:
				room_to_name = (room_to.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString())
				room_to_num = (room_to.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString())
				room_to_keycheck = (room_to.get_Parameter(p_param).AsString())
			except:
				a = 'a'
			try:
				room_from_name = (room_from.get_Parameter(DB.BuiltInParameter.ROOM_NAME).AsString())
				room_from_num = (room_from.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString())
				room_from_keycheck = (room_from.get_Parameter(p_param).AsString())
			except:
				a = 'a'
			rtk = self._priorities_keycheck(room_to_keycheck) # priorities keycheck takes the room and returns three values
			logger.debug('to priorities list: ' + str(rtk[0]) + ', ' + rtk[1] + ', ' + rtk[2])
			room_to_priority, room_to_key, room_to_keycheck_value = rtk[0], rtk[1], rtk[2] # returned values converted to three separate parameters
			rfk = self._priorities_keycheck(room_from_keycheck) # priorities keycheck takes the room and returns three values
			logger.debug('from priorities list: ' + str(rfk[0]) + ', ' + rfk[1] + ', ' + rfk[2])
			room_from_priority, room_from_key, room_from_keycheck_value = rfk[0], rfk[1], rfk[2] # returned values converted to three separate parameters
			if not room_to_priority: room_to_priority = self.default_priority_index # if no priority found, use default value
			if not room_from_priority: room_from_priority = self.default_priority_index # if no priority found, use default value
			if not room_to and not room_from:
				owned_reason = self.reason_0
			else:
				if not room_to: # if no to room, set owned room to from room
					owned_reason = self.reason_3
				elif not room_from:  # else if no from room, set owned room to to room
					owned_reason = self.reason_4
				else: # if there are both from and to rooms, then use priority number to determine ownership
					if room_from_priority > room_to_priority:
						owned_reason = self.reason_2
					else:
						owned_reason = self.reason_1
			if owned_reason == self.reason_2 or owned_reason == self.reason_3:
				room_ownedby = room_from
				room_ownedby_backup = room_to
				priority_backup = room_to_priority
				priority_backup_backup = room_from_priority
			elif owned_reason == self.reason_1 or owned_reason == self.reason_4:
				room_ownedby = room_to
				room_ownedby_backup = room_from
				priority_backup = room_from_priority
				priority_backup_backup = room_to_priority
			try:
				room_ownedby_num = room_ownedby.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString() # get room number of owning room
			except:
				a = 'a'
			
			if exclude_rooms: # If room number exclude, then flip ownedby room
				if self.roomno_exclude_char in room_ownedby_num:
					owned_reason = self.reason_5
					room_ownedby = room_ownedby_backup
					room_ownedby_num = room_ownedby.get_Parameter(DB.BuiltInParameter.ROOM_NUMBER).AsString()
					priority_backup = priority_backup_backup
			
			rooms_list.append((room_ownedby_num,id)) # adds owned room num and room id to room_list
			self._doors_backup_priority_dict[id] = priority_backup # adds backup priority room to backup dictionary
			dict_add = {
						'check': self.check_default,
						'mark_org': mark_org,
						'rm_to_nam': room_to_name,
						'rm_to_num': room_to_num,
						'rm_to_dept': room_to_dept,
						'rm_to_occ': room_to_occ,
						'rm_to_prty': room_to_priority,
						'rm_to_key': room_to_key,
						'rm_to_keychk': room_to_keycheck,
						'rm_frm_nam': room_from_name,
						'rm_frm_num': room_from_num,
						'rm_frm_dept': room_from_dept,
						'rm_frm_occ': room_from_occ,
						'rm_frm_prty': room_from_priority,
						'rm_frm_key': room_from_key,
						'rm_frm_keychk': room_from_keycheck,
						'rm_own_num': room_ownedby_num,
						'own_rsn': owned_reason,
						'priority_bkp': priority_backup
						}
			logger.debug('dict_add')
			logger.debug(dict_add)
			self._master_dict[id] = dict_add
		for room, drid in rooms_list: # takes room list and converts to dictionary so mulitple doors are listed under a single room key
			self._rooms_dict[room].append(drid)

#	the master dictionary holds all pertinent doors and their parameters for the review table as well as the apply function
	def _create__master_dict(self):
		self._process_doors()
		self.table_reassign = []
		logger.debug('rooms dictionary')
		logger.debug(self._rooms_dict)
		for room in self._rooms_dict.keys():
			logger.debug('processing room: ' + room)
			drids = self._rooms_dict.get(room)
			marks_list = []
			suffix = ''
			if len(drids) > 1:
				logger.debug('more than 1 door in this room')
				drids.sort(key = self._doors_backup_priority_dict.get) # !! when default priority used then this sort is unpredictable
				for drid in drids:
					marks_list.append(self._master_dict[drid]['mark_org'])
				logger.debug('marks found in this room: ')
				logger.debug(marks_list)
			for drid in drids:
				check = self.check_default
				#2022-05-18: Added parameters to handle suffix options in dialog
				suffix = self.default_suffix
				separator = self.suffix_separator
				mark_new = ''
				if len(marks_list) > 1:
					#2022-05-18: Added parameters to handle suffix options in dialog
					mark_new = room + separator + suffix
				else:
					mark_new = room
				mark_old = self._master_dict[drid]['mark_org']
				if mark_new <> mark_old:
					try:
						marks_list.remove(mark_old)
						logger.debug('removing old mark: ' + mark_old)
					except:
						a = 'a'
					if mark_new in marks_list:
						logger.debug('mark already exists: ' + mark_new)
						logger.debug('marks list is now: ')
						logger.debug(marks_list)
						while mark_new in marks_list:
							suffix = chr(ord(suffix) + 1)
							#2022-05-18: Added parameters to handle suffix options in dialog
							mark_new = room + separator + suffix
							logger.debug('new mark to test is: ' + mark_new)
					marks_list.append(mark_new)
					logger.debug('adding new mark: ' + mark_new)
				if mark_new == mark_old:
					mark_new = self.mark_nochange
					check = False
				self.table_reassign.append((drid, mark_old, mark_new))
				dict_add = {'check': check, 'mark_new': mark_new}
				self._master_dict[drid].update(dict_add)

#---------DIALOG BOX HANDLING END-------------------

proceed = forms.alert('WARNING!\n\nThis script is a work in progress for testing. If run, you will be allowed to review and approve any proposed changes. \n\nFeedback is appreciated!\n\nDo you wish to proceed?',
				title='Test Script Warning', yes=True, no=True, ok=False, exitscript = True)

#showme()
ListWindow('ListWindow.xaml').ShowDialog()
