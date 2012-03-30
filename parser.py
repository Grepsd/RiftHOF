# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import sys, os
import pickle, bz2
import re
#import time
import logparse.models
from zipfile import ZipFile
from django.conf import settings

# boss list, this is temporary list which is working only for french bosses.
# do need a list with the boss name in each languge we want to support
bosses_list 	= {
	'Murdantix':				'murdantix', 
	'Étripeur d\'âmes Zilas': 	'zilas',
	'Soulrender Zilas': 		'zilas',
	'Grugonim':					'grugonim', 
	'Roi runique Molinar': 		'molinar', 
	'Estrode':					'estrode',
	'Matrone Zamira':			'zamira', 
	'Matron Zamira':			'zamira',
	'Sicaron':					'sicaron', 
	'Inquisiteur Garau':		'garau', 
	'Inquisitor Garau':			'garau',
	'Inwar Noirflux':			'inwar', 
	'Inwar Darktide':			'inwar',
	'Akylios':					'akylios', 
	'Vladmal Prime':			'vladmal',

	'Duc Letareus':				'letareus', 
	'Infiltrateur Johlen':		'johlen',
	'Oracle Aleria':			'aleria', 
	'Prince Hylas':				'hylas', 
	'Seigneur Vertécaille':		'vertecailles', 

	'Maître de guerre Galenir':	'galenir', 
	'Héraut Gaurath':			'gaurath', 
	'Plutonus l\'Immortel': 	'plutonus',
	'Alsbeth la Discordante': 	'alsbeth', 
	'Balise ténébreuse': 		'balise_teneb', 

	'Commandant d\'assaut Jorb':'jorb', 
	'Joloral Ragemarée':		'joloral', 
	'Isskal':					'isskal',
	'Grande prêtresse Hydriss':	'hydriss',

	'Anrak l\'ignoble':			'anrak', 
	'Guurloth':					'guurloth', 
	'Thalguur':					'thalguur', 
	'Uruluuk':					'uruluuk', 

	'Ereandorn':				'ereandorn', 
	'Beruhast':					'beruhast', 
	'Général Silgen':			'silgen', 
	'Grand-prêtre Arakhurn':	'arkhurn',
}

skill_blacklist = [
	'Explosion fourchue',
	'Flammes mortelles',
]

# actors name blacklist. We dont want to see theses npc in the parses
mob_blacklist	= [
	'Concentration du Boss',
	'Bannière de zèle',
	'Prêtre capturé',
	'Bannière de rage',
	'Inconnu',
]

skills	= {0: 'Total'}
today 		= datetime.today()

class Encounter:

	types_actor	 = {
		'P':	'player',
		'N':	'npc',
		'O':	'other,'
	}
	
	def __init__(self, log, start_offset, end_offset, bosses = [], boss_killed=False):
		# lines to parse
		self.log 			= log
		# actors
		self.actors			= {}
		# just an holder to know if an actor in a player
		self.players		= {}
		# same but for npc
		self.npc			= {}
		self.end_time		= None
		# skill name cache
		self.skills			= skills
		# encounter start offset (used ?)
		self.start_offset	= start_offset
		self.end_offset		= end_offset

		# flag telling us if the encounter as already been parsed.
		self.parsed 		= False

		# encounter global data by skill, actor and deathlog.
		self.stats 			= {
			'skill':	{},
			'actor': 	{},
			'deathlog': [],
		}
		# encounter start time
		self.start_time		= self.log[0]['time']
		# encounter end time
		self.end_time		= self.log[len(self.log) - 1]['time']
		# current encounter boss list
		self.bosses 		= bosses
		# current encounter boss killed list
		self.boss_killed 	= boss_killed
		# death list (tmp, used to know if an actor was revived)
		self.deathes		= {}
		# rez done in this fight
		self.rez 			= []

	# the most simple structure, it holds every informations a hit or a heal require.
	def get_simple_struct(self):
		return {
			'hits':					0,
			'critical_hits':		0,
			'hits_count':			0,
			'critical_hits_count':	0,
			'heals':				0,
			'heals_count':			0,
			'critical_heals':		0,
			'critical_heals_count': 0,
			'max_hits': 			0,
			'max_heals':			0,
		}

	def get_detailed_struct(self, mask = None):
		return {
			'done': self.get_simple_struct(),
			'received': self.get_simple_struct(),
		}

	def get_timeline_structure(self):
		return {'done': {'heals': 0, 'hits': 0}, 'received': {'heals': 0, 'hits': 0}} 

	# calcul fight duration
	def get_duration(self):
		return (self.end_time - self.start_time).total_seconds()

	# serialize the current encounter, return a dict with every data necessary to build a full
	# detailled report.
	def serialize(self):
		return {
			'skills':		self.skills,
			'actors':		self.actors,
			'stats':		self.stats,
			'bosses':		self.bosses,
			'players':		self.players,
			'npc':			self.npc,
			'start_time':	self.start_time,
			'end_time':		self.end_time,
			'start_offset': self.start_offset,
			'end_offset':	self.end_offset,
			'bosses':		self.bosses,
			'boss_killed':	self.boss_killed,
			'rez':			self.rez,
			# removed cause it was too big to be stored that way.
			# we prefer to read it on live if needed (it shouldn't)
			#'log':		self.log,
		}

	def handle_heal(self, source, target, amount, skill_id, is_crit=False, over_heal=0):
		if not self.is_alive(target) and (self.line['time'] - self.deathes[target]).total_seconds() > 2:
			del self.deathes[target]
			self.rez.append({'source': source, 'target': target, 'skill': skill_id, 'time': self.line['time']})

	def handle_damage(self, source, target, amount, skill_id, is_crit=False, over_damages=0):
		# log this attack as the last attack. Used for the death log (death recap)
		self.stats['actor'][target]['last_attack'] = {
			'source':	source,
			'skill_id':	skill_id,
			'amount':	amount,
			'is_crit':	is_crit,
		}
		
	def get_actor_timeline(self, actor_id, time=None):
		if time is not None:
			tmp = self.get_actor_timeline(actor_id)
			if time not in tmp:
				tmp[time] = self.get_timeline_structure()
			return tmp[time]
		return self.stats['actor'][actor_id]['timeline']

	def update_actor_timeline(self, time, source, target, action_type, amount):
		self.get_actor_timeline(source, time)['done'][action_type]	 	+= amount
		self.get_actor_timeline(target, time)['received'][action_type] 	+= amount

	def get_total_skill(self, source, view):
		return self.stats['actor'][source][view]['skill']

	def get_total_for_skill(self, source, skill_id, view):
		tmp = self.get_total_skill(source, view)
		if skill_id not in tmp:
			tmp[skill_id] = self.get_simple_struct()
		return tmp[skill_id]

	def update_total_for_skill(self, source, action_type, skill_id, is_crit, amount, view='done'):
		tmp 				= self.get_total_for_skill(source, skill_id, view)

		self.update_simple_struct(tmp, action_type, amount, is_crit)

		if skill_id != 0:
			self.update_total_for_skill(source, action_type, 0, is_crit, amount, view)

	def get_actor_detail_for_actor_skill(self, source, target, view, type_action, skill_id):
		tmp = self.stats['actor'][source][view]['actor_skill']

		if target not in tmp:
			tmp[target] = {}

		if skill_id not in tmp[target]:
			tmp[target][skill_id] = self.get_simple_struct()

		return tmp[target][skill_id]

	def update_actor_detail_for_actor_skill(self, source, target, type_action, skill_id, amount, is_crit, inverse_view=False):
		if inverse_view:
			tmp = self.get_actor_detail_for_actor_skill(target, source, 'received', type_action, skill_id)
		else:
			self.update_actor_detail_for_actor_skill(source, target, type_action, skill_id, amount, is_crit, True)
			tmp = self.get_actor_detail_for_actor_skill(source, target, 'done', type_action, skill_id)

		self.update_simple_struct(tmp, type_action, amount, is_crit)
		
		if skill_id != 0:
			self.update_actor_detail_for_actor_skill(source, target, type_action, 0, amount, is_crit)

	def get_actor_global_stats(self, actor, view):
		return self.stats['actor'][actor]['global'][view]

	def update_actor_global_stats(self, source, target, action_type, amount, is_crit, inverse_view=False):
		if inverse_view:
			tmp = self.get_actor_global_stats(target, 'received')
		else:
			self.update_actor_global_stats(source, target, action_type, amount, is_crit, True)
			tmp = self.get_actor_global_stats(source, 'done')

		self.update_simple_struct(tmp, action_type, amount, is_crit)



	def get_actor_stats_for_actor(self, source, target, view):
		tmp = self.stats['actor'][source][view]
		if target not in tmp:
			tmp[target] = self.get_simple_struct()
		return tmp[target]

	def update_actor_stats_for_actor(self, source, target, action_type, amount, is_crit, inverse_view=False):
		if inverse_view:
			tmp = self.get_actor_stats_for_actor(target, source, 'received')
		else:
			self.update_actor_stats_for_actor(source, target, action_type, amount, is_crit, True)
			tmp = self.get_actor_stats_for_actor(source, target, 'done')

		self.update_simple_struct(tmp, action_type, amount, is_crit)

	def update_simple_struct(self, tmp, key, amount, is_crit):
		type_action = 'heals'
		if 'hits' in key:
			type_action = 'hits'

		if amount > tmp['max_' + type_action]:
			tmp['max_' + type_action] = amount

		tmp[key] 				+= amount
		tmp[key + '_count'] 	+= 1

		if is_crit:
			key = 'critical_' + key

			tmp[key] 				+= amount
			tmp[key + '_count'] 	+= 1


	def handle_damage_and_heal(self, action_type, source, target, amount, skill_id, is_crit):
		time = self.line['time']

		# does anything already happened at this $time in the timeline for the source (and then for the target)
		self.get_actor_timeline(source, time)
		self.get_actor_timeline(target, time)
		
		# add the value of this action in the timeline.
		self.update_actor_timeline(time, source, target, action_type, amount)

		# does this skill is already registered ? used to have a full report of what hits what and do 
		# stats on it.

		# get and update total stats per source, skill_id
		#gtfs 	= self.get_total_for_skill(source, skill_id)

		self.update_total_for_skill(source, action_type, skill_id, is_crit, amount)
		self.update_total_for_skill(target, action_type, skill_id, is_crit, amount, 'received')
		#self.update_total_for_skill(target, action_type, skill_id, is_crit, amount, 'received')

		# source, target, skill
		self.update_actor_detail_for_actor_skill(source, target, action_type, skill_id, amount, is_crit)

		self.update_actor_global_stats(source, target, action_type, amount, is_crit)

		self.update_actor_stats_for_actor(source, target, action_type, amount, is_crit)


	def get_buff(self, actor):
		return self.stats['actor'][actor]['buffes']

	def handle_buff(self, source, target, skill_id, type_buff, action_type):
		time = self.line['time']
		# see if the target is already in the list of the peoples who were affected by a buff/curse of the source.
		if target not in self.get_buff(source)['done'][type_buff]:
			self.get_buff(source)['done'][type_buff][target] 	= {}
		# same as ahead but inverse it. It allow us to know who did something to a specific actor.
		if source not in self.get_buff(target)['received'][type_buff]:
			self.get_buff(target)['received'][type_buff][source]= {}

		# does the target have already been affected by this skill from this source;
		if skill_id not in self.get_buff(source)['done'][type_buff][target]:
			self.get_buff(source)['done'][type_buff][target][skill_id] = []
		# same as ahead but inverse it.
		if skill_id not in self.get_buff(target)['received'][type_buff][source]:
			self.get_buff(target)['received'][type_buff][source][skill_id] = []

	
		def handle_buff(self, source, target, skill_id, type_buff, action_type, time, view):
		# track the buff/curse timeline (here for the source)
			tt = self.get_buff(source)[view][type_buff][target][skill_id]
			try:
				l_done 	= tt.pop(len(tt) - 1)
				no_last = False
			except:
				no_last = True
				l_done 	= []

			if action_type == 'up':
				if no_last is False:
					if len(l_done) < 2:
						l_done.append(time)
					tt.append(l_done)
				tt.append([time])
			else:
				if no_last is False:
					if len(l_done) < 2:
						l_done.append(time)
						tt.append(l_done)
					else:
						l_done = [l_done[0], time]
						tt.append(l_done)
				else:
					l_done.append([self.start_time, time])
		handle_buff(self, source, target, skill_id, type_buff, action_type, time, 'done')
		handle_buff(self, target, source, skill_id, type_buff, action_type, time, 'received')
			
	
	"""

		Handle a death.

		if it's a player kill, we add it to it's killboard,
		if it's a player death, we add it to the deathlog.


	"""
	def handle_death(self, actor, is_death=False, target=None):
		if is_death:
			if self.is_player(actor):
				
				# if the source is a player, we log this attack so we know what killed him
				if self.has_been_hit(actor):

					last_attack 		= self.get_last_attack(actor)
					last_attack['time']	= self.line['time']

					self.stats['actor'][actor]['killboard']['death'][self.line['time']] = last_attack
					
					
					# we add this death to the deathlog

					last_attack['target'] = actor
					self.stats['deathlog'].append(last_attack)

					# tmp data to know if the player has been revived, see below.
					self.deathes[actor] = self.line['time']
		else:
			# log when a player kill something.
			self.add_kill(actor, target, self.line['time'])
			
	def add_kill(self, actor_id, target_id, time):
		self.get_killboard(actor_id)['kill'].append({
			'time':			time, 
			'source':		actor_id,
			'target':		target_id,
		})

	def get_killboard(self, actor_id):
		return self.stats['actor'][actor_id]['killboard']

	def is_player(self, actor_id):
	 	return actor_id in self.players
	  
	def is_alive(self, actor_id):
	 	return actor_id not in self.deathes

	def has_been_hit(self, actor_id):
	 	return 'source' in self.stats['actor'][actor_id]['last_attack']

	def get_actor(self, actor_id):
	 	return self.actors[actor_id]

	def get_last_attack(self, actor_id):
	 	return self.stats['actor'][actor_id]['last_attack']

	def parse(self):
		for line in self.log:
			if self.parsed is True:
				break


			self.line 	 = line

			source 		= line['source_id']
			target 		= line['target_id']
			skill_id	= line['skill_id']
			time 		= line['time']

			if self.skills[skill_id] in skill_blacklist:
				continue


			if source not in self.actors:
				self.create_actor(line, 'source')

			if target not in self.actors:
				self.create_actor(line, 'target')

			if line['action_name'] in ('DIED', 'SLAIN'):
				self.handle_death(source, line['action_name'] is 'DIED', target)

				
			# is the action related to the buffes and curses.
			if line['action_name'] in ('GAINS', 'AFFLICTED', 'FADES', 'DISSIPATES'):

				# detect if it's a curse or a buff
				type_buff 	= 'debuff'
				if line['action_name'] in ('GAINS', 'FADES'):
					type_buff 	= 'buff'
				
				# detect if it's a start effect or an end effect.
				action_type 	= 'down'
				if line['action_name'] in ('GAINS', 'AFFLICTED'):
					action_type 	= 'up'

				self.handle_buff(source, target, skill_id, type_buff, action_type)

			# is this a heal or a hit ?
			if line['action_name'] in ('SUFFERS', 'HITS', 'CRITICALLY_HITS', 'HEALS', 'CRITICALLY_HEALS'):
				amount 	= line['amount']

				is_crit = line['action_name'][0:10] == 'CRITICALLY'

				if line['action_name'] in ('HITS', 'CRITICALLY_HITS', 'SUFFERS'):

					self.handle_damage(source, target, amount, skill_id, is_crit)
					a = 'hits'
				else:
					self.handle_heal(source, target, amount, skill_id, is_crit)
					a = 'heals'

				type_action = a
				self.handle_damage_and_heal(type_action, source, target, amount, skill_id, is_crit)

				
		
		self.parsed = True

	# used to give the full structure of an actor (stored in self.actors)
	# with this, we are able to know everything of an actor for the current fight.
	def create_actor(self, line, s):
		actor = {
			'id':	line['%s_id' % s],

			'name':	line['%s_name' % s],

			'type': self.types_actor.get(line['%s_primary_type' % s], 'other'),

			'registration': line['%s_registration' % s],
		}

		self.actors[actor['id']] = actor

		if actor['type'] == 'player':
			self.players[actor['id']] = actor
		else:
			self.npc[actor['id']] = actor

		self.stats['actor'][actor['id']] = {
			'global': 		self.get_detailed_struct(),
			'done':			{
				'skill':	{},
				'actor':	{},
				'actor_skill': {},
			},
			'received':		{
				'skill':	{},
				'actor':	{},
				'actor_skill': {},
			},
			'buffes': {
				'done':	{
					'buff': {},
					'debuff': {},
				},
				'received':	{
					'buff': {},
					'debuff': {},
				},
			},
			'killboard': {
				'kill':	[],
				'death': {}
			},
			'last_attack': {},
			'timeline': {},
		}

class Parser:

	actions	= {
		1:	'START_CASTING',
		2:	'INTERRUPTED',
		3:	'HITS',
		4:	'SUFFERS',
		5:	'HEALS',
		6:	'GAINS',
		7:	'FADES',
		8:	'AFFLICTED',
		9:	'DISSIPATES',
		10:	'MISSES',
		11:	'SLAIN',
		12:	'DIED',
		13:	'???',
		14:	'FALLING_DAMAGES',
		15:	'DODGES',
		16:	'PARRIES',
		17:	'???',
		18:	'???',
		19:	'RESISTS',
		20:	'??',
		21:	'??',
		22:	'REDIRECTS',
		23:	'CRITICALLY_HITS',
		24:	'FAVOR',
		25:	'??',
		26:	'IMMUNE',
		27:	'GIVES',
		28:	'CRITICALLY_HEALS',
	}
	
	def __init__(self, filename, first_byte=0, last_byte=None, log_id=None):
		# combat status defined in the combat log
		self.combat_status 		= False
		# combat log calculed from the last attack time and the combat_status
		self.in_combat 			= False

		# buffer of lines, is it useful ? i dont think so right now.
		# todo : clean this up
		self.lines_buffer 		= []
		# last attack time
		self.last_attack 		= None
		# number of line that have been read
		self.line_count 		= 0
		# current day (start at 0, and increase if the log have encounters on different days.)
		self.day				= 0
		# last action time
		self.last_otime 		= None
		# encounter counter
		self.encounter_count	= 0
		# list of encounters
		self.encounters			= []
		# start time of the current encounter
		self.start_time 		= None
		# combat lof filename (and path)
		self.filename 			= filename
		# offset at wich we should start parsing the file
		self.start_offset		= 0
		# current encounter boss
		self.boss 				= None
		# current encounter boss killed list
		self.boss_killed		= None
		# current encounter KIA players list
		self.kia 				= []
		# first byte we should parse
		self.first_byte			= first_byte
		# last byte we should parse
		if last_byte is not None:
			self.last_byte 		= last_byte
		else:
			self.last_byte		= None
		# if the log_id is defined, we can save the encounters and link them to the given Log object.
		self.log_id				= log_id
		self.actors 			= []

	def handle_file(self):
		try:
			f = open(settings.MEDIA_ROOT + '/combat_logs/%d/CombatLog.txt' % self.log_id, 'r')
			f.close()
		except Exception as e:
			z = ZipFile(self.filename, 'r')
			try:
				e = z.extract('CombatLog.txt', settings.MEDIA_ROOT + '/combat_logs/%d' % self.log_id)
			except KeyError:
				return False
		return True


	"""
		Parse the file.
		this method can either read the whole file or just a chunk, this feature is defined by the start_offset
		object property which is telling if we have to jump to the fight we want or not.
	"""
	def parse(self, full=False):


		if not self.handle_file():
			return False
		self.file 		= file(settings.MEDIA_ROOT + '/combat_logs/%d/CombatLog.txt' % self.log_id, 'r', 1024)
		#self.file 		= file(self.filename, 'r')

		# seek to the fight we want
		if self.first_byte > 0:
			self.file.seek(self.first_byte)

		while True:
			self.curr_offset = self.file.tell()
			# stop if we read the whole interesting data (an enouncter starts and ends at specifics offsets)
			if self.last_byte is not None and self.curr_offset >= self.last_byte:
				break
			line = self.file.readline()

			# does the line is fully blank ?
			# if yes, it means we're at the end of the file. (it wont happen if there is a \n at the end of the line)
			if len(line) == 0:
				break
			# if the striped line is blank, we pass this line.
			line 	= line.strip()
			if len(line) == 0:
				continue
			
			# count read lines.
			self.line_count += 1
			# parse line.
			parsed 	= self.parse_line(line, full)
		
		# if we're at the end of an encounter, let's do the saving and cleaning.
		if not self.combat_status and self.in_combat and self.last_attack is not None:


			if len(self.lines_buffer) > 0:

				self.in_combat 			= False

				# is this a worth of logging fight ? (more than 60 seconds.)
				if (self.last_otime - self.start_time).total_seconds() > 60:
					if self.boss is not None:
						self.save_encounter(full)
		print self.boss, (self.last_otime - self.start_time).total_seconds(), self.get_encounters()
		return True

	def get_encounters(self):
		return self.encounters

	def parse_line(self, line, full):

		# handle the log time
		logtime 	= line[0:8]
		try:
			otime		= datetime.strptime(logtime, '%H:%M:%S') + timedelta(days=self.day)
		except:
			raise

		# did we change day while fighting ?
		if self.last_otime is not None and otime.time() < self.last_otime.time():
			self.day+= 1
			otime += timedelta(days=1)

		self.last_otime = otime

		# split the line to detect format
		try:
			index = line.index('(')
		except:
			# detect the "Combat End" line telling us the client which logged this is now out of combat
			if line.split(" ")[2].lower() == "end":
				self.combat_status 		= False
			# same but for the combat start.
			else:
				self.combat_status 		= True
			# we don't have anything to parse after that.
			return

		rindex 	= line.index(')')


		data 	= line[index + 2:rindex]
		# striping elements to have "good" data to read.
		d 		= [x.strip() for x in data.split(",")]

		# a bad named npc with a , or a (, ) in is name ?
		if len(d) < 10:
			rindex1	= line.index(')', rindex + 1)
			rindex 	= line.index(')', rindex1 + 1)
			data 	= line[index + 2:rindex]
			# striping elements to have "good" data to read.
			d 		= [x.strip() for x in data.split(",")]
			

		action 		= int(d[0])
		action_name = self.actions[action]
		source_full = d[1]
		target_full = d[2]
		source_type = d[3]
		target_type = d[4]
		source_name = d[5]
		try:
			target_name = d[6]
		except:
			raise
		# some actor's name contain some unescaped chars such as "," which is used to split elements on the log line.
		try:
			amount 		= int(d[7])
			skill_id	= int(d[8])
			skill_name 	= d[9]
		except:
			target_name = ','.join([d[6], d[7]])
			amount 		= int(d[8])
			skill_id	= int(d[9])
			skill_name 	= d[10]

		source_type_= source_full.split('#')
		# player, npc ou other ?
		source_primary_type = source_type_[0][-1]
		# groupe, raid, or something else ?
		source_registration = source_type_[1][-1]
		source_id 			= source_type_[2]

		target_type_= target_full.split('#')
		target_primary_type = target_type_[0][-1]
		target_registration = target_type_[1][-1]
		target_id 			= target_type_[2]

		is_attack 	= action in (3,23)
		is_heal 	= action in (5,28)
		is_death 	= action in (11,12)

		line_data 	= {
			'action':		action,
			'action_name':	action_name,
			'source_full':	source_full,
			'source_name':	source_name,
			'target_full':	target_full,
			'source_type':	source_type,
			'target_type':	target_type,
			'target_name':	target_name,
			'amount':		amount,
			'skill_id':		skill_id,
			'skill_name':	skill_name,
			'is_attack':	is_attack,
			'is_heal':		is_heal,
			'is_death':		is_death,
			'raw':			line,
			'time':			otime,
			'source_id': 	source_id,
			'source_primary_type': source_primary_type,
			'source_registration': source_registration,
			'target_id':	target_id,
			'target_primary_type': target_primary_type,
			'target_registration': target_registration
		}

		if line_data['source_name'] not in self.actors:
			self.actors.append(line_data['source_name'])
		if line_data['target_name'] not in self.actors:
			self.actors.append(line_data['target_name'])

		# detect the bosses killed in the fight.
		if line_data['action'] == 11:
			# the actor who's dead was a boss ? It's important to detect wether or not the raid wiped on the boss.
			if line_data['target_name'] in bosses_list:
				self.boss_killed = bosses_list[line_data['target_name']]
			# if the actor who's dead is a player, add him to the KIA list.
			if line_data['target_name'] not in self.kia and line_data['target_primary_type'] == 'P':
				self.kia.append(line_data['target_name'])

		# detect players killed in the encounter.
		if line_data['action'] == 12 and line_data['source_primary_type'] == 'P':
			if line_data['source_name'] not in self.kia:
				self.kia.append(line_data['source_name'])

		# skill name cache
		if line_data['skill_id'] not in skills:
			skills[line_data['skill_id']] = line_data['skill_name']

		# first attack and we're not yet in combat ? Well, now we are.
		if not self.in_combat and is_attack:
			self.in_combat			= True
			self.start_offset 		= self.curr_offset
			self.start_time			= otime

		# detect the current encounter boss from target and source.
		if self.boss is None and line_data['target_name'] in bosses_list:
			self.boss = bosses_list[line_data['target_name']]
		if self.boss is None and line_data['source_name'] in bosses_list:
			self.boss = bosses_list[line_data['source_name']]

		if not self.combat_status and self.in_combat and self.last_attack is not None:

			if (otime - self.last_attack).total_seconds() > 15:

				self.in_combat 			= False

				# is this a worth of logging fight ? (more than 60 seconds.)
				if (otime - self.start_time).total_seconds() > 60:
					if self.boss is not None:
						self.save_encounter(full)

				# flush the buffers and reset the tmp data.
				self.lines_buffer 		= []
				self.boss 				= None
				self.boss_killed 		= None
				self.kia 				= []
		
		if is_attack:
			self.last_attack = otime

		if self.in_combat:
			self.lines_buffer.append(line_data)

	def save_encounter(self, full):
		self.encounter_count 	+= 1
		enc 					= Encounter(self.lines_buffer, self.start_offset, self.curr_offset, self.boss, self.boss_killed is not None)

		data 					= enc.serialize()
	
		if full:
			enc.parse()
		self.actors = []

		# the parse is one to save the data of the fight in the encounter datastore.
		if not full:

			l 						= logparse.models.Log.objects.get(id=self.log_id)
			encounter 				= logparse.models.Encounter(log=l)

			encounter.start_offset	= enc.start_offset
			encounter.end_offset 	= enc.end_offset

			# we try to load the boss from the database
			try:
				encounter.boss 			= logparse.models.Boss.objects.get(name=enc.bosses)
			# if this boss isn't in the database, we create it
			except:
				b = logparse.models.Boss(name=enc.bosses)
				b.save()
				encounter.boss = b
			
			# did the raid kill the boss ?
			encounter.wipe = not enc.boss_killed
			encounter.save()
			encounter.parse()
			stats = encounter.stats()
			if stats is not None:
				stats.parse()
				stats.create_actors()
			else:
				print "!!!", encounter, encounter.id
				#stats.delete()
				#encounter.delete()
				pass

			# memory efficiency fix.
			del enc, encounter

		else:

			self.encounters.append(enc)
