import {createElement} from 'react';
import {renderToStaticMarkup} from 'react-dom/server';
import {NextIntlClientProvider} from 'next-intl';
import {it,expect} from 'vitest';
import {PromptSourceEmpty,PromptOriginBadge} from '@/components/prompt-source-summary';
import en from '@/messages/en.json';
import zh from '@/messages/zh-CN.json';

function render(locale:string,messages:any,counts:any,source='natural'){
 return renderToStaticMarkup(createElement(NextIntlClientProvider,{locale,messages,timeZone:'Asia/Shanghai',children:createElement(PromptSourceEmpty,{counts,source,onBrowse:()=>{}})}));
}
it.each([{locale:'en',messages:en,pending:'Source verification is incomplete',button:'View all audit records'},
 {locale:'zh-CN',messages:zh,pending:'来源仍在核验',button:'查看全部审计记录'}])('pending source evidence is actionable, not an empty-history conclusion ($locale)',({locale,messages,pending,button})=>{
 const html=render(locale,messages,{natural:0,audit:1998,verification:'partial',pending:475});
 expect(html).toContain(pending);expect(html).toContain(button);
 expect(html).toContain('<button');expect(html).toContain('role="status"');
});
it('complete zero or an actually empty audit window does not claim pending work',()=>{
 for(const counts of [{natural:0,audit:0,verification:'complete',pending:0},{natural:0,audit:2,verification:'complete',pending:0}]){
  const html=render('en',en,counts);expect(html).not.toContain('Source verification is incomplete');
 }
});
it('an explicit unknown filter stays that filter rather than becoming a human claim',()=>{
 const html=render('en',en,{natural:0,audit:1998,verification:'partial',pending:475},'unknown');
 expect(html).toContain('No prompts match this source filter');expect(html).not.toContain('Source verification is incomplete');
});

it.each([{kind:'human',status:'verified',want:'Natural user prompts'},
 {kind:'human',status:'unknown',want:'Unknown source'},
 {kind:'subagent',status:'verified',want:'Subagent tasks'},
 {kind:'unknown',status:'unknown',want:'Unknown source'},
 {kind:'constructor',status:'verified',want:'Unknown source'}])('mixed audit rows show only their evidenced origin ($kind/$status)',({kind,status,want})=>{
 const html=renderToStaticMarkup(createElement(NextIntlClientProvider,{locale:'en',messages:en,timeZone:'Asia/Shanghai',children:createElement(PromptOriginBadge,{kind,status})}));
 expect(html).toContain(want);
 if(status!=='verified')expect(html).not.toContain('Natural user prompts');
});
