from django.contrib.auth import login
from django.contrib.auth.decorators import login_required
from django.shortcuts import redirect, render

from reading.models import Attempt

from .forms import SignupForm
from .modules import MODULES


def home(request):
    return render(request, "core/home.html", {"modules": MODULES})


def tests_hub(request):
    return render(request, "core/tests_hub.html", {"modules": MODULES})


def signup(request):
    if request.user.is_authenticated:
        return redirect("dashboard")
    form = SignupForm(request.POST or None)
    if request.method == "POST" and form.is_valid():
        user = form.save()
        login(request, user)
        return redirect("dashboard")
    return render(request, "registration/signup.html", {"form": form})


@login_required
def dashboard(request):
    finished = list(
        Attempt.objects.filter(user=request.user, finished_at__isnull=False)
        .select_related("test")
        .order_by("-finished_at")
    )
    bands = [a.band for a in finished if a.band is not None]
    stats = {
        "count": len(finished),
        "best": max(bands) if bands else None,
        "average": round(sum(bands) / len(bands) * 2) / 2 if bands else None,
    }
    trend = [
        {"attempt": a, "width": int(float(a.band) / 9 * 100)}
        for a in reversed(finished[:10])
        if a.band is not None
    ]
    unfinished = (
        Attempt.objects.filter(user=request.user, finished_at__isnull=True)
        .select_related("test")
        .order_by("-started_at")
        .first()
    )
    if unfinished and unfinished.is_expired():
        unfinished = None
    return render(
        request,
        "core/dashboard.html",
        {"attempts": finished[:20], "stats": stats, "trend": trend, "unfinished": unfinished},
    )
