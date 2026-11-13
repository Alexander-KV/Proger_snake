from fastapi.testclient import TestClient
from backend.main import create_app


def test_registration_session_and_logout(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as client:
        response = client.post('/api/auth/register', json={'username': 'Snake_1', 'name': '123', 'password': '1234'})
        assert response.status_code == 201
        assert client.get('/api/auth/me').json()['name'] == '123'
        assert client.post('/api/auth/logout').status_code == 204
        assert client.get('/api/auth/me').status_code == 401
        assert client.post('/api/auth/login', json={'username': 'snake_1', 'password': '1234'}).status_code == 200


def test_validation_and_unique_username(tmp_path):
    with TestClient(create_app(tmp_path / 'test.db')) as client:
        assert client.post('/api/auth/register', json={'username': 'bad name', 'name': '123', 'password': '1234'}).status_code == 422
        assert client.post('/api/auth/register', json={'username': 'snake', 'name': 'abc', 'password': '1234'}).status_code == 422
        assert client.post('/api/auth/register', json={'username': 'snake', 'name': '123', 'password': '1234'}).status_code == 201
        assert client.post('/api/auth/register', json={'username': 'SNAKE', 'name': '456', 'password': '1234'}).status_code == 409
        assert client.post('/api/auth/login', json={'username': 'snake', 'password': 'wrong'}).status_code == 401
