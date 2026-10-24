"""Bounded isolated initialize/list probe. Never performs a knowledge call."""
import json
import subprocess
import threading
import uuid


def probe_stdio(command,env,*,timeout_seconds=15.0):
    result={'schema':'ep.host-diagnostics.v1','probe_id':uuid.uuid4().hex,
            'evidence_kind':'isolated_probe','host_verified':False,'knowledge_calls':0,'provider_calls':0,
            'status':'failed','error_stage':'handshake'}
    requests=[{'jsonrpc':'2.0','id':1,'method':'initialize','params':{'protocolVersion':'2024-11-05',
        'capabilities':{},'clientInfo':{'name':'ep-isolated-probe','version':'1'}}},
        {'jsonrpc':'2.0','method':'notifications/initialized'},
        {'jsonrpc':'2.0','id':2,'method':'tools/list','params':{}}]
    proc=None;threads=[];buffers=[bytearray(),bytearray()];overflow=threading.Event()
    try:
        proc=subprocess.Popen(command,env=env,stdin=subprocess.PIPE,stdout=subprocess.PIPE,stderr=subprocess.PIPE)
        def consume(index,stream):
            while True:
                chunk=stream.read(4096)
                if not chunk:break
                if len(buffers[index])+len(chunk)>1024*1024:
                    overflow.set()
                    try:proc.kill()
                    except OSError:pass
                    break
                buffers[index].extend(chunk)
        for index,stream in enumerate((proc.stdout,proc.stderr)):
            thread=threading.Thread(target=consume,args=(index,stream),daemon=True);thread.start();threads.append(thread)
        proc.stdin.write((''.join(json.dumps(row)+'\n' for row in requests)).encode());proc.stdin.close()
        proc.wait(timeout=max(0.01,min(float(timeout_seconds),15.0)))
        for thread in threads:thread.join(1)
        if overflow.is_set():return {**result,'error_code':'output_budget_exceeded'}
        if proc.returncode:return {**result,'error_code':'process_failed'}
        rows={row['id']:row for row in map(json.loads,bytes(buffers[0]).decode('utf-8').splitlines()) if 'id' in row}
        initialized=rows[1]['result'];tools=rows[2]['result']['tools']
        if not initialized.get('protocolVersion') or not isinstance(tools,list):raise ValueError('invalid_protocol')
        names=[tool['name'] for tool in tools]
        if not all(isinstance(name,str) for name in names) or len(set(names))!=len(names):raise ValueError('invalid_catalog')
        return {**result,'status':'protocol_verified','error_stage':None,'error_code':None,
                'tool_names':names,'listed_tools':len(names),'protocol_version':initialized['protocolVersion']}
    except subprocess.TimeoutExpired:return {**result,'error_code':'timeout'}
    except (OSError,ValueError,TypeError,KeyError):return {**result,'error_code':'invalid_protocol_or_launch'}
    finally:
        if proc is not None:
            if proc.poll() is None:proc.kill()
            proc.wait()
            for thread in threads:thread.join(1)
            for stream in (proc.stdout,proc.stderr):stream.close()
