"""
Django management command to clear schema cache.

Usage:
    python manage.py clear_schema_cache              # Clear all cache
    python manage.py clear_schema_cache --database 3 # Clear cache for database 3
"""
from django.core.management.base import BaseCommand, CommandError
from chat.services.nl_to_sql import NLToSQLConverter


class Command(BaseCommand):
    help = 'Clear the database schema cache'

    def add_arguments(self, parser):
        parser.add_argument(
            '--database',
            type=int,
            help='Database ID to clear cache for (if not provided, clears all cache)',
        )

    def handle(self, *args, **options):
        database_id = options.get('database')

        try:
            NLToSQLConverter.clear_schema_cache(database_id)

            if database_id:
                self.stdout.write(
                    self.style.SUCCESS(f'Successfully cleared schema cache for database {database_id}')
                )
            else:
                self.stdout.write(
                    self.style.SUCCESS('Successfully cleared all schema cache')
                )

        except Exception as e:
            raise CommandError(f'Error clearing schema cache: {e}')
