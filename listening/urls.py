from django.urls import path

from . import views

app_name = "listening"

urlpatterns = [
    path("", views.test_list, name="list"),
    path("attempt/<int:pk>/", views.attempt_page, name="attempt"),
    path("attempt/<int:pk>/save/", views.attempt_save, name="save"),
    path("attempt/<int:pk>/submit/", views.attempt_submit, name="submit"),
    path("attempt/<int:pk>/result/", views.attempt_result, name="result"),
    path("attempt/<int:pk>/exam/begin/", views.exam_begin, name="exam_begin"),
    path("attempt/<int:pk>/exam/state/", views.exam_state, name="exam_state"),
    path(
        "attempt/<int:pk>/sound-check/",
        views.sound_check,
        name="sound_check",
    ),
    path(
        "attempt/<int:pk>/sound-check/start/",
        views.confirm_sound_check,
        name="confirm_sound_check",
    ),
    path("<slug:slug>/", views.test_detail, name="detail"),
    path("<slug:slug>/start/", views.start_attempt, name="start"),
]
