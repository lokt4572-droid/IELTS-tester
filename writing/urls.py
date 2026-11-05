from django.urls import path

from . import views

app_name = "writing"

urlpatterns = [
    path("", views.test_list, name="list"),
    path("attempt/<int:pk>/", views.attempt_page, name="attempt"),
    path("attempt/<int:pk>/save/", views.attempt_save, name="save"),
    path("attempt/<int:pk>/submit/", views.attempt_submit, name="submit"),
    path("attempt/<int:pk>/evaluate/", views.evaluate_attempt_response, name="evaluate"),
    path("attempt/<int:pk>/result/", views.attempt_result, name="result"),
    path("attempt/<int:pk>/preview/", views.attempt_preview, name="attempt_preview"),
    path("<slug:slug>/", views.test_detail, name="detail"),
    path("<slug:slug>/start/", views.start_attempt, name="start"),
]
