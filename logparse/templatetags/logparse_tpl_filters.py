from django import template
from django.template.defaultfilters import stringfilter

register = template.Library()

def seconds_duration(secs):
	if secs == '':
		return 'n/a'
	secs 	= int(secs)
	hours 	= int(secs / 60 / 60)
	secs 	%= 60 * 60
	minutes	= int(secs / 60)
	secs 	%= 60
	if hours > 0:
		if minutes > 0:
			if secs > 0:
				return "%d:%02d:%02d" % (hours, minutes, secs)
			else:
				return "%d:%02d:00" % (hours, minutes)
		else:
			if secs > 0:
				return "%d:00:%02d" % (hours, secs)
			else:
				return "%d:00:00" % (hours)
	else:
		if minutes > 0:
			if secs > 0:
				return "%d:%02d" % (minutes, secs)
			else:
				return "%d:00" % (minutes)
		else:
			if secs > 0:
				return "0:%d" % (secs)
@stringfilter
@register.filter
def concat(string, args):
	final = [string] + args.split(',')
	return "".join(final)

@register.filter
@stringfilter
def prepend(string, arg):
	return arg + string

register.filter('secs', seconds_duration)