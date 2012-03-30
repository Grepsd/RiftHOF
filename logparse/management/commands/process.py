from django.core.management.base import BaseCommand, CommandError, NoArgsCommand
from django.utils import translation
from logparse.models import *
from parser import Parser
from django.conf import settings
from datetime import datetime

class Command(BaseCommand):
    can_import_settings = True

    def handle(self, *args, **options):
        l = Log.objects.filter(processing=True).count()
        if l < settings.MAX_PROCESSING:
            todo_list = Log.objects.filter(processing=False, processed=False)
            log = todo_list[0]
            print "Processing log %d" % log.id
            start_time = datetime.now()
            log.parse()
            duration = (datetime.now() - start_time).total_seconds()
            print "Log %d processed in %ds" % (log.id, duration)
            
