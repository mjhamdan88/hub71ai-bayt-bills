from django.urls import path
from . import views
urlpatterns = [path('',views.home),path('login/',views.auth),path('logout/',views.signout),path('health/',views.health),path('ai/respond/',views.ai_respond),path('bills/<int:pk>/pay/',views.pay),path('budgets/<int:pk>/',views.budget),path('autopay/',views.autopay)]
