import {expect,it} from 'vitest';
import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {NextIntlClientProvider} from 'next-intl';
import {readFileSync} from 'node:fs';
import {RuntimeLoadStatus} from '@/components/runtime-load-status';
it.each(['en','zh-CN','de'])('shows saved, installed and observed states separately in %s',locale=>{
 const messages=JSON.parse(readFileSync(new URL(`../../src/messages/${locale}.json`,import.meta.url),'utf8'));
 const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale,messages,timeZone:'Asia/Shanghai',children:createElement(RuntimeLoadStatus,{data:{saved_config_status:'saved',installed_mcp_sha256:'a'.repeat(64),mcp_status:'reconnect_required',observed_reply_count:1,observations:[],console_disk_build_id:'web-build'}})}));
 expect(html).toContain(locale==='zh-CN'?'已保存配置':'Saved configuration');
 expect(html).toContain(locale==='zh-CN'?'观测到旧代码':'Old code observed');
 expect(html).toContain('web-build');
 if(locale!=='zh-CN')expect(html).not.toMatch(/[\u3400-\u9fff]/u);
});
