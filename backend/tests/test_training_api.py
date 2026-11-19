from concurrent.futures import ThreadPoolExecutor

from fastapi.testclient import TestClient

from backend.main import create_app
from backend.tests.test_matches import register
from backend.training.executor import AlgorithmError


class Decisions:
    async def ready(self):
        return None

    async def bot(self, bot, observation, seed):
        return observation["self"]["direction"]

    async def decide(self, source, observation, memory, **kwargs):
        if memory:
            raise AlgorithmError("runtime", "Ошибка на следующем такте", 2)
        return observation["self"]["direction"], {"used": True}


def test_private_saved_map_and_step_conflict(tmp_path):
    with TestClient(
        create_app(tmp_path / "training.db", executor=Decisions())
    ) as client:
        owner = register(client, "Owner")
        visitor = register(client, "Visitor")
        root = "/api/training"
        draft = {"seed": 4, "cleared": True, "config": {"tick_limit": 4}}
        assert (
            client.post(
                root + "/maps/generate",
                json=draft,
                headers=owner | {"origin": "https://elsewhere.test"},
            ).status_code
            == 403
        )
        saved = client.post(
            root + "/maps",
            headers=owner,
            json={"name": "Карта", "draft": draft, "bots": ["hunter"]},
        )
        assert saved.status_code == 201
        map_id = saved.json()["id"]
        assert client.get(root + "/maps", headers=visitor).json() == []
        start = client.post(
            root + "/runs", headers=owner, json={"map_id": map_id, "source": "fixture"}
        )
        assert start.status_code == 201
        run = root + "/runs/" + start.json()["id"]
        assert client.get(run, headers=visitor).status_code == 404
        assert client.get(run, headers={"cookie": ""}).status_code == 401

        def first_step(_):
            return client.post(run + "/step", headers=owner, json={"expected_tick": 0})

        with ThreadPoolExecutor(max_workers=2) as pool:
            responses = list(pool.map(first_step, range(2)))
        assert sorted(response.status_code for response in responses) == [200, 409]
        assert all(response.json()["arena"]["tick"] == 1 for response in responses)
        second = client.post(run + "/step", headers=owner, json={"expected_tick": 1})
        assert second.json()["error"]["line"] == 2
        assert second.json()["arena"]["tick"] == 2
        restarted = client.post(
            root + "/runs",
            headers=owner,
            json={
                "map_id": map_id,
                "source": "fixture",
                "replace_run": start.json()["id"],
            },
        )
        assert restarted.json()["arena"] == start.json()["arena"]
        assert client.get(run, headers=owner).status_code == 404

        assert client.delete(run, headers=owner).status_code == 204
        restarted_path = root + "/runs/" + restarted.json()["id"]
        assert client.delete(restarted_path, headers=visitor).status_code == 204
        assert client.get(restarted_path, headers=owner).status_code == 200
        assert client.delete(restarted_path, headers=owner).status_code == 204
        assert client.delete(restarted_path, headers=owner).status_code == 204
