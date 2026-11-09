import hashlib
from contextlib import asynccontextmanager
import asyncio
import httpx
import pytest

TOKEN='synthetic-test-token-not-a-secret'


def settings():
    return {'token_hashes':{hashlib.sha256(TOKEN.encode()).hexdigest():{'owner_id':'a','host_id':'workbuddy','installation_id':'one'}},
            'allowed_hosts':['testserver'],'allowed_origins':['http://testserver']}


@asynccontextmanager
async def factory(scope,launch):
    class Worker:
        async def list_tools(self):return [{'name':'user_recall','description':'synthetic echo','inputSchema':{'type':'object','properties':{}}},
                                           {'name':'promote_agent_process_memory','inputSchema':{'type':'object'}}]
        async def call_tool(self,name,arguments):return {'content':[{'type':'text','text':scope['owner_id']}],'isError':False}
    yield Worker()


@pytest.mark.asyncio
async def test_requires_authentication_even_loopback_and_origin_policy():
    from lib.host_integration.http_transport import create_governed_http_app
    app=create_governed_http_app(settings(),factory)
    async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
        assert (await client.post('/mcp',json={})).status_code==401
        headers={'Authorization':'Bearer '+TOKEN,'Origin':'http://evil.invalid'}
        assert (await client.post('/mcp',headers=headers,json={})).status_code==403
        assert (await client.post('/mcp',headers={'Authorization':'Bearer '+TOKEN,'Host':'evil.invalid'},json={})).status_code==403


@pytest.mark.asyncio
async def test_two_owners_never_share_stdio_state_and_direct_disabled_call_denied():
    from lib.host_integration.http_transport import GovernedSessionPool
    pool=GovernedSessionPool(factory,{},idle_timeout=0.2)
    try:
        a={'owner_id':'a','host_id':'workbuddy','installation_id':'one'}
        b={'owner_id':'b','host_id':'workbuddy','installation_id':'one'}
        result=await pool.call(a,'same-session','user_recall',{})
        other=await pool.call(b,'same-session','user_recall',{})
        assert result['content'][0]['text']=='a' and other['content'][0]['text']=='b'
        with pytest.raises(PermissionError):await pool.call(a,'same-session','promote_agent_process_memory',{})
        assert len(await pool.list_tools(a,'same-session'))==1
    finally:await pool.close()


@pytest.mark.asyncio
async def test_timeout_disconnect_cleans_worker():
    from lib.host_integration.http_transport import GovernedSessionPool
    closed=[]
    @asynccontextmanager
    async def slow(scope,launch):
        class Worker:
            async def call_tool(self,*args):await asyncio.sleep(5)
        try:yield Worker()
        finally:closed.append(True)
    pool=GovernedSessionPool(slow,{},request_timeout=0.02)
    with pytest.raises(TimeoutError):await pool.call({'owner_id':'a'},'session','user_recall',{})
    await pool.close()
    assert closed==[True]


def test_no_auth_configuration_and_remote_bind_are_not_silently_enabled():
    from lib.host_integration.http_transport import create_governed_http_app
    with pytest.raises(ValueError):create_governed_http_app({},factory)
    with pytest.raises(ValueError):create_governed_http_app({**settings(),'bind_host':'0.0.0.0'},factory)


def test_mixed_data_owners_cannot_share_one_core_launch():
    from lib.host_integration.http_transport import create_governed_http_app
    s=settings();s['token_hashes'][hashlib.sha256(b'synthetic-other').hexdigest()]={'owner_id':'b','host_id':'doubao_work','installation_id':'two'}
    with pytest.raises(ValueError,match='single_owner'):create_governed_http_app(s,factory)


@pytest.mark.asyncio
async def test_closed_sessions_do_not_permanently_exhaust_admission():
    from lib.host_integration.http_transport import create_governed_http_app
    app=create_governed_http_app(settings(),factory)
    headers={'Authorization':'Bearer '+TOKEN,'Accept':'application/json, text/event-stream'}
    payload={'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05',
             'capabilities':{},'clientInfo':{'name':'synthetic-session-test','version':'1'}}}
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver') as client:
            for index in range(66):
                initialized=await client.post('/mcp',headers=headers,json=payload)
                assert initialized.status_code==200,index
                sid=initialized.headers['mcp-session-id']
                closed=await client.delete('/mcp',headers={**headers,'mcp-session-id':sid})
                assert closed.status_code==200
            assert len(app.session_owners)==0


@pytest.mark.asyncio
async def test_standard_http_handshake_catalog_and_call_with_isolated_worker():
    from lib.host_integration.http_transport import create_governed_http_app
    from mcp.client.session import ClientSession
    from mcp.client.streamable_http import streamable_http_client
    app=create_governed_http_app(settings(),factory)
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(transport=httpx.ASGITransport(app=app),base_url='http://testserver',
                                     headers={'Authorization':'Bearer '+TOKEN}) as http:
            async with streamable_http_client('http://testserver/mcp',http_client=http) as (read,write):
                async with ClientSession(read,write) as session:
                    await session.initialize()
                    listed=await session.list_tools()
                    assert [t.name for t in listed.tools]==['user_recall']
                    result=await session.call_tool('user_recall',{})
                    assert result.content[0].text=='a'
                    denied=await session.call_tool('promote_agent_process_memory',{})
                    assert denied.model_dump(by_alias=True)['isError'] is True
