from config.settings import settings

print("=== Config check ===")
print("GEMINI_API_KEY loaded:", bool(settings.GEMINI_API_KEY), "| length:", len(settings.GEMINI_API_KEY))
print("GEMINI_MODEL:", settings.GEMINI_MODEL)
print("GROQ_API_KEY loaded:", bool(settings.GROQ_API_KEY), "| length:", len(settings.GROQ_API_KEY))
print("GROQ_MODEL:", settings.GROQ_MODEL)
print()

print("=== Testing Gemini directly ===")
try:
    import google.generativeai as genai
    genai.configure(api_key=settings.GEMINI_API_KEY)
    model = genai.GenerativeModel(settings.GEMINI_MODEL)
    response = model.generate_content("Say hello in 5 words.")
    print("SUCCESS:", response.text)
except Exception as exc:
    print("FAILED:", type(exc).__name__, "-", exc)

print()
print("=== Testing Groq directly ===")
try:
    import httpx
    resp = httpx.post(
        "https://api.groq.com/openai/v1/chat/completions",
        headers={"Authorization": f"Bearer {settings.GROQ_API_KEY}"},
        json={
            "model": settings.GROQ_MODEL,
            "messages": [{"role": "user", "content": "Say hello in 5 words."}],
        },
        timeout=15,
    )
    print("HTTP status:", resp.status_code)
    print("Response body:", resp.text[:500])
except Exception as exc:
    print("FAILED:", type(exc).__name__, "-", exc)