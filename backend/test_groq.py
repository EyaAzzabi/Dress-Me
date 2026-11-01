#!/usr/bin/env python
"""Test Groq LLM integration"""

from app.agents.llm_agent import LLMAgent
from app.core.config import get_settings

settings = get_settings()
print(f"LLM Provider: {settings.llm_provider}")
print(f"LLM Model: {settings.llm_model}")
print()

llm = LLMAgent()
result = llm.parse_occasion('un mariage', {'season': 'ete'})

if result:
    print("✓ LLM Works!")
    print(f"  Category: {result.get('occasion_category')}")
    print(f"  Formality: {result.get('formality')}")
    print(f"  Dress Code: {result.get('dress_code')}")
else:
    print("✗ LLM failed (fell back to rules)")
