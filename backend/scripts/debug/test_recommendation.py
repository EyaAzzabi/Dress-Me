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

def test_recommendation_api():
    """Test the /recommendations/outfits endpoint"""
    
    # First, we need to authenticate. Let's check if we can use a test token
    # For simplicity, we'll check if there's a test token in .env
    test_token = os.getenv("TEST_TOKEN")
    
    if not test_token:
        print("⚠ No test token found. Checking if we can use basic auth...")
        # Try without auth first to see response
        headers = {"Content-Type": "application/json"}
    else:
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {test_token}"
        }
    
    # Test payload
    payload = {
        "occasion": "entretien_d_embauche",
        "weather": "ensoleillé",
        "season": "printemps",
        "city": "Tunis",
        "request_text": "J'ai besoin d'une tenue professionnelle pour un entretien"
    }
    
    print(f"Testing recommendation endpoint at {BASE_URL}/recommendations/outfits")
    print(f"Payload: {json.dumps(payload, indent=2)}")
    
    try:
        response = requests.post(
            f"{BASE_URL}/recommendations/outfits",
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
    
    test_docs()
    print("\n" + "-" * 40)
    test_recommendation_api()