from django.shortcuts import render, redirect, get_object_or_404
from models import *
from django.core.context_processors import csrf
from django.contrib.auth.decorators import login_required, user_passes_test
from django.http import HttpResponse
from django.utils import simplejson
from datetime import datetime, timedelta, date
from parser import Parser
from django.conf import settings
from django.views.decorators.cache import cache_page
from django.core.cache import cache
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import MultipleObjectsReturned
from django.core.paginator import Paginator, EmptyPage, PageNotAnInteger
from django.db.models import Q

def home(request):
	data 		= cache.get("home")
	if data is None:
		data 		= {
			'logs': 			Log.objects.filter(private=False, processed=True, processing=False).order_by('-id')[0:5],
			'log_form': 		LogForm(),
			'news':				News.objects.all().order_by('-id')[0:1],
			'active_users':		User.objects.filter(last_login__gte=datetime.now() - timedelta(hours=1))
			}
		cache.set("home", data, 86400)

	if request.user.is_authenticated():
		if request.user.get_profile().has_guild():
			guild 		= request.user.get_profile().guild
			logs 		= cache.get("logs_%d" % guild.id)
			if logs is None:
				data['guild_logs']	= Log.objects.filter(guild=guild, processed=True, processing=False).order_by('-id')[0:5]
				cache.set("logs_%d" % guild.id, logs, 300)
	return render(request, 'home.html', data)

def register(request):
	data = {}
	if request.method == 'POST':
		form 	= UserCreationForm(request.POST)
		if form.is_valid():
			o = form.save()
			data['new_user'] = o
	else:
		form 	= UserCreationForm()
	data['form']	= form
	return render(request, 'register.html', data)

@login_required
def guild_home(request):
	guild 		= request.user.get_profile().guild
	data = {
		'log_form': 	LogForm(),
		'guild':		guild,
		'request_list':	GuildJoinRequest.objects.filter(guild=guild)
	}
	return render(request, 'guild/home.html', data)

@login_required
def guild_list(request):
	data = {
		'guild_list': Guild.objects.all(),
	}
	return render(request, 'guild/list.html', data)

@login_required
def guild_join(request, guild_id):
	guild 	= Guild.objects.get(id=guild_id)
	g 		= GuildJoinRequest(user=request.user, guild=guild)
	g.save()
	data = {
		'guild':	guild,
	}
	return render(request, 'guild/join.html', data)

@login_required
def guild_join_request_accept(request, req_id):
	g = GuildJoinRequest.objects.get(id=req_id)
	profile = g.user.get_profile()
	profile.guild = g.guild
	profile.save()
	g.delete()
	return redirect('guild_home')

@login_required
def guild_join_request_deny(request, req_id):
	g = GuildJoinRequest.objects.get(id=req_id)
	g.delete()
	return redirect('guild_home')

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
@user_passes_test(lambda u: u.is_active, login_url='/unauthorized')
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
		parser = Parser(settings.BASEPATH + '/content' + model.log_file.url, log_id=model.id)
		try:
			parser.handle_file()
		except Exception as e:
			model.delete()
			return render(request, 'log/upload.html', {'error': e})
		data['log'] = model

	return render(request, 'log/upload.html', data)

@login_required
@user_passes_test(lambda u: u.is_active, login_url='/unauthorized')
def guild_log_show(request, id):
	log 	= cache.get("log_%d" % int(id))
	if log is None:
		log = get_object_or_404(Log, id=id)
		if log.processed:
			cache.set("log_%d" % int(id), log, 60)
	return render(request, 'log/show.html', {'log': log})

@login_required
@user_passes_test(lambda u: u.is_active, login_url='/unauthorized')
def api_log_check_status(request, id):
	return HttpResponse(int(Log.objects.get(id=int(id)).processed), mimetype="application/json") 

@login_required
@user_passes_test(lambda u: u.is_active, login_url='/unauthorized')
def guild_log_encounter_show(request, id_encounter):

	data 			= cache.get("encounter_%d" % int(id_encounter))
	if data is None:
		data 		= get_object_or_404(Encounter, id=int(id_encounter))
		data.process_for_display()
		cache.set("encounter_%d" % int(id_encounter), data, 86400)


	return render(request, 'encounter/show.html', {'encounter': data})

@login_required
def ranking_boss(request, id):
	data = {}
	return render(request, 'ranking/boss/show.html', data)

@login_required
@user_passes_test(lambda u: u.is_active, login_url='/unauthorized')
def actor_show_detail(request, id_encounter, id_obj):
	#encounter 	= get_object_or_404(Encounter, id=int(id_encounter))
	data 		= cache.get("encounter_%d_actor_%d" % (int(id_encounter), int(id_obj)))
	if data is None:
		actor 		= get_object_or_404(Actor, encounter__id=int(id_encounter), obj_id=int(id_obj))
		stats 		= actor.encounter.stats()
		stats.parse()

		data 		= {
			'actor': 						actor,
			'deathes':						stats.get_deathlog(),
			'rez':							stats.get_rez(),
			'buffes':						stats.get_important_buffes(),
			'timeline':						stats.get_timeline(id_obj),
			'stats':						stats.get_detailed_stats(id_obj),
			'encounter_stats': 				stats,
			'detailed_total_stats': 		stats.get_detailed_total_stats(id_obj),
			'detailed_total_stats_received':stats.get_detailed_total_stats(id_obj, 'received'),
			'detailed_by_actor_stats': 		stats.get_detailed_by_actor_stats(id_obj),
			'important_buffes': 			stats.get_actor_important_buffes(id_obj),
			'actor_buffes':					stats.get_actor_buffes(id_obj),
		}
		cache.set("encounter_%d_actor_%d" % (int(id_encounter), int(id_obj)), data, 86400)

	return render(request, 'actor/show.html', data)

def unauthorized(request):
	return render(request, 'unauthorized.html')

def boss_list(request):
	data = {
		'boss_list':	Boss.objects.all().order_by('raid__id'),
	}
	return render(request, 'boss/list.html', data)

def boss_show(request, boss_id):
	boss = get_object_or_404(Boss, id=boss_id)
	if request.user.is_staff:
		encounters 	= Encounter.objects.filter(boss=boss)
	else:
		encounters = Encounter.objects.filter(Q(boss=boss) & (Q(log__guild=request.user.get_profile().guild) | Q(private=False)))
	return render(request, 'boss/show.html', {'boss': boss, 'encounters': encounters})

def show_guild_try_boss(request, guild_id, boss_id, day, month, year):
	start_date 	= date(int(year), int(month), int(day))
	end_date 	= start_date + timedelta(days=1)
	data 	= {
		'boss':		get_object_or_404(Boss, id=boss_id),
		'guild':	get_object_or_404(Guild, id=guild_id),
		'start_date':start_date,

	}
	data['encounters']	=	Encounter.objects.filter(
			log__guild=data['guild'], 
			boss=data['boss'], 
			log__upload_date__gte=start_date, 
			log__upload_date__lt=end_date)
	return render(request, 'boss/show_guild_try.html', data)

@login_required
@user_passes_test(lambda u: u.is_active, login_url='/unauthorized')
@user_passes_test(lambda u: u.is_staff, login_url='/unauthorized')
def dashboard_logs_show(request):
	data = {'logs': Log.objects.all()}
	return render(request, 'dashboard/logs/list.html', data)

@login_required
def log_list(request):
	if request.user.is_staff:
		logs 	= Log.objects.all().order_by('-id')
	else:
		logs 	= Log.objects.filter(Q(private=False) | (Q(guild=request.user.get_profile().guild))).order_by('-id')
	paginator= Paginator(logs, 25)
	page 	= request.GET.get('page')
	try:
		log_list = paginator.page(page)
	except PageNotAnInteger:
		log_list = paginator.page(1)
	except EmptyPage:
		log_list = paginator.page(paginator.num_pages)

	data = {
		'logs':	log_list,
	}
	return render(request, 'log/list.html', data)

@login_required
def comment_post(request, object_type, object_id):
	object_type_short= None
	for short,o_type in comments_types:
		if o_type == object_type:
			object_type_short = short
	c = Comment(object_type=object_type_short, object_id=object_id, user=request.user, comment=request.POST.get('comment'))
	c.save()
	if object_type == 'log':
		return redirect('guild_log_show', object_id)
	elif object_type == 'encounter':
		return redirect('guild_log_encounter_show', object_id)
	return redirect()

@login_required
def log_delete(request, log_id):
	l = Log.objects.get(id=log_id)
	if l.user == request.user:
		l.delete()
	return redirect('home')

@login_required
def log_rename(request, log_id):
	l = Log.objects.get(id=log_id)
	if l.user == request.user:
		l.name = request.POST.get('name')
		l.save()
	return redirect('guild_log_show', l.id)

@login_required
def guild_show(request, guild_id, guild_name):
	guild 	= get_object_or_404(Guild, id=guild_id)
	if request.user.is_staff:
		logs 	= Log.objects.filter(guild=guild).order_by('-id')
	else:
		logs 	= Log.objects.filter((Q(private=False) | (Q(guild=request.user.get_profile().guild))) & (Q(guild=guild))).order_by('-id')
	paginator= Paginator(logs, 25)
	page 	= request.GET.get('page')
	try:
		log_list = paginator.page(page)
	except PageNotAnInteger:
		log_list = paginator.page(1)
	except EmptyPage:
		log_list = paginator.page(paginator.num_pages)
	data 	= {
		'guild':	guild,
		'logs':		log_list,
	}
	return render(request, 'guild/show.html', data)