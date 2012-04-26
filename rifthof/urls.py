from django.conf.urls import patterns, include, url
from django.conf.urls.i18n import i18n_patterns

# Uncomment the next two lines to enable the admin:
from django.contrib import admin
admin.autodiscover()

urlpatterns = patterns('',
    (r'^i18n/',                     include('django.conf.urls.i18n')),
)

urlpatterns += i18n_patterns('',
    # Examples:
    url(r'^$', 						'logparse.views.home', 					name='home'),
    url(r'^login$', 				'django.contrib.auth.views.login', {'template_name': 'login.html'}, name='login'),
    url(r'^logout$',                'django.contrib.auth.views.logout', {'next_page': '/'}, name='logout'),
    url(r'^register$',              'logparse.views.register',              name='register'),
    url(r'^boss/list$',             'logparse.views.boss_list',             name='boss_list'),
    url(r'^boss/(\d+)$',             'logparse.views.boss_show',             name='boss_show'),
    url(r'^guild/(\d+)/boss/(\d+)/date/(\d+)/(\d+)/(\d+)$',             'logparse.views.show_guild_try_boss',             name='show_guild_try_boss'),



    url(r'^guild$', 				'logparse.views.guild_home', 			name='guild_home'),
    url(r'^guild/(\d+)/([^\/]+)$',  'logparse.views.guild_show',            name='guild_show'),
    url(r'^guild/list$',            'logparse.views.guild_list',            name='guild_list'),
    url(r'^guild/join/(\d+)$',      'logparse.views.guild_join',            name='guild_join'),
    url(r'^guild/request/deny/(\d+)$','logparse.views.guild_join_request_deny',name='guild_join_request_deny'),
    url(r'^guild/request/accept/(\d+)$','logparse.views.guild_join_request_accept',name='guild_join_request_accept'),

    url(r'^guild/create$', 			'logparse.views.guild_create', 			name='guild_create'),
    url(r'^guild/quit$', 			'logparse.views.guild_quit', 			name='guild_quit'),
    url(r'^guild/quit/act$', 		'logparse.views.guild_quit_act', 		name='guild_quit_act'),
    url(r'^log/upload$', 		    'logparse.views.guild_log_upload', 		name='guild_log_upload'),
    url(r'^log/(\d+)$',             'logparse.views.guild_log_show',        name='guild_log_show'),
    url(r'^log/list/$',             'logparse.views.log_list',              name='log_list'),
    url(r'^log/delete/(\d+)$',      'logparse.views.log_delete',            name='log_delete'),
    url(r'^log/rename/(\d+)$',      'logparse.views.log_rename',            name='log_rename'),

    url(r'^encounter/(\d+)$',       'logparse.views.guild_log_encounter_show',name='guild_log_encounter_show'),
    url(r'^encounter/(\d+)/(\d+)$', 'logparse.views.actor_show_detail',     name='actor_show_detail'),
    url(r'^unauthorized$',          'logparse.views.unauthorized',          name='unauthorized'),
    

    url(r'^ranking/boss/(\d+)$',    'logparse.views.ranking_boss',          name='ranking_boss'),

    url(r'^api/guild/list$', 		'logparse.views.api_guild_list', 		name='api_guild_list'),
    url(r'^api/guild/checkname$',   'logparse.views.api_guild_checkname',	name='api_guild_checkname'),
    url(r'^api/guild/log/check/(\d+)$','logparse.views.api_log_check_status',name='api_log_check_status'),

    url(r'^comment/post/(\S+)/(\d+)$','logparse.views.comment_post',          name='comment_post'),



    url(r'^dashboard/logs/$','logparse.views.dashboard_logs_show',          name='dashboard_logs_show'),
  
    # url(r'^rifthof/', include('rifthof.foo.urls')),

    # Uncomment the admin/doc line below to enable admin documentation:
    url(r'^admin/doc/', include('django.contrib.admindocs.urls')),

    # Uncomment the next line to enable the admin:
    url(r'^admin/', include(admin.site.urls)),
)
