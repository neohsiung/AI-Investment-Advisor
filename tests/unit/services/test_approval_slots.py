"""
Tests for the approval slot budget.
核准名額預算的測試。

Context (2026-08-11): `InteractionService.request_approval` polls for up to
300 seconds inside the calling Celery task. Production runs 2 worker
containers at concurrency 2 — four slots — and `sentinel_tick` fires every
minute. Without a budget, four concurrent approvals park every worker for five
minutes and the sentinel stops running, stop-loss checks included.

2026-08-11：request_approval 會在呼叫端的 Celery task 內輪詢最多 300 秒，而
production 僅 4 個並行槽、sentinel_tick 每分鐘觸發。沒有預算限制時，四筆同時
待核准會讓所有 worker 停擺五分鐘，連停損檢查一起停掉。
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch

from src.services.automated_trading_service import _ApprovalSlot


class _FakeRedis:
    """INCR / DECR / EXPIRE / SET over a dict."""

    def __init__(self):
        self.store = {}
        self.expires = {}

    async def incr(self, key):
        self.store[key] = self.store.get(key, 0) + 1
        return self.store[key]

    async def decr(self, key):
        self.store[key] = self.store.get(key, 0) - 1
        return self.store[key]

    async def expire(self, key, seconds):
        self.expires[key] = seconds
        return True

    async def set(self, key, value):
        self.store[key] = value
        return True


def _repo(limit=2):
    repo = MagicMock()
    repo.get.side_effect = lambda uid, key: limit if key == "max_pending_approvals" else None
    return repo


def _patch(redis):
    return patch("src.infrastructure.cache.redis_client.get_redis", AsyncMock(return_value=redis))


@pytest.mark.asyncio
class TestSlotBudget:

    async def test_grants_up_to_the_limit(self):
        redis = _FakeRedis()
        with _patch(redis):
            slots = [_ApprovalSlot("u1", _repo(2)) for _ in range(2)]
            assert all([await s.acquire() for s in slots])

    async def test_refuses_beyond_the_limit(self):
        """
        The fourth concurrent approval must not park the last worker.
        第四筆同時核准不得佔用最後一個 worker。
        """
        redis = _FakeRedis()
        with _patch(redis):
            for _ in range(2):
                await _ApprovalSlot("u1", _repo(2)).acquire()
            assert await _ApprovalSlot("u1", _repo(2)).acquire() is False

    async def test_a_refusal_does_not_consume_a_slot(self):
        """
        A rejected acquire must roll its increment back, or repeated refusals
        would ratchet the counter up and lock the budget out permanently.
        被拒絕的取得必須回滾其遞增，否則反覆被拒會把計數器越推越高，最終永久鎖死。
        """
        redis = _FakeRedis()
        with _patch(redis):
            for _ in range(2):
                await _ApprovalSlot("u1", _repo(2)).acquire()
            for _ in range(5):
                await _ApprovalSlot("u1", _repo(2)).acquire()
            assert redis.store["approval:slots:u1"] == 2

    async def test_release_returns_the_slot(self):
        redis = _FakeRedis()
        with _patch(redis):
            held = _ApprovalSlot("u1", _repo(2))
            await held.acquire()
            await _ApprovalSlot("u1", _repo(2)).acquire()

            assert await _ApprovalSlot("u1", _repo(2)).acquire() is False
            await held.release()
            assert await _ApprovalSlot("u1", _repo(2)).acquire() is True

    async def test_release_is_idempotent(self):
        redis = _FakeRedis()
        with _patch(redis):
            slot = _ApprovalSlot("u1", _repo(2))
            await slot.acquire()
            await slot.release()
            await slot.release()
            assert redis.store["approval:slots:u1"] == 0

    async def test_releasing_an_unheld_slot_is_a_no_op(self):
        """A refused acquire must not release someone else's slot."""
        redis = _FakeRedis()
        with _patch(redis):
            await _ApprovalSlot("u1", _repo(1)).acquire()
            refused = _ApprovalSlot("u1", _repo(1))
            assert await refused.acquire() is False
            await refused.release()
            assert redis.store["approval:slots:u1"] == 1

    async def test_budget_is_per_user(self):
        redis = _FakeRedis()
        with _patch(redis):
            await _ApprovalSlot("u1", _repo(1)).acquire()
            assert await _ApprovalSlot("u2", _repo(1)).acquire() is True

    async def test_key_gets_a_ttl_so_a_killed_worker_returns_its_slot(self):
        redis = _FakeRedis()
        with _patch(redis):
            await _ApprovalSlot("u1", _repo(2)).acquire()
        ttl = redis.expires["approval:slots:u1"]
        assert ttl > 300, "TTL must outlive the 300s approval wait"

    async def test_fails_open_when_redis_is_down(self):
        """
        The budget is a fairness guard, not a safety control. Redis being down
        must not stop the user being asked about a trade.
        此預算是公平性保護而非安全控制；Redis 故障不應讓使用者收不到交易詢問。
        """
        with patch("src.infrastructure.cache.redis_client.get_redis",
                   AsyncMock(side_effect=ConnectionError("redis down"))):
            assert await _ApprovalSlot("u1", _repo(2)).acquire() is True
