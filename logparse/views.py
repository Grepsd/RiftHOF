from django.shortcuts import render, redirect
from models import *
from django.core.context_processors import csrf
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.utils import simplejson
from datetime import datetime
from parser import Parser
from django.conf import settings
from django.views.decorators.cache import cache_page
from django.core.cache import cache

def home(request):
	return render(request, 'home.html')

@login_required
def guild_home(request):
	data = {
		'log_form': 	LogForm(),
		'guild':		request.user.get_profile().guild,
	}
	return render(request, 'guild/home.html', data)

@login_required
def guild_join(request):
	if request.method == 'GET':
		data		= {
			'zones':		Zone.objects.all(),
		}
		return render(request, 'guild/join.html', data)
	else:
		data	= {'errors': ['This functionality has been disabled.']}
		return render(request, 'guild/join.html', data)

@login_required
def guild_create(request):
	if request.method == 'GET':
		data 		= {
			'zones':		Zone.objects.all(),
			'factions':		factions,
		}
		return render(request, 'guild/create.html', data)
	else:

		guild 		= Guild(name=request.POST.get('name'), faction=request.POST.get('faction'))
		guild.shard = Shard.objects.get(id=request.POST.get('shard'))

		try:
			guild.save()
			data = {'success': True, 'guild': guild}
			request.user.get_profile().guild = guild
			request.user.get_profile().save()
		except Exception as e:
			data = {'errors': [e]}
		return render(request, 'guild/create.html', data)

@login_required
def guild_quit(request):
	return render(request, 'guild/quit.html')

@login_required
def guild_quit_act(request):
	request.user.get_profile().leave_guild()
	return redirect('guild_home')

@login_required
def api_guild_list(request):
	if 'shard_id' in request.GET:
		guilds = Guild.objects.filter(shard__id=request.GET.get('shard_id'))

	else:
		guilds = Guild.objects.all()
	result 	= {}
	for guild in guilds:
		result[guild.id] = guild.name
	return HttpResponse(simplejson.dumps(result), mimetype="application/json")

@login_required
def api_guild_checkname(request):
	try:
		Guild.objects.get(name=str(request.GET.get('name')))
		result = 0
	except:
		result = 1
	return HttpResponse(result, mimetype="application/json")

@login_required
def guild_log_upload(request):
	data 			= {}
	form 			= LogForm(request.POST, request.FILES)
	model 			= form.save(False)
	model.user 		= request.user
	guild 			= request.user.get_profile().guild
	model.guild 	= guild
	model.upload_date= datetime.now()

	if form.is_valid():
		model.save()
		data['log'] = model

	return render(request, 'log/upload.html', data)

#@cache_page(60 * 15)
def guild_log_show(request, id):
	data	= {
		'log':	 Log.objects.get(id=id)
	}
	return render(request, 'log/show.html', data)

def api_log_check_status(request, id):
	log = Log.objects.get(id=id)
	if not log.processed:
		log.processed = True
		log.save()
		parser = Parser(settings.BASEPATH + '/content' + log.log_file.url, log_id=log.id)
		parser.parse(False)
	return HttpResponse(int(log.processed), mimetype="application/json") 

#cache_page(60 * 15)
def guild_log_encounter_show(request, id_encounter):

	id_encounter = int(id_encounter)

	enc 	= Encounter.objects.get(id=id_encounter)
	c 		= False
	if not enc.parsed:
		enc.parse()
		c = True

	stats = enc.stats()
	stats.parse()
	if c:
		stats.create_actors()

	if not enc.boss:
		boss_id 	= 0
		boss_name 	= 'Unknown'
	else:
		boss_id 	= enc.boss.id
		boss_name 	= enc.boss.name

	#data = cache.get("encounter_%d" % id_encounter)
	data = None

	if data is None:
		data 	= {
			'encounter':	enc,
			'boss_id':		boss_id,
			'boss_name':	boss_name,
			'all_tops':		stats.all_tops(),
			'npc_all_tops':	stats.npc_all_tops(),
			'timeline':		stats.get_timeline(),
			'deathes':		stats.get_deathlog(),
			'rez':			stats.get_rez(),
			'buffes':		stats.get_important_buffes(),
			'life_and_death':stats.get_life_and_death(),
			}

		cache.set("encounter_%d" % id_encounter, data, 6 * 15)

	return render(request, 'encounter/show.html', data)

def ranking_boss(request, id):
	data = {}
	return render(request, 'ranking/boss/show.html', data)

def actor_show_detail(request, id_encounter, id_obj):
	id_encounter	= int(id_encounter)
	id_obj			= int(id_obj)
	data 			= cache.get("encounter_%d_actor_%d" % (id_encounter, id_obj))
	data = None
	if data is None:
		actor 		= Actor.objects.get(encounter__id=id_encounter, obj_id=id_obj)
		encounter 	= actor.encounter
		stats 		= encounter.stats()
		stats.parse()
		data 		= {
			'actor': 		actor,
			'deathes':		stats.get_deathlog(),
			'rez':			stats.get_rez(),
			'buffes':		stats.get_important_buffes(),
			'timeline':		stats.get_timeline(id_obj),
			'stats':		stats.get_detailed_stats(id_obj),
			'encounter_stats': stats,
		}
		cache.set("encounter_%d_actor_%d" % (id_encounter, id_obj), data, 6 * 15)
	return render(request, 'actor/show.html', data)