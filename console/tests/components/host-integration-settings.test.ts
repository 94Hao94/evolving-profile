import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { NextIntlClientProvider } from 'next-intl';
import { describe,it,expect } from 'vitest';
import en from '../../src/messages/en.json';
import zh from '../../src/messages/zh-CN.json';

const data={schema:'ep.host-discovery.v1',hosts:[{host_id:'workbuddy',labels:{en:'Tencent WorkBuddy','zh-CN':'腾讯 WorkBuddy'},
  status:'observed',installation:{state:'not_installed',candidates:[]},configuration:{state:'unknown',candidates:[]},
  readiness:{capabilities:{prompt_hook:{state:'unknown'},mcp_stdio:{state:'documented'}},host_verified:false,capture_enabled:false}}],
  configuration_write_enabled:false};

describe('host integration settings',()=>{
  it.each(['en','zh-CN'])('does not turn bounded discovery absence into an uninstall claim in %s',async(locale)=>{
    const { HostIntegrationSettings }=await import('../../src/components/host-integration-settings');
    const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale,messages:locale==='en'?en:zh,timeZone:'UTC',
      children:createElement(HostIntegrationSettings,{initialData:data})}));
    expect(html).toContain(locale==='en'?'Not found in checked locations':'检查范围内未发现');
    expect(html).not.toContain(locale==='en'?'Not installed':'未安装');
    expect(html).toContain(locale==='en'?'Unknown':'未知');
    expect(html).toContain('disabled');
    expect(html).toContain(locale==='en'?'existing integrations are unchanged':'已有接入不变');
    expect(html).not.toContain(locale==='en'?'宿主接入':'Host integrations');
  });
});
