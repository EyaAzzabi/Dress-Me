#!/usr/bin/env python3
"""
Create a test user and test the recommendation endpoint
"""
import requests
import json
import uuid

BASE_URL = 'http://localhost:8000/api/v1'

# Create a unique test user with valid domain
test_email = f'test_{uuid.uuid4().hex[:8]}@example.com'
test_password = 'test123456'
test_name = 'Test User'

print(f'Creating test user: {test_email}')
print(f'Password: {test_password}')

# Register
try:
    response = requests.post(
        f'{BASE_URL}/auth/register',
        json={
            'email': test_email,
            'password': test_password,
            'full_name': test_name
        },
        timeout=10
    )
    
    if response.status_code == 201:
        print(f'✓ User created: {response.json()}')
        
        # Now login to get token
        login_response = requests.post(
            f'{BASE_URL}/auth/login',
            json={'email': test_email, 'password': test_password},
            timeout=10
        )
        
        if login_response.status_code == 200:
            token = login_response.json()['access_token']
            print(f'\n✓ Login successful!')
            print(f'Token: {token}')
            print(f'\nUse this for testing:')
            print(f'Email: {test_email}')
            print(f'Password: {test_password}')
            print(f'Authorization: Bearer {token}')
            
            # Test the recommendation endpoint
            print(f'\nTesting recommendation endpoint...')
            headers = {'Authorization': f'Bearer {token}', 'Content-Type': 'application/json'}
            payload = {
                'occasion': 'entretien_d_embauche',
                'weather': 'ensoleillé',
                'season': 'printemps',
                'city': 'Tunis',
                'request_text': 'Test de l\'agent recommendation'
            }
            
            rec_response = requests.post(
                f'{BASE_URL}/recommendations/outfits',
                json=payload,
                headers=headers,
                timeout=30
            )
            
            print(f'Recommendation status: {rec_response.status_code}')
            if rec_response.status_code == 200:
                data = rec_response.json()
                print(f'✓ Success! Got {len(data.get("outfits", []))} outfits')
                
                # Check for new fields
                for i, outfit in enumerate(data.get('outfits', [])):
                    print(f'\nOutfit {i+1}:')
                    print(f'  - Score: {outfit.get("score")}')
                    print(f'  - Critic score: {outfit.get("critic_score")}')
                    print(f'  - ReAct trace steps: {len(outfit.get("react_trace", []))}')
                    print(f'  - Style guidelines: {len(outfit.get("style_guidelines_used", []))}')
                    
                    # Show some ReAct trace if available
                    react_trace = outfit.get('react_trace', [])
                    if react_trace:
                        print(f'  - ReAct example step: {react_trace[0].get("thought", "N/A")[:100]}...')
                        
            else:
                print(f'✗ Error: {rec_response.text}')
                
        else:
            print(f'✗ Login failed: {login_response.status_code} - {login_response.text}')
            
    else:
        print(f'✗ Registration failed: {response.status_code} - {response.text}')
        
except Exception as e:
    print(f'✗ Error: {e}')