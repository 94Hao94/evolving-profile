"""Optional standard HTTP MCP over isolated, governed EP stdio sessions."""
import asyncio
from contextlib import asynccontextmanager,suppress
import hashlib
import hmac
import json
import os
import re
import time
from urllib.parse import urlsplit
from .policy import authorize_tool_call,filter_tools


@asynccontextmanager
async def open_governed_session(authenticated_scope,launch):
    from fastmcp import Client
    config=dict(launch)
    config['env']={**os.environ,**config.get('env',{}),
        'EVOLVING_PROFILE_HOST_ID':authenticated_scope['host_id'],
        'EVOLVING_PROFILE_INSTALLATION_ID':authenticated_scope['installation_id'],
        'EVOLVING_PROFILE_OWNER_ID':authenticated_scope['owner_id'],
        'PYTHONUTF8':'1','PYTHONIOENCODING':'utf-8',
        'EVOLVING_PROFILE_ACCESS_MODE':'read-only'}
    async with Client({'mcpServers':{'ep':config}},timeout=30,init_timeout=15) as client:
        class Worker:
            async def list_tools(self):return [tool.model_dump(by_alias=True) for tool in await client.list_tools()]
            async def call_tool(self,name,arguments):
                result=await client.call_tool(name,arguments,raise_on_error=False)
                return {'content':[c.model_dump(by_alias=True) for c in result.content],
                        'structuredContent':result.structured_content,'isError':result.is_error}
        yield Worker()


class _SessionActor:
    def __init__(self,factory,scope,launch,idle):
        self.queue=asyncio.Queue();self.factory=factory;self.scope=scope;self.launch=launch;self.idle=idle
        self.task=asyncio.create_task(self._run())

    async def _run(self):
        current=None
        try:
            async with self.factory(self.scope,self.launch) as worker:
                while True:
                    current=await asyncio.wait_for(self.queue.get(),self.idle)
                    method,args,future=current
                    if future.cancelled():continue
                    try:result=await getattr(worker,method)(*args)
                    except Exception as exc:
                        if not future.done():future.set_exception(exc)
                    else:
                        if not future.done():future.set_result(result)
                    current=None
        except (asyncio.CancelledError,TimeoutError):pass
        except Exception as exc:
            if current and not current[2].done():current[2].set_exception(exc)
        finally:
            if current and not current[2].done():current[2].set_exception(RuntimeError('session_closed'))
            while not self.queue.empty():
                _,_,future=self.queue.get_nowait()
                if not future.done():future.set_exception(RuntimeError('session_closed'))

    async def invoke(self,method,args,timeout):
        future=asyncio.get_running_loop().create_future();await self.queue.put((method,args,future))
        try:return await asyncio.wait_for(future,timeout)
        except BaseException:
            await self.close();raise

    async def close(self):
        self.task.cancel()
        with suppress(asyncio.CancelledError):await self.task


class GovernedSessionPool:
    def __init__(self,factory,launch,*,idle_timeout=60,request_timeout=30):
        self.factory=factory;self.launch=launch;self.idle=idle_timeout;self.timeout=request_timeout;self.actors={}

    def _actor(self,scope,session):
        if not scope.get('owner_id') or not isinstance(session,str) or not session or len(session)>256:
            raise PermissionError('authenticated_session_required')
        for key,actor in list(self.actors.items()):
            if actor.task.done():self.actors.pop(key)
        key=(scope['owner_id'],scope.get('host_id'),scope.get('installation_id'),session)
        if key not in self.actors:
            if len(self.actors)>=4 or sum(k[0]==key[0] for k in self.actors)>=2:raise RuntimeError('session_capacity_exceeded')
            self.actors[key]=_SessionActor(self.factory,dict(scope),self.launch,self.idle)
        return self.actors[key]

    async def list_tools(self,scope,session):
        return filter_tools(await self._actor(scope,session).invoke('list_tools',(),self.timeout),scope)

    async def call(self,scope,session,name,arguments):
        authorize_tool_call(name,arguments,scope)
        return await self._actor(scope,session).invoke('call_tool',(name,arguments),self.timeout)

    async def close(self):
        await asyncio.gather(*(a.close() for a in self.actors.values()),return_exceptions=True)
        self.actors.clear()

    async def close_session(self,scope,session):
        key=(scope['owner_id'],scope.get('host_id'),scope.get('installation_id'),session)
        actor=self.actors.pop(key,None)
        if actor is not None:await actor.close()


def create_governed_http_app(settings,session_factory=open_governed_session):
    from fastmcp import FastMCP
    from fastmcp.server.providers import Provider
    from fastmcp.server.dependencies import get_http_request
    from fastmcp.tools import Tool,ToolResult
    from mcp.types import CallToolResult
    from starlette.responses import JSONResponse
    tokens=settings.get('token_hashes',{})
    if not tokens or not all(re.fullmatch('[0-9a-f]{64}',key) for key in tokens):raise ValueError('token_hashes_required')
    if settings.get('bind_host','127.0.0.1') not in ('127.0.0.1','localhost','::1'):raise ValueError('remote_bind_requires_separate_review')
    for scope in tokens.values():
        if not all(scope.get(k) for k in ('owner_id','host_id','installation_id')):raise ValueError('invalid_authenticated_scope')
    # The configured launch addresses one EP data core. Distinct actor processes
    # do not create distinct Bank authorization. Multiple hosts may share its
    # owner; other owners must use separately governed core launches.
    if len({scope['owner_id'] for scope in tokens.values()})!=1:raise ValueError('single_owner_gateway_required')
    pool=GovernedSessionPool(session_factory,settings.get('launch',{}))
    def request_scope():
        request=get_http_request()
        return request.state.ep_scope,request.headers.get('mcp-session-id','')
    class ProxyTool(Tool):
        async def run(self,arguments):
            scope,session=request_scope();result=await pool.call(scope,session,self.name,arguments)
            parsed=CallToolResult.model_validate(result)
            values=parsed.model_dump(by_alias=True)
            return ToolResult(content=parsed.content,structured_content=values.get('structuredContent'),is_error=values.get('isError',False))
    class ProxyProvider(Provider):
        async def get_tasks(self):return []
        async def _list_tools(self):
            scope,session=request_scope()
            return [ProxyTool(name=row['name'],description=row.get('description'),parameters=row.get('inputSchema',{'type':'object'}))
                    for row in await pool.list_tools(scope,session)]
    @asynccontextmanager
    async def lifespan(server):
        try:yield {}
        finally:await pool.close()
    server=FastMCP('evolving_profile_controller',providers=[ProxyProvider()],lifespan=lifespan,cache_ttl=None)
    app=server.http_app(path='/mcp',transport='streamable-http',json_response=True,
                       stateless_http=False,session_idle_timeout=60,
                       allowed_hosts=settings.get('allowed_hosts',['127.0.0.1','localhost']),
                       allowed_origins=settings.get('allowed_origins',[]))
    class AuthenticatedApp:
        def __init__(self):self.router=app.router;self.session_owners={};self.session_touched={};self.pool=pool
        async def forget_session(self,sid):
            owner=self.session_owners.pop(sid,None);self.session_touched.pop(sid,None)
            if owner is not None:
                await pool.close_session(dict(zip(('owner_id','host_id','installation_id'),owner)),sid)
        async def __call__(self,scope,receive,send):
            if scope['type']!='http':return await app(scope,receive,send)
            headers={k.decode().lower():v.decode() for k,v in scope.get('headers',[])}
            authority=headers.get('host','');host=urlsplit('//'+authority).hostname
            if host not in settings.get('allowed_hosts',['127.0.0.1','localhost']):
                return await JSONResponse({'error':'host_rejected'},status_code=403)(scope,receive,send)
            origin=headers.get('origin')
            if origin and origin not in settings.get('allowed_origins',[]):
                return await JSONResponse({'error':'origin_rejected'},status_code=403)(scope,receive,send)
            authorization=headers.get('authorization','')
            digest=hashlib.sha256(authorization[7:].encode()).hexdigest() if authorization.startswith('Bearer ') else ''
            authorized=next((v for k,v in tokens.items() if hmac.compare_digest(k,digest)),None)
            if authorized is None:return await JSONResponse({'error':'authentication_required'},status_code=401)(scope,receive,send)
            now=time.monotonic()
            for old,touched in list(self.session_touched.items()):
                if now-touched>=60:await self.forget_session(old)
            sid=headers.get('mcp-session-id');owner=(authorized['owner_id'],authorized['host_id'],authorized['installation_id'])
            if sid and sid not in self.session_owners:
                return await JSONResponse({'error':'session_unknown_or_expired'},status_code=404)(scope,receive,send)
            if sid and self.session_owners[sid]!=owner:
                return await JSONResponse({'error':'session_owner_mismatch'},status_code=403)(scope,receive,send)
            if sid:self.session_touched[sid]=now
            if not sid and len(self.session_owners)>=64:
                return await JSONResponse({'error':'session_capacity_exceeded'},status_code=429)(scope,receive,send)
            scope.setdefault('state',{})['ep_scope']=dict(authorized)
            response_status=0
            async def wrapped(message):
                nonlocal response_status
                if message['type']=='http.response.start':
                    response_status=message['status']
                    for key,value in message.get('headers',[]):
                        if key.lower()==b'mcp-session-id' and 200<=response_status<300:
                            self.session_owners[value.decode()]=owner;self.session_touched[value.decode()]=time.monotonic()
                await send(message)
            await app(scope,receive,wrapped)
            if sid and scope.get('method')=='DELETE' and response_status in (200,202,204,404):
                await self.forget_session(sid)
    return AuthenticatedApp()
