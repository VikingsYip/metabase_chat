"""
URL configuration for the chat application.
"""
from django.urls import path
from . import views

app_name = 'chat'

urlpatterns = [
    path('', views.chat_interface, name='chat_interface'),
    path('conversation/<int:conversation_id>/', views.conversation_detail, name='conversation_detail'),
    path('api/send/', views.send_message, name='send_message'),
    path('api/send/<int:conversation_id>/', views.send_message, name='send_message_conversation'),
]
