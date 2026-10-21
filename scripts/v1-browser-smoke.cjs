const { chromium } = require('playwright');
const fs=require('fs');
const base=process.env.BASE_URL||'http://frontend:8080';
const out=process.env.OUTPUT_DIR||'/evidence/v1-browser';
const nonce=Date.now().toString(36);
fs.mkdirSync(out,{recursive:true});
const report={baseUrl:base,kind:'observed',mockedRequests:0,checks:[],screenshots:[],errors:[]};
const checked=name=>{report.checks.push(name);console.log('PASS',name);};
(async()=>{
 const browser=await chromium.launch({headless:true,executablePath:'/usr/bin/chromium',args:['--no-sandbox','--disable-dev-shm-usage']});
 const contexts=[];
 async function login(account,button){
  const context=await browser.newContext({viewport:{width:1440,height:1000},timezoneId:"Asia/Seoul"});contexts.push(context);
  const page=await context.newPage();page.setDefaultTimeout(15000);console.log('LOGIN',account);
  page.on('pageerror',e=>report.errors.push(e.message));page.on('request',r=>{if(r.method()==='POST')console.log('POST',r.url());});page.on('response',r=>{if(r.request().method()==='POST')console.log('STATUS',r.status(),r.url());});
  await page.goto(base,{waitUntil:'domcontentloaded',timeout:20000});await page.waitForLoadState('networkidle',{timeout:5000}).catch(()=>{});
  await page.getByRole('button',{name:button,exact:true}).click();
  await page.getByLabel('아이디',{exact:true}).fill(account);
  await page.locator('#password').fill('liveguard-local');
  const result=page.waitForResponse(r=>r.url().endsWith('/api/auth/login')&&r.request().method()==='POST');
  await page.getByRole('button',{name:'로그인',exact:true}).click();
  if((await result).status()!==200)throw Error('Login failed '+account);
  await page.locator('.v1-shell').waitFor();
  return page;
 }
 async function capture(page,name){await page.screenshot({path:out+'/'+name+'.png',fullPage:true,timeout:8000,animations:'disabled'}).catch(e=>console.log('screenshot unavailable',name));report.screenshots.push(name+'.png');}
 try{
  const operator=await login('moderator','스트리머로 시작하기');
  await operator.locator('.v1-live-id').waitFor({timeout:2500}).catch(()=>{});
  if(process.env.FRESH_LIVE==='1'&&(await operator.locator('.v1-live-id').count())){await operator.getByRole('button',{name:'방송 종료',exact:true}).click();await operator.waitForTimeout(500);await operator.getByRole('button',{name:'새로고침',exact:true}).click();await operator.waitForTimeout(500);}
  if(!(await operator.locator('.v1-live-id').count()))await operator.getByRole('button',{name:'방송 시작',exact:true}).click();
  const viewer=await login('demo-viewer-10','시청자로 시작하기');
  const observer=await login('demo-viewer-11','시청자로 시작하기');
  const admin=await login('admin','시스템 운영자 전용');
  await admin.getByText('이 화면에는 Mock 집계를 표시하지 않습니다.').waitFor();
  checked('Four independent role sessions; admin has no fabricated metrics');
  const normal='브라우저 실연동 인사 '+nonce;
  await viewer.getByLabel('채팅 보내기',{exact:true}).fill(normal);
  await viewer.getByLabel('채팅 보내기',{exact:true}).press('Enter');
  await observer.getByText(normal,{exact:true}).waitFor({timeout:15000});
  await operator.getByText(normal,{exact:true}).waitFor();
  checked('UI chat -> real Backend/DB -> SSE -> non-author and operator');
  const context='오늘 무대 미쳤다ㅋㅋ '+nonce;
  await viewer.getByLabel('채팅 보내기',{exact:true}).fill(context);
  await viewer.getByRole('button',{name:'채팅 전송',exact:true}).click();
  await operator.getByText(context,{exact:true}).first().waitFor({timeout:15000});
  if(await observer.getByText(context,{exact:true}).count())throw Error('HELD text leaked to observer');
  checked('Context candidate is HELD and absent from non-author DOM');
  const card=operator.locator('.v1-review').filter({hasText:context}).first();
  await card.waitFor({timeout:120000});
  await card.locator('.v1-finding b').first().waitFor();
  const reviewId=await card.getAttribute('data-review-id');report.reviewId=reviewId;
  await capture(operator,'operator-ai-review');await capture(observer,'observer-held-isolated');await capture(viewer,'author-held');
  checked('Actual Agent task, Business MCP, RAG and model produce a human review');
  await card.getByLabel('결정 이유',{exact:true}).fill('추가 확인을 위해 보류합니다.');
  await card.getByRole('button',{name:'보류',exact:true}).click();
  await operator.getByRole('status').filter({hasText:'DEFER'}).waitFor({timeout:15000});
  await operator.waitForTimeout(1500);
  if(await observer.getByText(context,{exact:true}).count())throw Error('DEFER released message');
  checked('DEFER keeps same review and message HELD');
  await operator.getByRole('button',{name:'새로고침',exact:true}).click();
  const same=operator.locator('[data-review-id="'+reviewId+'"]');
  await same.getByLabel('결정 이유',{exact:true}).fill('무대를 칭찬한 표현임을 문맥으로 확인했습니다.');
  await same.getByRole('button',{name:'정상 확정',exact:true}).click();
  await observer.getByText(context,{exact:true}).waitFor({timeout:30000});
  await capture(operator,'operator-decision-applied');await capture(observer,'observer-public-restored');await capture(admin,'admin-no-mock');
  checked('Stored human decision -> same thread resume -> Backend apply -> SSE public restoration');
  const risky=await login(process.env.ATTACK_ACCOUNT||'demo-viewer-12','시청자로 시작하기');
  const attack='시청자 11 너 꺼져 '+nonce;
  await risky.getByLabel('채팅 보내기',{exact:true}).fill(attack);
  await risky.getByRole('button',{name:'채팅 전송',exact:true}).click();
  const attackCard=operator.locator('.v1-review').filter({hasText:attack}).first();
  await attackCard.waitFor({timeout:120000});
  await attackCard.getByLabel('괴롭힘',{exact:true}).check();
  await attackCard.getByLabel('결정 이유',{exact:true}).fill('특정 시청자를 향한 공격임을 확인했습니다.');
  await attackCard.getByRole('button',{name:'위반 확정',exact:true}).click();
  await risky.locator('.v1-message.hidden').filter({hasText:attack}).waitFor({timeout:30000});
  if(await observer.getByText(attack,{exact:true}).count())throw Error('Confirmed hidden text leaked');
  await risky.getByLabel('채팅 보내기',{exact:true}).fill('제한 중 전송 검증 '+nonce);
  const denied=risky.waitForResponse(r=>r.url().includes('/messages')&&r.request().method()==='POST');
  await risky.getByRole('button',{name:'채팅 전송',exact:true}).click();
  const deniedResponse=await denied;const deniedBody=await deniedResponse.json();
  if(deniedResponse.status()!==403||deniedBody.error.code!=='TIMED_OUT'||!deniedBody.error.until)throw Error('Missing real timeout refusal');
  await capture(operator,'operator-violation-confirmed');await capture(risky,'author-hidden-timeout');
  checked('Human violation -> actual HIDDEN/TIMEOUT -> 403 TIMED_OUT with until; observer remains isolated');
  if(process.env.RUN_KICK==='1') {
   const repeat=await login(process.env.KICK_ACCOUNT||'demo-viewer-13','시청자로 시작하기');
   const attacks=[1,2,3].map(n=>'시청자 11 너 꺼져 반복공격 '+n+' '+nonce);
   for(const text of attacks){
    await repeat.getByLabel('채팅 보내기',{exact:true}).fill(text);
    const sent=repeat.waitForResponse(r=>r.url().includes('/messages')&&r.request().method()==='POST');
    await repeat.getByRole('button',{name:'채팅 전송',exact:true}).click();
    if((await sent).status()!==201)throw Error('Kick setup send refused');
   }
   for(const text of attacks){
    const review=operator.locator('.v1-review').filter({has:operator.locator('.v1-finding blockquote').filter({hasText:text})}).first();
    await review.waitFor({timeout:180000});
    await review.getByLabel('괴롭힘',{exact:true}).check();
    await review.getByLabel('결정 이유',{exact:true}).fill('같은 시청자를 겨냥한 별도 공격을 확인했습니다.');
    await review.getByRole('button',{name:'위반 확정',exact:true}).click();
    await repeat.locator('.v1-message.hidden').filter({hasText:text}).waitFor({timeout:45000});
   }
   const kick=operator.locator('.v1-review').filter({has:operator.locator('.v1-kind').filter({hasText:'강퇴 승인'})}).first();
   await kick.waitFor({timeout:60000});await capture(operator,'operator-separate-kick-approval');
   await kick.getByLabel('결정 이유',{exact:true}).fill('서로 다른 확정 사건 3건을 확인하고 현재 방송 강퇴를 승인합니다.');
   await kick.getByRole('button',{name:'강퇴 승인',exact:true}).click();
   await repeat.getByRole('status').filter({hasText:'입장이 제한'}).waitFor({timeout:60000});
   await capture(repeat,'author-kicked-until-live-end');
   checked('Three distinct confirmed cases -> separate human KICK approval -> real MCP execution -> target SSE disconnect');
  }
  const recovered=await login(process.env.RECOVERY_ACCOUNT||'demo-viewer-18','시청자로 시작하기');
  const mistaken='시청자 11 너 꺼져 오판취소 '+nonce;
  await recovered.getByLabel('채팅 보내기',{exact:true}).fill(mistaken);
  await recovered.getByRole('button',{name:'채팅 전송',exact:true}).click();
  const recoveryReview=operator.locator('.v1-review').filter({has:operator.locator('.v1-finding blockquote').filter({hasText:mistaken})}).first();
  await recoveryReview.waitFor({timeout:120000});
  await recoveryReview.getByLabel('괴롭힘',{exact:true}).check();
  await recoveryReview.getByLabel('결정 이유',{exact:true}).fill('복구 시험용으로 문맥 위반을 확인합니다.');
  await recoveryReview.getByRole('button',{name:'위반 확정',exact:true}).click();
  await recovered.locator('.v1-message.hidden').filter({hasText:mistaken}).waitFor({timeout:30000});
  const recoveryCard=operator.locator('.v1-recovery').filter({hasText:mistaken}).first();
  await recoveryCard.locator('summary').click();
  await recoveryCard.getByLabel('취소 사유',{exact:true}).fill('문맥 재확인 결과 오판이므로 해당 확정 근거를 취소합니다.');
  await recoveryCard.getByRole('button',{name:'확정 근거 취소',exact:true}).click();
  await observer.getByText(mistaken,{exact:true}).waitFor({timeout:30000});
  await recovered.getByLabel('채팅 보내기',{exact:true}).fill('제한 복구 뒤 전송 '+nonce);
  const restored=recovered.waitForResponse(r=>r.url().includes('/messages')&&r.request().method()==='POST');
  await recovered.getByRole('button',{name:'채팅 전송',exact:true}).click();
  if((await restored).status()!==201)throw Error('Recovery failed to remove own timeout');
  await capture(operator,'operator-finding-revoked');await capture(observer,'observer-recovery-public');
  checked('Human finding revocation -> real PUBLIC recovery and timeout removal -> new send accepted');
  const flooder=await login('demo-viewer-17','시청자로 시작하기');
  const flood='같은 문장 반복 시험 '+nonce;
  for(let i=0;i<4;i++){
   await flooder.getByLabel('채팅 보내기',{exact:true}).fill(flood);
   const sent=flooder.waitForResponse(r=>r.url().includes('/messages')&&r.request().method()==='POST');
   await flooder.getByRole('button',{name:'채팅 전송',exact:true}).click();
   if((await sent).status()!==201)throw Error('First FLOOD burst unexpectedly timed out');
  }
  await operator.waitForFunction(value=>[...document.querySelectorAll('.v1-message.hidden')].filter(n=>n.textContent.includes(value)).length===2,flood,{timeout:20000});
  if(await observer.getByText(flood,{exact:true}).count()!==2)throw Error('FLOOD changed first two public context messages');
  await capture(operator,'operator-flood-third-fourth-hidden');
  checked('FLOOD burst keeps first two PUBLIC; third and fourth share confirmed hidden handling');
  const sessionChange=await operator.evaluate(async()=>{
   await fetch('/api/auth/me');
   const token=decodeURIComponent(document.cookie.split('; ').find(x=>x.startsWith('XSRF-TOKEN=')).split('=').slice(1).join('='));
   return (await fetch('/api/auth/login',{method:'POST',headers:{'Content-Type':'application/json','X-XSRF-TOKEN':token},body:JSON.stringify({username:'demo-viewer-19',password:'liveguard-local'})})).status;
  });
  if(sessionChange!==200)throw Error('Same-cookie reauthentication failed');
  await operator.getByText('시청자 19',{exact:true}).waitFor({timeout:15000});
  if(await operator.locator('.v1-reviews').count())throw Error('Old operator review panel survived identity change');
  await capture(operator,'same-cookie-viewer-cleared-operator-state');
  checked('Same-cookie account switch clears old operator cards and private chat state');
  if(report.errors.length)throw Error('Browser runtime error');
  report.status='PASS';
 }catch(error){report.status='FAIL';report.error=error.message;console.error(error.message);for(let i=0;i<contexts.length;i++){const p=contexts[i].pages()[0];if(p)await capture(p,'failure-'+i);}process.exitCode=1;}
 finally{fs.writeFileSync(out+'/report.json',JSON.stringify(report,null,2));await browser.close();}
})();
