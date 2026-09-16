#!/usr/bin/env python3
"""Test API endpoints"""

import requests
import json

BASE_URL = "http://localhost:4000/api"

def test_health():
    """Test health endpoint"""
    print("=== Test Health Endpoint ===")
    resp = requests.get(f"{BASE_URL}/health")
    print(f"Status: {resp.status_code}")
    print(f"Response: {resp.json()}")
    print()

def test_login():
    """Test login endpoint"""
    print("=== Test Login Endpoint ===")
    payload = {
        "email": "admin@hvktcnan.edu.vn",
        "password": "Demo@2026"
    }
    resp = requests.post(f"{BASE_URL}/auth/login", json=payload)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        user = data.get('user', {})
        print(f"Login thanh cong! User: {user.get('email', 'N/A')}")
        role = user.get('role', {})
        print(f"Role: {role.get('name', 'N/A') if isinstance(role, dict) else role}")
        token = data.get('accessToken', '')
        print(f"Access token: {token[:50]}..." if token else "No token")
        return token
    else:
        print(f"Loi: {resp.text}")
    print()
    return None

def test_documents(token):
    """Test documents endpoint"""
    print("=== Test Documents Endpoint ===")
    headers = {"Authorization": f"Bearer {token}"} if token else {}
    resp = requests.get(f"{BASE_URL}/documents?type=QUYCHE&limit=3", headers=headers)
    print(f"Status: {resp.status_code}")
    if resp.status_code == 200:
        data = resp.json()
        print(f"So tai lieu: {len(data.get('items', []))}")
        for doc in data.get('items', [])[:3]:
            print(f"  - {doc.get('name')} ({doc.get('type')})")
    else:
        print(f"Response: {resp.text[:200]}")
    print()

if __name__ == "__main__":
    test_health()
    token = test_login()
    if token:
        test_documents(token)
