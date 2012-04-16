# -*- coding: utf-8 -*-
from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.forms import ModelForm
from parser import Parser, mob_blacklist, skill_to_class, classes
from django.conf import settings
import pickle
from django.core.cache import cache
from copy import copy, deepcopy


zones 	= (
	('US', 'USA'),
	('EU', 'Europe'),
)
class Zone(models.Model):
	name 				= models.CharField(max_length=200, choices=zones)

	def __unicode__(self):
		return self.name

	def shards(self):
		return Shard.objects.filter(zone=self)

class Shard(models.Model):
	name				= models.CharField(max_length=200)
	zone 				= models.ForeignKey(Zone)

	def __unicode__(self):
		return self.name

factions 	= (
	('D', 'Defiant'),
	('G', 'Guardian'),
)

class Guild(models.Model):
	name 				= models.CharField(max_length=200)
	shard 				= models.ForeignKey(Shard)
	default_log_private = models.BooleanField(default=False)
	faction 			= models.CharField(max_length=100, choices=factions)

	def __unicode__(self):
		return self.name

	def logs(self):
		return Log.objects.filter(guild=self)

	def members(self):
		final = []
		for profile in UserProfile.objects.filter(guild=self):
			final.append(profile.user)
		return final

class Character(models.Model):
	name 				= models.CharField(max_length=200)
	shard 				= models.ForeignKey(Shard)
	guild 				= models.ForeignKey(Guild)
	faction 			= models.CharField(max_length=200, choices=factions)

	def __unicode__(self):
		return self.name

class UserProfile(models.Model):
	user 				= models.OneToOneField(User)
	guild 				= models.ForeignKey(Guild, null=True, blank=True)
	characters			= models.ManyToManyField(Character, null=True, blank=True)

	def __unicode__(self):
		return self.user.username

	def has_guild(self):
		return self.guild is not None

	def leave_guild(self):
		self.guild = None
		self.save()



class Raid(models.Model):
	name 				= models.CharField(max_length=200)

	def __unicode__(self):
		return self.name
	
class Boss(models.Model):
	name 				= models.CharField(max_length=200)
	raid 				= models.ForeignKey(Raid, null=True, blank=True)
	order 				= models.IntegerField(default=0)

	def __unicode__(self):
		return "%s of %s" % (self.name, self.raid)

class Log(models.Model):
	guild 				= models.ForeignKey(Guild)
	log_file 			= models.FileField(upload_to='combat_logs')
	upload_date			= models.DateTimeField(auto_now=True)
	processing_date 	= models.DateTimeField(null=True, blank=True)
	processed 			= models.BooleanField(default=False)
	private 			= models.BooleanField(default=False)
	user 				= models.ForeignKey(User)
	processing 			= models.BooleanField(default=False)
	start_processing_time= models.DateTimeField(null=True, blank=True)
	end_processing_time =  models.DateTimeField(null=True, blank=True)

	def reset(self):
		self.processed = False
		self.processing= False
		self.save()

	def day(self):
		return self.upload_date.date()

	def __unicode__(self):
		return "%d parse %s" % (self.id, self.guild)

	def encounters(self):
		return Encounter.objects.filter(log=self).order_by('id')

	def parse(self):
		if not self.processed and not self.processing:
			[x.delete() for x in self.encounters()]
			self.processing = True
			self.save()
			parser = Parser(settings.BASEPATH + '/content' + self.log_file.url, log_id=self.id)
			if not parser.parse(False):
				self.processed = False
			else:
				self.processed = True
			self.processing = False
			self.save()
		return self.processed

class Encounter(models.Model):
	boss 				= models.ForeignKey(Boss, blank=True, null=True)
	log 				= models.ForeignKey(Log)
	start_offset		= models.IntegerField(default=0)
	end_offset			= models.IntegerField(null=False)
	private 			= models.BooleanField(default=False)
	wipe 				= models.BooleanField(default=False)
	parsed 				= models.BooleanField(default=False)
	processing 			= models.BooleanField(default=False)

	cache 				= None

	stats_cache			= None

	def __unicode__(self):
		return "%d against %s" % (self.id, u'%s' % self.boss)

	def process_for_display(self):
		create_actors 	= False
		if not self.parsed:
			self.parse()
			create_actors= True

		stats = self.stats()
		try:
			stats.parse()
		except:
			self.parse()
			stats = self.stats()
			stats.parse()

		if create_actors:
			stats.create_actors()
		
		self.stats_cache = stats

	def parse(self):
		if not self.parsed:
			parser 		= Parser(settings.BASEPATH + '/content' + self.log.log_file.url, self.start_offset, self.end_offset, log_id=self.log.id)
			parser.parse(full=True)
			encounters= parser.get_encounters()
			try:
				encounter = encounters[0]
			except IndexError:
				self.delete()
				return False
			encounter.parse()
			self.cache 	= pickle.dumps(encounter.serialize())
			try:
				enc = EncounterStats.objects.get(encounter=self)
				if len(enc.data) == 0:
					enc.data = self.cache
					enc.save()
			except:
				enc = EncounterStats(encounter=self, data=self.cache)
				enc.save()
			self.parsed = True
			self.save()

	def stats(self):
		if self.stats_cache is not None:
			return self.stats_cache
		try:
			return EncounterStats.objects.get(encounter=self)
		except:
			e = EncounterStats(encounter=self)
			if self.cache is not None:
				e.data = self.cache
			try:
				e.save()
				return e
			except Exception as e:
				pass

	def reset(self):
		self.parsed = False
		self.save()
		try:
			s = EncounterStats.objects.get(encounter=self)
			s.data = ''
			s.save()
		except:
			pass


class Actor(models.Model):
	encounter 			= models.ForeignKey(Encounter)
	name 				= models.CharField(max_length=200, null=False)
	dps 				= models.BigIntegerField(default=0, null=False)
	hps 				= models.BigIntegerField(default=0, null=False)
	taken 				= models.BigIntegerField(default=0, null=False)
	obj_id 				= models.BigIntegerField(default=0, null=False)
	calling 			= models.CharField(max_length=200, blank=True, null=True)

	stats_cache 		= None

	def __unicode__(self):
		return "%s on %s" % (self.name, self.encounter)

	def get_dps(self):
		if self.stats_cache is None:
			self.stats_cache = self.encounter.stats()
		return self.dps / self.stats_cache.duration

	def get_hps(self):
		if self.stats_cache is None:
			self.stats_cache = self.encounter.stats()
		return self.hps / self.stats_cache.duration

	def get_taken(self):
		if self.stats_cache is None:
			self.stats_cache = self.encounter.stats()
		return self.taken / self.stats_cache.duration

class EncounterStats(models.Model):
	encounter 			= models.ForeignKey(Encounter)
	dps					= models.IntegerField(default=0, null=False)
	hps					= models.IntegerField(default=0, null=False)
	duration			= models.IntegerField(default=0, null=False)
	actors				= models.ManyToManyField(Actor)
	data 				= models.TextField(blank=True, null=True)

	rdata 				= None

	def __unicode__(self):
		return "%d" % self.encounter.id

	def parse(self):
		if self.rdata is None:
			self.rdata = cache.get("encounter_stats_%d" % self.encounter.id)
		if self.rdata is None:
			self.rdata = pickle.loads(str(self.data))
			cache.set("encounter_stats_%d" % self.encounter.id, self.rdata, 60 * 15)

		if not self.encounter.boss:
			b = Boss(name=self.rdata['bosses'])
			b.save()
			self.encounter.boss = b
			self.encounter.save()

		if self.duration == 0:
			self.duration = (self.rdata['end_time'] - self.rdata['start_time']).total_seconds()
			self.save()

	def top(self, stat='hits', view='done', type_actor='players'):
		result 	= []
		if self.rdata is None:
			self.rdata = cache.get("encounter_stats_%d" % self.encounter.id)
		if self.rdata is None:
			self.rdata = pickle.loads(self.data)
			cache.set("encounter_stats_%d" % self.encounter.id, self.rdata, 60 * 15)

		total 			= 0
		total_original 	= 0
		total_by_time 	= 0
		for actor, stats in self.rdata['stats']['actor'].items():
			if actor in self.rdata[type_actor]:
				if type_actor == 'npc':
					if self.rdata['actors'][actor]['name'] in mob_blacklist:
						continue
				found = False
				for e in result:
					if e['name'] == self.rdata['actors'][actor]['name']:
						found = True
						e['original'] 	+= int(stats['global'][view][stat])
						e['by_time'] 	= int(e['original'] / self.duration)
						e['value'] 		= int(e['original'])
						e['count']		+= 1

						total 			+= e['value']
						total_original	+= e['original']
						total_by_time 	+= e['by_time']
				if not found:
					el = {
						'name': 		self.rdata['actors'][actor]['name'],
						'actor':		self.get_actor_model(actor),
						'original': 	int(stats['global'][view][stat]),
						'id':			actor,
						'skills':		{},
						'count':		1,
						'is_player':	actor in self.rdata['players'],
					}
					for skill_id, value in stats[view]['skill'].items():
						if view not in el['skills']:
							el['skills'][view] = {}
						if stat not in el['skills'][view]:
							el['skills'][view][stat] = []
						if el['original'] == 0:
							ratio = 0
						else:
							ratio = float(value[stat]) / el['original'] * 100
						d = {'name': self.rdata['skills'][skill_id], 'value': value[stat], 'ratio': ratio, 'id': skill_id}
						el['skills'][view][stat].append(d)

					el['by_time'] 	= int(el['original'] / self.duration)
					el['value'] 	= int(el['original'])

					total 			+= el['value']
					total_original	+= el['original']
					total_by_time 	+= el['by_time']
					result.append(el)

		for el in result:
			if total == 0:
				el['ratio'] = 0
			else:
				el['ratio'] = int(float(el['value']) / total * 100)

		el = {
			'name':	 	'total',
			'value':	total,
			'original': total_original,
			'by_time':	total_by_time,
			'ratio':	100,
		}
		result.append(el)
		return result

	def top_damages(self):
		return self.top()

	def top_damages_taken(self):
		return self.top(view='received')

	def top_heals(self):
		return self.top('heals')

	def npc_top_damages(self):
		return self.top(type_actor='npc')

	def npc_top_damages_taken(self):
		return self.top(view='received', type_actor='npc')

	def npc_top_heals(self):
		return self.top('heals', type_actor='npc')

	def all_tops(self):
		result 	= []
		for p in self.top_damages():
			tmp_result 	= {}
			for key, value in p.items():
				if key is not 'name':
					tmp_result['damages_%s' % key] = value
				else:
					tmp_result[key]	= value
			result.append(tmp_result)

		for p in self.top_heals():
			for a in result:
				if a['name'] == p['name']:
					for key, value in p.items():
						if key is not 'name':
							a['heals_%s' % key] = value

		for p in self.top_damages_taken():
			for a in result:
				if a['name'] == p['name']:
					for key, value in p.items():
						if key is not 'name':
							a['taken_%s' % key] = value
		return result

	def npc_all_tops(self):
		result 	= []
		for p in self.npc_top_damages():
			tmp_result 	= {}
			for key, value in p.items():
				if key is not 'name':
					tmp_result['damages_%s' % key] = value
				else:
					tmp_result[key]	= value
			result.append(tmp_result)

		for p in self.npc_top_heals():
			for a in result:
				if a['name'] == p['name']:
					for key, value in p.items():
						if key is not 'name':
							a['heals_%s' % key] = value

		for p in self.npc_top_damages_taken():
			for a in result:
				if a['name'] == p['name']:
					for key, value in p.items():
						if key is not 'name':
							a['taken_%s' % key] = value
		return result

	def get_timeline(self, id_obj=None, by_actor=False):

		if by_actor is True:

			return self.get_timeline_by_actor()
		if id_obj is not None:

			return self.get_actor_timeline(id_obj)
		timeline = {'total': {}}

		for actor, stats in self.rdata['stats']['actor'].items():
			actor_name 	= self.rdata['actors'][actor]['name']

			for time, stat in stats['timeline'].items():
				time = int((time - self.rdata['start_time']).total_seconds() / 5) * 5

				tmp = 'npcs'
				if actor in self.rdata['players']:
					tmp = 'players'

				if time not in timeline['total']:
					timeline['total'][time] 	= {
						'time':		time,
						'players': {
							'done': {
								'heals': 0, 
								'hits': 0,
							},
							'received': {
								'heals': 0, 
								'hits': 0,
							}
						}, 
						'npcs': {
							'done': {
								'heals': 0, 
								'hits': 0,
							},
							'received': {
								'heals': 0, 
								'hits': 0,
							}
						}
					}

					timeline['total'][time][tmp]= deepcopy(stat)
				
				if actor_name not in timeline:
					timeline[actor_name]		= {}

				if time not in timeline[actor_name]:
					timeline[actor_name][time] 	= deepcopy(stat)
				
				timeline[actor_name][time]['done']['hits'] 			+= stat['done']['hits']
				timeline[actor_name][time]['done']['heals']	 		+= stat['done']['heals']
				timeline[actor_name][time]['received']['hits'] 		+= stat['received']['hits']
				timeline[actor_name][time]['received']['heals'] 	+= stat['received']['heals']
				
				
				
				timeline['total'][time][tmp]['done']['hits'] 		+= stat['done']['hits']
				timeline['total'][time][tmp]['done']['heals']	 	+= stat['done']['heals']
				timeline['total'][time][tmp]['received']['hits'] 	+= stat['received']['hits']
				timeline['total'][time][tmp]['received']['heals'] 	+= stat['received']['heals']

		final 	= {}
		for actor, values in timeline.items():
			for time, stats in values.items():
				if actor not in final:
					final[actor] = []
				stats['time'] = time
				final[actor].append(stats)

		return final

	def get_timeline_by_actor(self):
		result = {}
		for actor in self.rdata['players']:
			actor_name 			= self.get_actor(actor)['name']
			actor 				= int(actor)
			result[actor_name] 	= {'timeline': self.get_actor_timeline(actor), 'actor_id': actor}
		return result
	
	def get_actor_timeline(self, id_obj):
		results 	= {}
		aaaa= {}
		for time,stats in self.rdata['stats']['actor'][id_obj]['timeline'].items():
			t = (int(self.get_sec(time)) / 5) * 5
			if 'time' not in stats:
				stats['time'] = t
			if t in results:
				for view, s1 in stats.items():
					if view != 'time':
						for action, s2 in s1.items():
							results[t][view][action] += s2
							if action + "_count" not in results[t][view]:
								results[t][view][action + "_count"] = 0
							results[t][view][action + "_count"] += 1
			else:
				results[t] = stats
		final = []
		for f, data in results.items():
			final.append(data)
		
		return final

	def get_detailed_stats(self, obj_id):
		result 	= self.rdata['stats']['actor'][obj_id]['global']
		if result['done']['hits_count'] >  0:
			result['done']['hit_crit_rate'] = float(result['done']['critical_hits_count']) / result['done']['hits_count'] * 100
		else:
			result['done']['hit_crit_rate'] =  0
		if result['done']['heals_count'] > 0:
			result['done']['heal_crit_rate'] = float(result['done']['critical_heals_count']) / result['done']['heals_count'] * 100
		else:
			result['done']['heal_crit_rate'] = 0
		if result['received']['hits_count'] >  0:
			result['received']['hit_crit_rate'] = float(result['received']['critical_hits_count']) / result['received']['hits_count'] * 100
		else:
			result['received']['hit_crit_rate'] =  0
		return result

	def get_deathlog(self):
		result 	= []
		for death in self.rdata['stats']['deathlog']:
			if death['target'] in self.rdata['players']:
				v = {
					'time': (death['time'] - self.rdata['start_time']).total_seconds(),
					'player': self.get_actor(death['target'])['name'],
					'type':	'death',
					#'all':	death,
					'source':	self.get_actor(death['source'])['name'],
					'skill':	self.rdata['skills'][death['skill_id']],
					'amount':	death['amount'],
				}
				result.append(v)
		return result

	def get_rez(self):
		result 	= []
		for rez in self.rdata['rez']:
			tmp 			= {}
			tmp['player'] 	= self.get_actor(rez['target'])['name']
			tmp['time'] 	= self.get_sec(rez['time'])
			tmp['type']		= 'life'
			#tmp['all']		= rez
			tmp['source']	= self.get_actor(rez['source'])['name']
			tmp['skill']	= self.rdata['skills'][rez['skill']]
			result.append(tmp)
		return result

	def get_life_and_death(self):
		life = self.get_rez()
		death= self.get_deathlog()
		final= life
		for d in death:
			final.append(d)
		return final

	def get_actor_important_buffes(self, actor):
		actor = '%s' % actor
		results = []
		for source, skills in self.rdata['stats']['actor'][actor]['buffes']['received']['buff'].items():
			for skill_id, timeline in skills.items():
				if skill_id == 2117300275:
					timeline_t = []
					for time in timeline:
						a = {
							'from': self.get_sec(time[0]),
						}
						if len(time) == 2:
							a['to'] = self.get_sec(time[1])
						else:
							a['to'] = self.get_sec(self.rdata['end_time'])

						timeline_t.append(a)
					results.append({'skill_id': skill_id, 'skill_name': self.rdata['skills'][skill_id], 'timeline': timeline_t})
		return results

	def get_actor_buffes(self, actor):
		final_return = []
		actor_name 	= self.get_actor(actor)['name']
		tmp = self.rdata['stats']['actor'][actor]['buffes']
		for view, type_buffes in tmp.items():
			for type_buff, sources in type_buffes.items():
				for source_id, skills in sources.items():
					source_name = self.get_actor(source_id)['name']
					for skill_id, timeline in skills.items():
						skill_name 	= self.rdata['skills'][skill_id]
						skill_data = {
							'name':				skill_name,
							'uptime':			0,
							'total_duration':	0,
							'view':				view,
							'type_buff':		type_buff,
							'actor2_name':		source_name,
							'actor_name':		actor_name,
							'skill_id':			skill_id,
						}
						for time in timeline:
							a = {
								'from': self.get_sec(time[0]),
							}
							if len(time) == 2:
								a['to'] = self.get_sec(time[1])
							else:
								a['to'] = self.get_sec(self.rdata['end_time'])
							a['duration'] = a['to'] - a['from']
							skill_data['total_duration'] += a['duration']
						skill_data['uptime'] = "%i" % (float(skill_data['total_duration']) / self.duration * 100)
						final_return.append(skill_data)
		return final_return
						


	def get_important_buffes(self):
		results 	= []
		last 		= None
		for actor, stats in self.rdata['stats']['actor'].items():
			if actor not in self.rdata['players']:
				continue
			#self.stats['actor'][source]['buffes']['done'][type_buff][target] 	= {}
			a = self.rdata['actors'][actor]['name']
			for view, buffes in stats['buffes'].items():
				if view != "done":
					continue
					for target, skills in buffes['buff'].items():
						for skill_id, timeline in skills.items():
							# sicaron's contract
							if skill_id == 2117300275:
								s = self.rdata['skills'][skill_id]
								for time in timeline:
									b = {
										'from': time[0],
									}
									if len(time) == 2:
										b['to'] = time[1]
									else:
										b['to'] = self.rdata['end_time']
									results.append({
										'player':	a,
										'skill':	s,
										'display':	False,
										'display_player': True,
										'from':		self.get_sec(b['from']),
										'to':		self.get_sec(b['to']),
										'color':	'#000',
										'render': 	'line',
									})
				for type_buff, targets in buffes.items():
					for target, skills in targets.items():
						t = self.rdata['actors'][target]['name']
						for skill_id, buff_timeline in skills.items():
							s = self.rdata['skills'][skill_id]
							if skill_id not in (1742325987, 766317719):
								continue
							if actor != target:
								continue

							for b in buff_timeline:
								if 1 not in b:
									b.append(self.rdata['end_time'])
								if last == (a,t,s,b):
									continue
								last = (a,t,s,b)
								results.append({
									'player':	a,
									'skill':	s,
									'skill_id':	skill_id,
									'display':	False,
									'display_player': False,
									'from':		self.get_sec(b[0]),
									'to':		self.get_sec(b[1]),
									'render':	'band',
								})
		return results
	
	def get_detailed_total_stats(self, actor_id, view='done'):
		results	= []
		for skill_id, stats in self.rdata['stats']['actor'][actor_id][view]['skill'].items():
			tmp = stats
			tmp['skill_id'] = skill_id
			tmp['skill_name']=self.rdata['skills'][skill_id]
			results.append(tmp)
		return results


	def get_detailed_by_actor_stats(self, actor_id):
		results	= []
		for actor, skills in self.rdata['stats']['actor'][actor_id]['done']['actor_skill'].items():
			actor_name = self.get_actor(actor)['name']
			for skill_id, stats in skills.items():
				tmp = stats
				tmp['actor_id'] = actor
				tmp['is_player'] = "%s" % actor in self.rdata['players']
				tmp['actor_name']= actor_name
				tmp['skill_id'] = skill_id
				tmp['skill_name']=self.rdata['skills'][skill_id]
				results.append(tmp)
		return results

	
	def create_actors(self):
		for actor, stats in self.rdata['actors'].items():
			if actor in self.rdata['players']:
				skill_id = 0
				for actor2, skills in self.rdata['stats']['actor'][actor]['done']['actor_skill'].items():
					to_break = False
					for skill_id in skills:
						if skill_id in skill_to_class:
							#print classes[skill_to_class[skill_id]], self.get_actor(actor)['name']
							to_break = True
							break
					if to_break is True:
						break
					else:
						#print "No class found for %s [%s] (%d)" % (self.get_actor(actor)['name'], self.rdata['skills'][skill_id], skill_id)
						pass
				if skill_id is not 0 and skill_id in skill_to_class:
					calling_name = classes[skill_to_class[skill_id]]
				else:
					calling_name = 'unknown'
				obj, created = Actor.objects.get_or_create(
					encounter=self.encounter, 
					name=str(stats['name']), 
					obj_id=actor,
					dps=self.rdata['stats']['actor'][actor]['global']['done']['hits'], 
					taken=self.rdata['stats']['actor'][actor]['global']['received']['hits'], 
					hps=self.rdata['stats']['actor'][actor]['global']['done']['heals'],
					calling=calling_name)

	def get_actor(self, id):
		return self.rdata['actors'][id]

	def get_actor_model(self, id):
		return Actor.objects.get(obj_id=id, encounter=self.encounter)
	
	# return the combat elapsed time from a datetime.
	def get_sec(self, d):
		return (d - self.rdata['start_time']).total_seconds()

class Down(models.Model):
	boss 				= models.ForeignKey(Boss)
	guild 				= models.ForeignKey(Guild)
	encounter 			= models.ForeignKey(Encounter)
	verified 			= models.BooleanField(default=False)

	def __unicode__(self):
		return "%s by %s" % (self.boss.name, self.guild)

def create_user_profile(sender, instance, created, **kwargs):
    if created:
        UserProfile.objects.create(user=instance)

post_save.connect(create_user_profile, sender=User)

class News(models.Model):
	title 				= models.CharField(max_length=300)
	body				= models.TextField()
	author 				= models.ForeignKey(User)
	publication_date	= models.DateTimeField(auto_now=True)

	def __unicode__(self):
		return "%s by %s" % (self.title, self.author.username)

	def comments(self):
		return NewsComment.objects.filter(news=self)

class NewsComment(models.Model):
	news 				= models.ForeignKey(News)
	title 				= models.CharField(max_length=300)
	body				= models.TextField()
	author 				= models.ForeignKey(User)
	publication_date	= models.DateTimeField(auto_now=True)


class LogForm(ModelForm):
	class Meta:
		model 	= Log
		fields	= ('log_file', 'private')

class GuildJoinRequest(models.Model):
	guild 		= models.ForeignKey(Guild)
	user 		= models.ForeignKey(User)
	date 		= models.DateTimeField(auto_now_add=True)