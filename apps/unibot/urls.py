from django.urls import path
from . import views

app_name = 'unibot'

urlpatterns = [
    path('credential-setup/<uuid:session_id>/', views.credential_setup, name='credential_setup'),
] 