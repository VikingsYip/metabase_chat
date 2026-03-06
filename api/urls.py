"""
URL configuration for the REST API.
"""
from django.urls import path
from . import views

app_name = 'api'

urlpatterns = [
    # Database endpoints
    path('databases/', views.list_databases, name='list_databases'),
    path('databases/<int:database_id>/tables/', views.list_tables, name='list_tables'),
    path('tables/<int:table_id>/fields/', views.get_table_fields, name='get_table_fields'),

    # Query endpoints
    path('query/execute/', views.execute_query, name='execute_query'),
    path('cards/', views.list_cards, name='list_cards'),
    path('cards/create/', views.create_card, name='create_card'),
    path('cards/execute/', views.execute_card, name='execute_card'),

    # Collection endpoints
    path('collections/', views.list_collections, name='list_collections'),
    path('collections/create/', views.create_collection, name='create_collection'),

    # Auth info
    path('login/', views.login, name='login'),
]
