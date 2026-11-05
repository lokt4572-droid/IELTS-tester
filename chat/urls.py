from django.urls import path

from . import views

app_name = "chat"

urlpatterns = [
    path("", views.chat_page, name="home"),
    path("send/", views.send, name="send"),
    path("<int:pk>/", views.chat_page, name="session"),
    path("<int:pk>/delete/", views.delete, name="delete"),
]
