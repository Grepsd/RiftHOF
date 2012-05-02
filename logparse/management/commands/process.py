from django.core.management.base import BaseCommand, CommandError, NoArgsCommand
from django.utils import translation
from logparse.models import *
from parser import Parser
from django.conf import settings
from datetime import datetime, timedelta
from django.utils.timezone import utc
from django.db.models import Q

class Command(BaseCommand):
    can_import_settings = True

    def handle(self, *args, **options):
        self.trash_olds()
        l = Log.objects.filter(processing=True).count()
        if l < settings.MAX_PROCESSING:
            todo_list = Log.objects.filter(Q(processing=False), Q(processed=False), Q(error__isnull=True) | Q(error="") | Q(start_processing_time__lt=datetime.now() - timedelta(hours=1)))
            try:
                log = todo_list[0]
            except IndexError:
                print "nothing to do"
                return
            print "Processing log %d" % log.id
            start_time                  = datetime.utcnow().replace(tzinfo=utc)
            log.start_processing_time   = start_time
            log.save()
            try:
                log.parse()
            except Exception as e:
                log.error = e
                log.processing = False
                log.save()
                raise e
            log.end_processing_time     = datetime.utcnow().replace(tzinfo=utc)
            log.save()
            duration                    = (datetime.utcnow().replace(tzinfo=utc) - start_time).total_seconds()
            print "Log %d processed in %ds" % (log.id, duration)
        else:
            print "max parallel processing exceeded."

    def trash_olds(self):
        trashs = Log.objects.filter(processing=True, start_processing_time__lt=datetime.utcnow().replace(tzinfo=utc) - timedelta(hours=1))
        for trash in trashs:
            trash.processing = False
            trash.start_processing_time = None
            trash.save()
