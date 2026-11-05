from django.urls import path

from . import views

urlpatterns = [
    path("", views.home, name="home"),
    path("tests/", views.tests_hub, name="tests_hub"),
    path("dashboard/", views.dashboard, name="dashboard"),
    path("accounts/signup/", views.signup, name="signup"),
]
