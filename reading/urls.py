from django.urls import path

from . import views

app_name = "reading"

urlpatterns = [
    path("", views.test_list, name="list"),
    path("attempt/<int:pk>/", views.attempt_page, name="attempt"),
    path("attempt/<int:pk>/save/", views.attempt_save, name="save"),
    path("attempt/<int:pk>/submit/", views.attempt_submit, name="submit"),
    path("attempt/<int:pk>/result/", views.attempt_result, name="result"),
    path("<slug:slug>/", views.test_detail, name="detail"),
    path("<slug:slug>/start/", views.start_attempt, name="start"),
]
