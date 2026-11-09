"""Bounded metadata discovery. Never launches clients or reads their conversations."""
import copy
import hashlib
import json
import os
import platform
import plistlib
import sys
import time
from pathlib import Path
from .readiness import readiness

_CACHE={}


def _windows_app_metadata():
    """Read bounded standard uninstall metadata, never commands or client data."""
    import winreg
    rows=[];started=time.monotonic();count=0;limited=False;opened=False
    subkey=r'Software\Microsoft\Windows\CurrentVersion\Uninstall'
    for hive_name in ('HKEY_CURRENT_USER','HKEY_LOCAL_MACHINE'):
        for view in (winreg.KEY_WOW64_64KEY,winreg.KEY_WOW64_32KEY):
            if count>=512 or time.monotonic()-started>2:limited=True;break
            try:
                with winreg.OpenKey(getattr(winreg,hive_name),subkey,0,winreg.KEY_READ|view) as parent:
                    opened=True
                    for index in range(512-count):
                        if time.monotonic()-started>2:limited=True;break
                        try:name=winreg.EnumKey(parent,index)
                        except OSError as exc:
                            if getattr(exc,'winerror',None)!=259:limited=True
                            break
                        count+=1
                        try:
                            with winreg.OpenKey(parent,name,0,winreg.KEY_READ|view) as entry:
                                values={}
                                for key in ('DisplayName','DisplayVersion','InstallLocation'):
                                    try:
                                        value,kind=winreg.QueryValueEx(entry,key)
                                        if kind in (winreg.REG_SZ,winreg.REG_EXPAND_SZ) and isinstance(value,str):
                                            values[key]=value[:1024]
                                    except FileNotFoundError:pass
                                    except OSError:limited=True
                                if values.get('DisplayName'):
                                    rows.append({'display_name':values['DisplayName'],'version':values.get('DisplayVersion','unknown'),
                                                 'location':values.get('InstallLocation',''),
                                                 'registry_key':f'{hive_name}/{view}/{subkey}/{name}'})
                        except FileNotFoundError:continue
                        except OSError:limited=True;continue
                    if count>=512:limited=True
            except FileNotFoundError:continue
            except OSError:limited=True;continue
    return rows,'limited' if limited else 'observed' if opened else 'unavailable'


def native_environment(*,include_apps=True):
    system='macos' if sys.platform=='darwin' else 'windows' if os.name=='nt' else 'linux'
    mode='wsl' if os.environ.get('WSL_INTEROP') or os.environ.get('WSL_DISTRO_NAME') else 'local'
    result={'platform':system,'architecture':platform.machine(),'home':str(Path.home()),'mode':mode,
            'search_roots':os.get_exec_path()}
    if system=='windows' and include_apps:
        result['windows_apps'],result['windows_registry_status']=_windows_app_metadata()
    return result


def _candidate_paths(profile, environment, override):
    home=Path(environment['home']);system=environment['platform'];paths=[]
    if system=='macos':
        paths.extend(('app',Path(a['path']),a) for a in profile.get('apps',[]))
    for name in profile.get('executables',[]):
        for root in environment.get('search_roots',[]):
            for suffix in (('.exe','.cmd','.bat','') if system=='windows' else ('',)):
                paths.append(('executable',Path(root)/(name+suffix),{}))
    paths.extend(('config',home/rel,{}) for rel in profile.get('config',{}).get('paths',{}).get(system,[]))
    for kind in ('app','executable','config'):
        paths.extend((kind,Path(p),{}) for p in override.get(kind,[]))
    return paths[:32],len(paths)>32


def discover_hosts(registry, environment=None, overrides=None):
    environment=dict(environment or native_environment());overrides=overrides or {}
    started=time.monotonic();hosts=[]
    for profile in registry['profiles']:
        candidates,truncated=_candidate_paths(profile,environment,overrides.get(profile['id'],{}))
        stamps=[]
        for kind,path,_ in candidates:
            try:
                s=path.stat();stamps.append((kind,str(path),s.st_mtime_ns,s.st_size))
            except OSError:stamps.append((kind,str(path),None))
            if kind=='app':
                try:
                    info=(path/'Contents/Info.plist').stat();stamps.append(('app_metadata',str(path),info.st_mtime_ns,info.st_size))
                except OSError:pass
        key=hashlib.sha256(json.dumps([profile,environment,stamps],sort_keys=True).encode()).hexdigest()
        cached=_CACHE.get(key)
        if not overrides.get('bypass_cache') and cached and time.monotonic()-cached[0]<30:
            hosts.append(copy.deepcopy(cached[1]));continue
        installed=[];configs=[];limited=truncated
        if environment['platform']=='windows':
            aliases={name.strip().casefold() for name in profile.get('windows_display_names',[])}
            limited=limited or environment.get('windows_registry_status') in ('limited','unavailable')
            for app in environment.get('windows_apps',[])[:512]:
                if str(app.get('display_name','')).strip().casefold() not in aliases:continue
                installed.append({'kind':'windows_registry_candidate','display_name':app['display_name'],
                                  'version':app.get('version','unknown'),'executed':False,
                                  'path':app.get('location') or app.get('registry_key') or app['display_name']})
        for kind,path,metadata in candidates:
            if time.monotonic()-started>5:limited=True;break
            if path.is_symlink():continue
            if kind=='config':
                if path.is_file():configs.append({'path':str(path),'content_read':False})
                continue
            if kind=='app':
                info=path/'Contents/Info.plist'
                try:
                    if info.is_symlink() or info.stat().st_size>128*1024:continue
                    data=plistlib.loads(info.read_bytes())
                    if metadata.get('bundle_id') and data.get('CFBundleIdentifier')!=metadata['bundle_id']:continue
                    installed.append({'kind':'app','path':str(path),'version':str(data.get('CFBundleShortVersionString') or 'unknown'),
                                      'bundle_id':data.get('CFBundleIdentifier')})
                except (OSError,ValueError,TypeError):continue
            elif path.is_file():installed.append({'kind':'executable_candidate','path':str(path),'version':'unknown','executed':False})
        unique={r['path']:r for r in installed};installed=list(unique.values())
        installation='ambiguous' if len(installed)>1 else 'detected' if installed else 'not_installed' if candidates and not limited else 'unknown'
        context={'platform':environment['platform'],'mode':environment.get('mode','local'),
                 'host_version':installed[0]['version'] if len(installed)==1 else 'unknown',
                 'adapter_revision':registry.get('sha256',registry.get('revision','unknown')),
                 'config_sha256':hashlib.sha256(json.dumps([s for s in stamps if s[0]=='config'],sort_keys=True).encode()).hexdigest(),
                 'config_fingerprint_kind':'candidate_metadata_not_file_content'}
        row={'host_id':profile['id'],'labels':profile.get('labels',{}),'status':'limited' if limited else 'observed',
             'context':context,'installation':{'state':installation,'candidates':installed,'scope':'bounded_candidates'},
             'configuration':{'state':'present' if configs else 'absent' if profile.get('config',{}).get('paths',{}).get(environment['platform']) else 'unknown','candidates':configs},
             'readiness':readiness(profile,[],context),'limited':limited}
        if len(_CACHE)>=128:_CACHE.pop(next(iter(_CACHE)))
        _CACHE[key]=(time.monotonic(),copy.deepcopy(row));hosts.append(row)
    return {'schema':'ep.host-discovery.v1','environment':{k:v for k,v in environment.items() if k not in ('home','search_roots','windows_apps')},'hosts':hosts}
