from django.db import models
from django.contrib.auth.models import User
from django.db.models.signals import post_save
from django.forms import ModelForm
from parser import Parser, mob_blacklist
from django.conf import settings
import pickle
from django.core.cache import cache


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

	def __unicode__(self):
		return self.name

class Log(models.Model):
	guild 				= models.ForeignKey(Guild)
	log_file 			= models.FileField(upload_to='combat_logs')
	upload_date			= models.DateTimeField(auto_now=True)
	processing_date 	= models.DateTimeField(null=True)
	processed 			= models.BooleanField(default=False)
	private 			= models.BooleanField(default=False)
	user 				= models.ForeignKey(User)

	def __unicode__(self):
		return "%d parse %s" % (self.id, self.guild)

	def encounters(self):
		return Encounter.objects.filter(log=self).order_by('id')

class Encounter(models.Model):
	boss 				= models.ForeignKey(Boss, blank=True, null=True)
	log 				= models.ForeignKey(Log)
	start_offset		= models.IntegerField(default=0)
	end_offset			= models.IntegerField(null=False)
	private 			= models.BooleanField(default=False)
	wipe 				= models.BooleanField(default=False)
	parsed 				= models.BooleanField(default=False)

	cache 				= None

	def __unicode__(self):
		return "%d against %s" % (self.id, self.boss)

	def parse(self):
		if not self.parsed:
			parser 		= Parser(settings.BASEPATH + '/content' + self.log.log_file.url, self.start_offset, self.end_offset)
			parser.parse(full=True)
			try:
				encounter 	= parser.get_encounters()[0]
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
			except:
				self.delete()

	def stats(self):
		try:
			return EncounterStats.objects.get(encounter=self)
		except:
			e = EncounterStats(encounter=self)
			if self.cache is not None:
				e.data = self.cache
			try:
				e.save()
			except:
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
				el = {
					'name': 		self.rdata['actors'][actor]['name'],
					'original': 	int(stats['global'][view][stat]),
					'id':			actor,
					'skills':		{},
				}
				for skill_id, value in stats[view]['skill'][stat].items():
					if view not in el['skills']:
						el['skills'][view] = {}
					if stat not in el['skills'][view]:
						el['skills'][view][stat] = []
					if el['original'] == 0:
						ratio = 0
					else:
						ratio = float(value) / el['original'] * 100
					d = {'name': self.rdata['skills'][skill_id], 'value': value, 'ratio': ratio}
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

	def get_timeline(self, id_obj=None):
		if id_obj is not None:
			return self.get_actor_timeline(id_obj)
		timeline = {}
		for actor, stats in self.rdata['stats']['actor'].items():
			actor_name 	= self.rdata['actors'][actor]['name']
			for time, stat in stats['timeline'].items():
				time = int((time - self.rdata['start_time']).total_seconds() / 5) * 5
				if actor in self.rdata['players']:
					tmp = 'players'
				else:
					tmp = 'npcs'
				if time not in timeline:
					timeline[time] = {'total': {'players': {'done': {'heals': 0, 'hits': 0},'received': {'heals': 0, 'hits': 0}}, 'npcs': {'done': {'heals': 0, 'hits': 0},'received': {'heals': 0, 'hits': 0}}}}
					timeline[time]['total'][tmp]= stat
				if actor not in timeline[time]:
					timeline[time][actor_name] 	= stat
				else:
					timeline[time][actor_name]['done']['hits'] 		+= stat['done']['hits']
					timeline[time][actor_name]['done']['heals']	 	+= stat['done']['heals']
					timeline[time][actor_name]['received']['hits'] 	+= stat['received']['hits']
					timeline[time][actor_name]['received']['heals'] += stat['received']['heals']
				
				timeline[time]['total'][tmp]['done']['hits'] 		+= stat['done']['hits']
				timeline[time]['total'][tmp]['done']['heals']	 	+= stat['done']['heals']
				timeline[time]['total'][tmp]['received']['hits'] 	+= stat['received']['hits']
				timeline[time]['total'][tmp]['received']['heals'] 	+= stat['received']['heals']
		final = []
		for f, s in timeline.items():
			s['time'] = f
			final.append(s)
		return final
	
	def get_actor_timeline(self, id_obj):
		id_obj 		= '%d' % id_obj
		results 	= {}
		for time,stats in self.rdata['stats']['actor'][id_obj]['timeline'].items():
			t = (int(self.get_sec(time)) / 5) * 5
			if 'time' not in stats:
				stats['time'] = t
			if t in results:
				for view, s1 in stats.items():
					if view != 'time':
						for action, s2 in s1.items():
							results[t][view][action] += s2
			else:
				results[t] = stats
		final = []
		for f, data in results.items():
			final.append(data)
		return final

	def get_detailed_stats(self, obj_id):
		result 	= self.rdata['stats']['actor']['%d' % obj_id]['global']
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
			result.append(tmp)
		return result

	def get_life_and_death(self):
		life = self.get_rez()
		death= self.get_deathlog()
		final= life
		for d in death:
			final.append(d)
		return final


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
				for type_buff, targets in buffes.items():
					for target, skills in targets.items():
						t = self.rdata['actors'][target]['name']
						for skill_id, buff_timeline in skills.items():
							s = self.rdata['skills'][skill_id]
							if s not in ("Puissance flamboyante", "Couplet de joie"):
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
									'from':		self.get_sec(b[0]),
									'to':		self.get_sec(b[1]),
								})
		return results
	
	def create_actors(self):
		for actor, stats in self.rdata['actors'].items():
			if actor in self.rdata['players']:
				obj, created = Actor.objects.get_or_create(
					encounter=self.encounter, 
					name=stats['name'], 
					obj_id=actor,
					dps=self.rdata['stats']['actor'][actor]['global']['done']['hits'], 
					taken=self.rdata['stats']['actor'][actor]['global']['received']['hits'], 
					hps=self.rdata['stats']['actor'][actor]['global']['done']['heals'])

	def get_actor(self, id):
		return self.rdata['actors'][id]
	
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


class LogForm(ModelForm):
	class Meta:
		model 	= Log
		fields	= ('log_file', 'private')