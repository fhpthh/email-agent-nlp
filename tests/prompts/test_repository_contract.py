"""Verify SQL boundary/parameter contracts; database integration is tested separately."""
from types import SimpleNamespace
from unittest.mock import AsyncMock

import pytest

from src.emailagent.adapters.db.repositories.analysis import AnalysisRepository
from src.emailagent.adapters.db.repositories.search import SearchRepository


@pytest.mark.asyncio
@pytest.mark.parametrize('metric', ['count_tasks', 'count_threads'])
async def test_analytics_uses_exclusive_end_and_category_filter(metric):
    result = SimpleNamespace(mappings=lambda: SimpleNamespace(first=lambda: {}))
    session = SimpleNamespace(execute=AsyncMock(return_value=result))
    await AnalysisRepository(session).get_analytics_summary(metric=metric, category='work')
    query, parameters = session.execute.call_args.args
    sql = str(query)
    assert '< CAST(:date_before' in sql
    assert '<= CAST(:date_before' not in sql
    assert 't.category = CAST(:category' in sql
    assert parameters['category'] == 'work'


@pytest.mark.asyncio
async def test_both_hybrid_search_branches_use_exclusive_end():
    session = SimpleNamespace(execute=AsyncMock(return_value=SimpleNamespace(fetchall=lambda: [])))
    await SearchRepository(session).search_similar_threads(query_embedding=[.1], query_text='budget')
    queries = [str(call.args[0]) for call in session.execute.call_args_list]
    assert len(queries) == 2
    for sql in queries:
        assert 't.last_message_at < CAST' in sql
        assert 't.last_message_at <= CAST' not in sql
