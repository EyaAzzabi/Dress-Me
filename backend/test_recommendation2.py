#!/usr/bin/env python3
"""
Test the new RecommendationAgent with LangGraph + ReAct + Critic + RAG
"""
import os
import uuid
import requests
import json
from dotenv import load_dotenv

load_dotenv()

# Use test user ID from database
TEST_USER_ID = "1b451aa0-e8fc-48da-b04c-9be940d68cbc"  # test@dressme.tn
BASE_URL = "http://localhost:8000"
API_PREFIX = os.getenv("API_V1_PREFIX", "/api/v1")

def test_recommendation_api():
    """Test the /api/v1/recommendations/outfits endpoint"""
    
    # Try to get a test token - maybe we can create one
    # For now, let's test the endpoint structure
    headers = {"Content-Type": "application/json"}
    
    # Test payload
    payload = {
        "occasion": "entretien_d_embauche",
        "weather": "ensoleillé",
        "season": "printemps",
        "city": "Tunis",
        "request_text": "J'ai besoin d'une tenue professionnelle pour un entretien"
    }
    
    endpoint = f"{BASE_URL}{API_PREFIX}/recommendations/outfits"
    print(f"Testing recommendation endpoint at {endpoint}")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            endpoint,
            json=payload,
            headers=headers,
            timeout=30
        )
        
        print(f"Status Code: {response.status_code}")
        
        if response.status_code == 200:
            data = response.json()
            print("✓ Success! Response:")
            print(json.dumps(data, indent=2, ensure_ascii=False))
            
            # Check if new fields exist
            if "outfits" in data:
                for i, outfit in enumerate(data["outfits"]):
                    print(f"\n--- Outfit {i+1} ---")
                    print(f"Score: {outfit.get('score')}")
                    print(f"Critic score: {outfit.get('critic_score')}")
                    print(f"ReAct trace: {len(outfit.get('react_trace', []))} steps")
                    print(f"Style guidelines used: {len(outfit.get('style_guidelines_used', []))}")
                    
        elif response.status_code == 401:
            print("✗ Authentication required. Need a valid JWT token.")
            print(f"Response: {response.text}")
        else:
            print(f"✗ Error: {response.status_code}")
            print(f"Response: {response.text}")
            
    except Exception as e:
        print(f"✗ Request failed: {e}")

def test_health():
    """Test health endpoint"""
    try:
        response = requests.get(f"{BASE_URL}/health", timeout=5)
        print(f"Health check: {response.status_code} - {response.json()}")
    except Exception as e:
        print(f"Health check failed: {e}")

def test_docs():
    """Test if API documentation is accessible"""
    try:
        response = requests.get(f"{BASE_URL}/docs", timeout=10)
        print(f"\nAPI Docs available at: {BASE_URL}/docs (Status: {response.status_code})")
    except Exception as e:
        print(f"✗ Cannot access docs: {e}")

if __name__ == "__main__":
    print("=" * 60)
    print("Testing RecommendationAgent (LangGraph + ReAct + Critic + RAG)")
    print("=" * 60)
    
    test_health()
    test_docs()
    print("\n" + "-" * 40)
    test_recommendation_api()