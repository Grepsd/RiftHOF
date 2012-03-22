# -*- coding: utf-8 -*-
from datetime import datetime, timedelta
import sys, os
import pickle, bz2
import re
import time
import logparse.models

bosses_list 	= [
	'Murdantix', 
	'Étripeur d\'âmes Zilas', 
	'Grugonim', 
	'Roi runique Molinar', 
	'Estrode',
	'Matrone Zamira', 
	'Sicaron', 
	'Inquisiteur Garau', 
	'Inwar Noirflux', 
	'Akylios', 

	'Duc Letareus', 
	'Infiltrateur Johlen',
	'Oracle Aleria', 
	'Prince Hylas', 
	'Seigneur Vertécaille', 

	'Maître de guerre Galenir', 
	'Héraut Gaurath', 'Plutonus l\'Immortel',
	'Alsbeth la Discordante', 
	'Balise ténébreuse', 

	'Commandant d\'assaut Jorb', 
	'Joloral Ragemarée', 
	'Isskal', 
	'Grande prêtresse Hydriss',

	'Anrak l\'ignoble', 
	'Guurloth', 
	'Thalguur', 
	'Uruluuk', 

	'Ereandorn', 
	'Beruhast', 
	'Général Silgen', 
	'Grand-prêtre Arakhurn'
]

mob_blacklist	= [
	'Concentration du Boss',
	'Bannière de zèle',
	'Prêtre capturé',
	'Bannière de rage',
	'Inconnu',
]

skills	= {}
today 		= datetime.today()

class Encounter:

	types_actor	 = {
		'P':	'player',
		'N':	'npc',
		'O':	'other,'
	}
	
	def __init__(self, log, start_offset, end_offset, bosses = [], boss_killed=False):
		self.log 			= log
		self.actors			= {}
		self.players		= {}
		self.npc			= {}
		self.start_time		= None
		self.end_time		= None
		self.skills			= skills
		self.start_offset	= start_offset
		self.end_offset		= end_offset
		self.stats 			= {
			'skill':	{},
			'actor': 	{},
			'deathlog': [],
		}
		self.start_time		= self.log[0]['time']
		self.end_time		= self.log[len(self.log) - 1]['time']
		self.bosses 		= bosses
		self.boss_killed 	= boss_killed
		self.deathes		= {}
		self.rez 			= []

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
		}

	def get_detailed_struct(self, mask = None):
		return {
			'done': self.get_simple_struct(),
			'received': self.get_simple_struct(),
		}

	def get_duration(self):
		return (self.end_time - self.start_time).total_seconds()

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
			#'log':		self.log,
		}

	def parse(self):
		l = 0
		for line in self.log:
			l += 1
			if l == 1:
				if len(self.actors) > 3:
					break
			source 	= line['source_id']
			target 	= line['target_id']
			skill_id= line['skill_id']
			time 	= line['time']


			if source not in self.actors:
				self.create_actor(line, 'source')

			if target not in self.actors:
				self.create_actor(line, 'target')


			if line['action_name'] in ('DIED', 'SLAIN'):

				if line['action_name'] is 'DIED':

					if source in self.players:

						if 'source' in self.stats['actor'][source]['last_attack']:
							self.stats['actor'][source]['killboard']['death'][line['time']] = {
								'source':	self.stats['actor'][source]['last_attack']['source'],
								'skill_id':	self.stats['actor'][source]['last_attack']['skill_id'],
								'amount':	self.stats['actor'][source]['last_attack']['amount'],
								'is_crit':	self.stats['actor'][source]['last_attack']['is_crit'],
								'time':		line['time'],
							}

							self.stats['deathlog'].append({
								'source':	self.stats['actor'][source]['last_attack']['source'],
								'skill_id':	self.stats['actor'][source]['last_attack']['skill_id'],
								'amount':	self.stats['actor'][source]['last_attack']['amount'],
								'is_crit':	self.stats['actor'][source]['last_attack']['is_crit'],
								'target':  	source,
								'time':		line['time'],
							})
							self.deathes[source] = time
				else:
					self.stats['actor'][source]['killboard']['kill'].append({
						'time':			line['time'], 
						'source':		source,
						'target':		target,
					})
				
			if line['action_name'] in ('GAINS', 'SUFFERS', 'AFFLICTED', 'FADES'):


				if line['action_name'] in ('GAINS', 'FADES'):
					type_buff 	= 'buff'
				else:
					type_buff 	= 'debuff'
				
				if line['action_name'] in ('GAINS', 'AFFLICTED'):
					action_type 	= 'up'
				else:
					action_type 	= 'down'
				
				if target not in self.stats['actor'][source]['buffes']['done'][type_buff]:
					self.stats['actor'][source]['buffes']['done'][type_buff][target] 	= {}
				if source not in self.stats['actor'][target]['buffes']['received'][type_buff]:
					self.stats['actor'][target]['buffes']['received'][type_buff][source]= {}

				if skill_id not in self.stats['actor'][source]['buffes']['done'][type_buff][target]:
					self.stats['actor'][source]['buffes']['done'][type_buff][target][skill_id] = []
				if skill_id not in self.stats['actor'][target]['buffes']['received'][type_buff][source]:
					self.stats['actor'][target]['buffes']['received'][type_buff][source][skill_id] = []

			
				tt = self.stats['actor'][source]['buffes']['done'][type_buff][target][skill_id]
				try:
					l_done 	= tt.pop(len(tt) - 1)
					no_last = False
				except:
					no_last = True
					l_done 	= []

				if action_type == 'up':
					if no_last is False:
						if len(l_done) < 2:
							l_done.append(line['time'])
						tt.append(l_done)
					tt.append([line['time']])
				else:
					if no_last is False:
						if len(l_done) < 2:
							l_done.append(line['time'])
							tt.append(l_done)
						else:
							l_done = [l_done[0], line['time']]
							tt.append(l_done)
					else:
						l_done.append([self.start_time, line['time']])

				tt = self.stats['actor'][target]['buffes']['received'][type_buff][source][skill_id]
				try:
					l_done 	= tt.pop(len(tt) - 1)
					no_last = False
				except:
					no_last = True
					l_done 	= []

				if action_type == 'up':
					if no_last is False:
						if len(l_done) < 2:
							l_done.append(line['time'])
						tt.append(l_done)
					tt.append([line['time']])
				else:
					if no_last is False:
						if len(l_done) < 2:
							l_done.append(line['time'])
							tt.append(l_done)
						else:
							l_done = [l_done[0], line['time']]
							tt.append(l_done)
					else:
						l_done.append([self.start_time, line['time']])

			if line['action_name'] in ('SUFFERS', 'HITS', 'CRITICALLY_HITS', 'HEALS', 'CRITICALLY_HEALS'):
				amount 	= line['amount']
				if line['action_name'] in ('HITS', 'CRITICALLY_HITS', 'SUFFERS'):
					a = 'hits'
					self.stats['actor'][target]['last_attack'] = {
						'source':	source,
						'skill_id':	skill_id,
						'amount':	amount,
						'is_crit':	line['action_name'] is 'CRITICALLY_HITS',
					}
				else:
					a = 'heals'
					if target in self.deathes and (time - self.deathes[target]).total_seconds() > 2:
						del self.deathes[target]
						self.rez.append({'source': source, 'target': target, 'skill': skill_id, 'time': time})

				
				if time not in self.stats['actor'][source]['timeline']:
					self.stats['actor'][source]['timeline'][time] = {'done': {'heals': 0, 'hits': 0}, 'received': {'heals': 0, 'hits': 0}}
				if time not in self.stats['actor'][target]['timeline']:
					self.stats['actor'][target]['timeline'][time] = {'done': {'heals': 0, 'hits': 0}, 'received': {'heals': 0, 'hits': 0}}
				
				self.stats['actor'][source]['timeline'][time]['done'][a] += amount
				self.stats['actor'][target]['timeline'][time]['received'][a] += amount

				if skill_id not in self.stats['actor'][source]['done']['skill'][a]:
					self.stats['actor'][source]['done']['skill'][a][skill_id] = 0

				self.stats['actor'][source]['done']['skill'][a][skill_id] += amount

				if skill_id not in self.stats['actor'][target]['received']['skill'][a]:
					self.stats['actor'][target]['received']['skill'][a][skill_id] = 0

				self.stats['actor'][target]['received']['skill'][a][skill_id] += amount

				self.stats['actor'][target]['global']['received'][a] 				+= amount
				self.stats['actor'][target]['global']['received']['%s_count' % a] 	+= 1
				if line['action_name'] == 'CRITICALLY_HITS':
					self.stats['actor'][target]['global']['received']['critical_%s' % a] 		+= amount
					self.stats['actor'][target]['global']['received']['critical_%s_count' % a] 	+= 1

				self.stats['actor'][source]['global']['done'][a] 				+= amount
				self.stats['actor'][source]['global']['done']['%s_count' % a] 	+= 1
				if line['action_name'] == 'CRITICALLY_HITS':
					self.stats['actor'][source]['global']['done']['critical_%s' % a] 		+= amount
					self.stats['actor'][source]['global']['done']['critical_%s_count' % a] 	+= 1

				if source not in self.stats['actor'][target]['received']['actor']:
					self.stats['actor'][target]['received']['actor'][source] = self.get_simple_struct()
				self.stats['actor'][target]['received']['actor'][source][a] 				+= amount
				self.stats['actor'][target]['received']['actor'][source]['%s_count' % a] 	+= 1
				if line['action_name'] == 'CRITICALLY_HITS':
					self.stats['actor'][target]['received']['actor'][source]['critical_%s' % a] 		+= amount
					self.stats['actor'][target]['received']['actor'][source]['critical_%s_count' % a] 	+= 1

				if target not in self.stats['actor'][source]['done']['actor']:
					self.stats['actor'][source]['done']['actor'][target] = self.get_simple_struct()
				self.stats['actor'][source]['done']['actor'][target][a] 				+= amount
				self.stats['actor'][source]['done']['actor'][target]['%s_count' % a] 	+= 1
				if line['action_name'] == 'CRITICALLY_HITS':
					self.stats['actor'][source]['done']['actor'][target]['critical_%s' % a] 		+= amount
					self.stats['actor'][source]['done']['actor'][target]['critical_%s_count' % a] 	+= 1
				

		#print sorted([x['name'] for x in self.players.values()])
		#print [x['name'] for x in self.npc.values()]
		"""
		t = {}
		for a, s in self.stats['actor'].items():
			if a in self.players:
				for actor_buff, buffes in self.stats['actor'][a]['buffes']['received']['buff'].items():
					if actor_buff != a:
						continue
					
					for skill_id, ups in buffes.items():
						total_up = 0
						occurence = 0
						for u in ups:
							if len(u) == 0:
								continue
							if len(u) < 2:
								u.append(self.end_time)
							occurence += 1
							total_up += (u[1] - u[0]).total_seconds()
						print "%d%% (%ds) (%d times) for %s by %s on %s" % (total_up / self.get_duration() * 100, total_up, occurence, self.skills[skill_id], self.actors[actor_buff]['name'], self.actors[a]['name'])
				if s['global']['done']['hits'] not in t:
					t[s['global']['done']['hits']] = []
				t[s['global']['done']['hits']].append(self.actors[a]['name'])
		k = t.keys()
		k = sorted(k, reverse=True)

		for death in self.stats['deathlog']:
			print "%s %s was killed by %s [%s recus de %s]" % (death['time'].time(), self.actors[death['target']]['name'], self.actors[death['source']]['name'], death['amount'], self.skills[death['skill_id']])

		total = 0
		for a in k:
			total += a
			print "%d : %s" % (a / self.get_duration(), (", ".join(t[a])))
		print "Total : %d / %ds" % (total / self.get_duration(), self.get_duration())
		"""

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
				'skill':	{'heals': {}, 'hits': {}},
				'actor':	{},
			},
			'received':		{
				'skill':	{'heals': {}, 'hits': {}},
				'actor':	{},
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
		self.combat_status 		= False
		self.in_combat 			= False
		self.lines_buffer 		= []
		self.last_attack 		= None
		self.line_count 		= 0
		self.day				= 0
		self.last_otime 		= None
		self.encounter_count	= 0
		self.encounters			= []
		self.start_time 		= None
		"""self.path				= path
		self.parse_name 		= name"""
		self.filename 			= filename
		self.start_offset		= 0
		self.boss 				= None
		self.boss_killed		= None
		self.kia 				= []
		self.first_byte			= first_byte
		if last_byte is not None:
			self.last_byte 		= last_byte
		else:
			self.last_byte		= None
		self.log_id				= log_id

	def parse(self, full=False):
		self.file 		= file(self.filename, 'r', 1024)
		if self.first_byte > 0:
			self.file.seek(self.first_byte)
		while True:
			self.curr_offset = self.file.tell()
			if self.last_byte is not None and self.curr_offset >= self.last_byte:
				break
			line = self.file.readline()
			if len(line) == 0:
				break
			line 	= line.strip()
			if len(line) == 0:
				continue
			self.line_count += 1
			parsed 	= self.parse_line(line, full)
		if self.last_byte is not None and self.start_time is not None:
			if (self.last_otime - self.start_time).total_seconds() > 60:
				self.encounter_count 	+= 1
				enc 					= Encounter(self.lines_buffer, self.start_offset, self.curr_offset, self.boss, self.boss_killed is not None)
				#enc.parse()
				data 					= enc.serialize()
				
				if data['bosses'] is not None:
					if full:
						enc.parse()
						#data = enc.serialize()
						#if 'Alsbeth la Discordante' != self.boss or ('Alsbeth la Discordante' == self.boss and len(data['players']) > 5):
						#c_data 					= str(pickle.dumps(data))

					self.encounters.append(enc)

	def get_encounters(self):
		return self.encounters

	def parse_line(self, line, full):

		logtime 	= line[0:8]
		try:
			otime		= datetime.strptime(logtime, '%H:%M:%S') + timedelta(days=self.day)
		except:
			print line
			print self.file.tell()
			raise

		if self.last_otime is not None and otime.time() < self.last_otime.time():
			self.day+= 1
			otime += timedelta(days=1)

		self.last_otime = otime

		try:
			index = line.index('(')
		except:
			if line.split(" ")[2].lower() == "end":
				self.combat_status 		= False
			else:
				self.combat_status 		= True
			return

		rindex 	= line.index(')')

		data 	= line[index + 2:rindex]
		d 		= [x.strip() for x in data.split(",")]

		action 		= int(d[0])
		action_name = self.actions[action]
		source_full = d[1]
		target_full = d[2]
		source_type = d[3]
		target_type = d[4]
		source_name = d[5]
		target_name = d[6]
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
		source_primary_type = source_type_[0][-1]
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
		if line_data['action'] == 11:
			if line_data['target_name'] in bosses_list:
				self.boss_killed = line_data['target_name']
			if line_data['target_name'] not in self.kia and line_data['target_primary_type'] == 'P':
				self.kia.append(line_data['target_name'])
		if line_data['action'] == 12 and line_data['source_primary_type'] == 'P':
			if line_data['source_name'] not in self.kia:
				self.kia.append(line_data['source_name'])

		if line_data['skill_id'] not in skills:
			skills[line_data['skill_id']] = line_data['skill_name']

		if not self.in_combat and is_attack:
			self.in_combat			= True
			self.start_offset 		= self.curr_offset
			self.start_time			= otime
		if self.boss is None and line_data['target_name'] in bosses_list:
			self.boss = line_data['target_name']
		if self.boss is None and line_data['source_name'] in bosses_list:
			self.boss = line_data['source_name']

		if not self.combat_status and self.in_combat and self.last_attack is not None:
			if (otime - self.last_attack).total_seconds() > 10:
				if len(self.lines_buffer) > 0:
					self.in_combat 			= False
					if (otime - self.start_time).total_seconds() > 60:
						self.encounter_count 	+= 1
						enc 					= Encounter(self.lines_buffer, self.start_offset, self.curr_offset, self.boss, self.boss_killed is not None)
						#enc.parse()
						data 					= enc.serialize()
						
						if data['bosses'] is not None:
							if full:
								enc.parse()
								"""
	log = Log.objects.get(id=id)
	if not log.processed:
		parser = Parser(settings.BASEPATH + '/content' + log.log_file.url)
		parser.parse(False)
		for encounter in parser.get_encounters():
	log.process = True
	log.processing_date = datetime.now()
	log.save()"""
							#data = enc.serialize()
							#if len(data['players']) > 5:
								#c_data 					= str(pickle.dumps(data))

							if self.log_id is not None:
								l 						= logparse.models.Log.objects.get(id=self.log_id)
								encounter 				= logparse.models.Encounter(log=l)
								encounter.start_offset	= enc.start_offset
								encounter.end_offset 	= enc.end_offset
								try:
									encounter.boss 			= logparse.models.Boss.objects.get(name=enc.bosses)
								except:
									b = logparse.models.Boss(name=enc.bosses)
									b.save()
									encounter.boss = b
								encounter.wipe = not enc.boss_killed
								encounter.save()
								del enc, encounter
							else:
								self.encounters.append(enc)

					self.lines_buffer 		= []
					self.boss 				= None
					self.boss_killed 		= None
					self.kia 				= []
		
		if is_attack:
			self.last_attack = otime

		if not self.in_combat and is_attack:
			self.in_combat		= True

		if self.in_combat:
			self.lines_buffer.append(line_data)

#path = '/tmp/rift_heliasae_parser/'
"""
path = sys.argv[2]
name = sys.argv[3]
try:
	os.stat(path)
except OSError:
	os.makedirs(path)
parser = Parser(sys.argv[1])
parser.parse()"""