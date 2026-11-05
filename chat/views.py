import json
import logging

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.http import JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from .context import build_question_context
from .models import ChatMessage, ChatSession
from .providers import (
    ChatProviderError,
    generate_chat_reply,
    is_available,
)

logger = logging.getLogger(__name__)
HISTORY_LIMIT = 20


@login_required
def chat_page(request, pk=None):
    sessions = ChatSession.objects.filter(user=request.user)[:50]
    session, messages = None, []
    if pk:
        session = get_object_or_404(ChatSession, pk=pk, user=request.user)
        messages = [
            {"role": m.role, "content": m.content}
            for m in session.messages.all()
        ]
    ask = None
    if not pk:
        ctx = build_question_context(request.user, request.GET.get("attempt"), request.GET.get("question"))
        if ctx:
            ask = {"label": ctx["label"], "attempt": request.GET["attempt"], "question": request.GET["question"],
                   "prefill": "Why is the correct answer right, and what did I get wrong?"}
    return render(request, "chat/chat.html", {
        "sessions": sessions,
        "session": session,
        "messages_json": messages,
        "ask": ask,
        "configured": is_available(settings.CHAT_AI_PROVIDER),
        "max_chars": settings.CHAT_MAX_MESSAGE_CHARS,
    })


@login_required
@require_POST
def send(request):
    try:
        payload = json.loads(request.body or b"{}")
    except (TypeError, ValueError):
        return JsonResponse({"error": "Invalid request."}, status=400)
    if not isinstance(payload, dict):
        return JsonResponse({"error": "Invalid request."}, status=400)
    message = str(payload.get("message", "")).strip()
    if not message:
        return JsonResponse({"error": "Write a message first."}, status=400)
    if len(message) > settings.CHAT_MAX_MESSAGE_CHARS:
        return JsonResponse({"error": f"Messages can be at most {settings.CHAT_MAX_MESSAGE_CHARS} characters."}, status=400)

    provider = settings.CHAT_AI_PROVIDER

    midnight = timezone.localtime(timezone.now()).replace(hour=0, minute=0, second=0, microsecond=0)
    used = ChatMessage.objects.filter(session__user=request.user, role="user", created_at__gte=midnight).count()
    if used >= settings.CHAT_DAILY_LIMIT:
        return JsonResponse({"error": "You have reached today's message limit. It resets at midnight."}, status=429)

    session = None
    if payload.get("session_id"):
        session = ChatSession.objects.filter(pk=payload["session_id"], user=request.user).first()
        if not session:
            return JsonResponse({"error": "That chat no longer exists."}, status=404)

    context_text = ""
    if not session:
        ctx = build_question_context(request.user, payload.get("attempt"), payload.get("question"))
        if ctx:
            context_text = ctx["text"]

    history = []
    if session:
        recent = list(session.messages.order_by("-id")[:HISTORY_LIMIT])[::-1]
        history = [{"role": m.role, "content": m.api_text} for m in recent]
        while history and history[0]["role"] != "user":
            history.pop(0)
    history.append({"role": "user", "content": f"{context_text}\n\n{message}" if context_text else message})

    try:
        reply, provider_used, _fallback_from = generate_chat_reply(history, provider)
    except ChatProviderError as exc:
        return JsonResponse({"error": str(exc)}, status=502)

    with transaction.atomic():
        if not session:
            session = ChatSession.objects.create(user=request.user, title=message[:60])
        ChatMessage.objects.create(session=session, role="user", content=message, context=context_text)
        ChatMessage.objects.create(
            session=session,
            role="assistant",
            content=reply,
            provider=provider_used,
            model=(
                settings.GROQ_CHAT_MODEL
                if provider_used == "groq"
                else settings.GEMINI_MODEL
            ),
        )
        session.save(update_fields=["updated_at"])
    response_data = {
        "session_id": session.pk,
        "reply": reply,
    }
    return JsonResponse(response_data)


@login_required
@require_POST
def delete(request, pk):
    get_object_or_404(ChatSession, pk=pk, user=request.user).delete()
    return redirect("chat:home")
