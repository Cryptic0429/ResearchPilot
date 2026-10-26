'use strict';
// Credentials stay in HttpOnly cookies; localStorage only signals account changes.
let clientWorkspace=null,accountLocked=false,layoutSaveTimer,layoutPatch={};

function currentUser(){return S.account?.user||null;}
function accountInitial(){return (currentUser()?.display_name||'访').slice(0,1).toUpperCase();}
function accountStorageKey(name){return 'rp.'+name+'.'+(currentUser()?.id||'guest')+'.'+(S.project?.id||'none')+'.'+(S.research?.id||'none');}
function accountShortcut(){
  const user=currentUser();
  return `<button class="account-shortcut" data-action="${user?'account-settings':'auth-open'}" title="${user?'管理个人资料与偏好':'登录或注册邮箱账号'}"><span class="account-avatar">${e(accountInitial())}</span><span class="account-shortcut-copy"><strong>${e(user?.display_name||'访客研究空间')}</strong><small>${user?'个人资料与偏好':'登录 / 注册，保存你的偏好'}</small></span>${icon('chevron')}</button>`;
}
function applyAccountPreferences(initial=false){
  const prefs=S.account?.preferences||{};
  document.documentElement.dataset.theme=prefs.theme||'system';
  if(currentUser()){
    sidebarCollapsed=!!prefs.sidebar_collapsed;contextHidden=!!prefs.context_hidden;
    useModel=!!prefs.prefer_model&&S.model.ready;
  }
  if(initial){
    clientWorkspace=currentUser()?.id||'guest';
    if(currentUser()&&!location.hash)view=prefs.default_view||'home';
    if(!S.last_run)taskDraft=S.research?.title||prefs.research_field||'';
    daysDraft=String(prefs.search_days||90);
    searchDraft=S.search?.query||prefs.research_field||searchDraft;
    topicDraft=S.last_run?.topic||S.research?.title||prefs.research_field||'';
    constraintDraft=S.last_run?.constraints??prefs.default_constraints??'';
    readerState.target=prefs.translation_target||'zh-CN';
    readerState.glossary=prefs.glossary||'';
  }
}
function signalAccountChange(){try{localStorage.setItem('rp.account-change',String(Date.now())+Math.random());}catch{}}
function reloadAccount(target){
  signalAccountChange();
  if(target)history.replaceState(null,'','#'+target);
  location.reload();
}
function lockAccount(message){
  if(accountLocked)return;
  accountLocked=true;setWatch(false);clearTimeout(layoutSaveTimer);clearTimeout(readerAutoTimer);
  readerState.generation++;readerState.documentEpoch++;readerState.renderTask?.cancel();readerState.pdfTask?.destroy();
  readerState.pdf?.destroy();readerState.text='';readerState.result=null;readerState.history=[];
  chat=[];selected.clear();taskDraft=topicDraft=constraintDraft=chatDraft='';plan=null;envResult=null;
  S={project:null,search:null,last_run:null,notes:[],events:[],model:{ready:false},models:{research:{ready:false},translation:{ready:false}},active_jobs:[]};
  closeModal();
  $('#app').innerHTML=`<main class="account-gate"><img src="/favicon.svg" alt="研途"><h1>重新连接你的研究空间</h1><p>${e(message)}</p><div class="button-row"><button class="btn primary" data-action="auth-open">重新登录</button><button class="btn" data-action="account-reload">载入当前账号</button><button class="btn text" data-action="auth-guest">进入访客空间</button></div></main>`;
}
window.addEventListener('storage',event=>{if(event.key==='rp.account-change')lockAccount('账号已在另一个页面变更，请重新载入后继续。');});
window.addEventListener('pageshow',event=>{if(event.persisted)location.reload();});

function authModal(mode='login',email=''){
  if(busy)return toast('请等待当前任务完成后再切换账号');
  const signup=mode==='register';
  modal(`<div class="auth-brand"><img src="/favicon.svg" alt=""><span>研途<span class="brand-dot">.</span><small>一个属于你的研究空间</small></span></div>
    <div class="tab-switch auth-tabs" role="group" aria-label="账号操作"><button data-action="auth-mode" data-mode="login" class="${signup?'':'selected'}" aria-pressed="${!signup}">邮箱登录</button><button data-action="auth-mode" data-mode="register" class="${signup?'selected':''}" aria-pressed="${signup}">创建账号</button></div>
    <h2>${signup?'让工作台记住你的研究习惯':'欢迎回到研途'}</h2><p class="auth-intro">${signup?'保存个人偏好，在专属空间继续你的研究。':'登录后，继续你的项目、笔记与研究探索。'}</p>
    <form id="auth-form" class="auth-form">
      ${signup?'<div class="form-group"><label class="form-label" for="auth-name">怎么称呼你</label><input class="field full" id="auth-name" name="name" autocomplete="nickname" maxlength="40" placeholder="你的昵称" required></div>':''}
      <div class="form-group"><label class="form-label" for="auth-email">邮箱地址</label><input class="field full" id="auth-email" name="email" type="email" autocomplete="username" maxlength="254" value="${e(email)}" placeholder="you@example.com" required></div>
      ${signup?'<div class="auth-password-grid">':''}<div class="form-group"><label class="form-label" for="auth-password">${signup?'设置密码':'密码'}</label><input class="field full" id="auth-password" name="password" type="password" autocomplete="${signup?'new-password':'current-password'}" ${signup?'minlength="10"':''} maxlength="128" placeholder="${signup?'10–128 个字符':'输入你的密码'}" required></div>
      ${signup?'<div class="form-group"><label class="form-label" for="auth-confirm">确认密码</label><input class="field full" id="auth-confirm" name="confirm" type="password" autocomplete="new-password" minlength="10" maxlength="128" placeholder="再输入一次密码" required></div></div>':''}
      <div class="auth-options"><label class="check-label"><input id="auth-remember" type="checkbox">保持登录 30 天</label><label class="check-label"><input id="auth-show" type="checkbox">显示密码</label></div>
      <p id="auth-error" class="account-form-error" role="alert" aria-live="polite"></p>
      <button class="btn primary full-btn" type="submit" id="auth-submit">${signup?'创建我的账号':'登录研究空间'} ${icon('arrow')}</button>
    </form>
    <p class="auth-boundary">邮箱用于本机登录，当前不发送验证邮件。${signup?'新账号拥有独立工作区，已有访客记录仍保留在访客空间。':'忘记密码？当前版本未接入邮件找回，可在已登录的账号设置中修改密码。'}</p>
    <div class="auth-footer">${icon('shield')}账号和研究数据保存在本机<button class="text-link" data-action="${accountLocked?'auth-guest':'close-modal'}">${accountLocked?'进入访客空间':'暂时以访客使用'}</button></div>`);
  $('#modal-root .modal').classList.add('auth-modal');
  $('#auth-show').onchange=event=>{for(const id of ['auth-password','auth-confirm'])if($('#'+id))$('#'+id).type=event.target.checked?'text':'password';};
  $('#auth-form').onsubmit=async event=>{
    event.preventDefault();const form=event.currentTarget,button=$('#auth-submit'),error=$('#auth-error');
    if(button.disabled)return;
    if(signup&&$('#auth-password').value!==$('#auth-confirm').value){error.textContent='两次输入的密码不一致';$('#auth-confirm').focus();return;}
    const data={email:$('#auth-email').value,password:$('#auth-password').value,remember:$('#auth-remember').checked};
    if(signup)data.display_name=$('#auth-name').value;
    button.disabled=true;error.textContent='';
    try{
      const result=await api('/api/auth/'+(signup?'register':'login'),data);
      form.reset();reloadAccount(result.user.preferences.default_view||'home');
    }catch(err){error.textContent=err.message;button.disabled=false;}
  };
  $(signup?'#auth-name':'#auth-email').focus();
}

function accountSettings(){
  const user=currentUser(),p=S.account?.preferences||{};
  if(!user)return `<section class="panel account-invitation"><span class="account-invitation-icon">${icon('user')}</span><div><div class="eyebrow">YOUR PERSONAL WORKSPACE</div><h2>让研途记住你的研究习惯</h2><p>注册邮箱账号，保存个人偏好，拥有独立的项目、笔记和模型配置。</p><small>当前为访客空间；已有记录会继续保留在这里。</small></div><div class="button-row"><button class="btn" data-action="auth-open">登录</button><button class="btn primary" data-action="auth-open" data-mode="register">创建账号 ${icon('arrow')}</button></div></section>`;
  return `<section class="panel account-profile"><div class="account-profile-head"><span class="account-avatar large">${e(accountInitial())}</span><div><div class="eyebrow">YOUR PERSONAL WORKSPACE</div><h2>${e(user.display_name)} 的研究空间</h2><p>${e(user.email)} <span class="tag gray">本机账号</span></p></div><button class="btn" data-action="auth-logout" data-busy>退出登录</button></div>
    <div class="divider"></div><form id="profile-form"><div class="panel-head"><h3>${icon('user')} 个人资料与研究偏好</h3><span class="tiny muted">随账号保存在本机</span></div>
    <div class="account-preference-grid"><div class="form-group"><label class="form-label" for="pref-name">昵称</label><input class="field full" id="pref-name" autocomplete="nickname" value="${e(user.display_name)}" maxlength="40" required></div><div class="form-group"><label class="form-label" for="pref-field">默认研究方向</label><input class="field full" id="pref-field" value="${e(p.research_field)}" maxlength="180" placeholder="填写你的研究方向"></div></div>
    <div class="form-group"><label class="form-label" for="pref-constraints">默认研究条件与目标</label><textarea class="field full" id="pref-constraints" maxlength="2000" rows="2" placeholder="填写时间安排、可用数据与研究目标">${e(p.default_constraints)}</textarea></div>
    <div class="account-preference-grid four"><div class="form-group"><label class="form-label" for="pref-theme">界面主题</label><select class="field full" id="pref-theme">${[['system','跟随系统'],['light','浅色'],['dark','深色']].map(([v,n])=>`<option value="${v}" ${p.theme===v?'selected':''}>${n}</option>`).join('')}</select></div><div class="form-group"><label class="form-label" for="pref-home">默认进入页面</label><select class="field full" id="pref-home">${views.map(([id,label])=>`<option value="${id}" ${p.default_view===id?'selected':''}>${label}</option>`).join('')}</select></div><div class="form-group"><label class="form-label" for="pref-days">默认检索时间范围</label><select class="field full" id="pref-days">${[[7,'近 7 天'],[30,'近 30 天'],[90,'近 90 天'],[365,'近一年']].map(([v,n])=>`<option value="${v}" ${p.search_days===v?'selected':''}>${n}</option>`).join('')}</select></div><div class="form-group"><label class="form-label" for="pref-target">默认翻译方向</label><select class="field full" id="pref-target"><option value="zh-CN" ${p.translation_target==='zh-CN'?'selected':''}>英文 → 中文</option><option value="en" ${p.translation_target==='en'?'selected':''}>中文 → 英文</option></select></div></div>
    <details class="account-more"><summary>术语与工作台布局</summary><div class="form-group"><label class="form-label" for="pref-glossary">默认翻译术语约定</label><textarea class="field full" id="pref-glossary" maxlength="1000" rows="2" placeholder="填写需要统一的术语及对应译法">${e(p.glossary)}</textarea></div><div class="account-layout-options"><label class="check-label"><input id="pref-sidebar" type="checkbox" ${p.sidebar_collapsed?'checked':''}>默认收起导航</label><label class="check-label"><input id="pref-context" type="checkbox" ${p.context_hidden?'checked':''}>默认收起研究上下文</label><label class="check-label"><input id="pref-model" type="checkbox" ${p.prefer_model?'checked':''}>接口可用时优先使用模型</label></div></details>
    <p id="profile-error" class="account-form-error" role="alert"></p><div class="account-save-row"><span class="tiny muted">新研究使用默认方向与约束；项目摘要外发仍需明确勾选。</span><button class="btn primary" type="submit" data-busy>${icon('check')} 保存个人偏好</button></div></form>
    <details class="account-security"><summary>${icon('shield')} 账号安全 · 修改密码</summary><form id="password-form"><div class="account-preference-grid three"><div class="form-group"><label class="form-label" for="password-current">当前密码</label><input class="field full" id="password-current" type="password" autocomplete="current-password" maxlength="128" required></div><div class="form-group"><label class="form-label" for="password-new">新密码</label><input class="field full" id="password-new" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></div><div class="form-group"><label class="form-label" for="password-confirm">确认新密码</label><input class="field full" id="password-confirm" type="password" autocomplete="new-password" minlength="10" maxlength="128" required></div></div><p id="password-error" class="account-form-error" role="alert"></p><div class="account-save-row"><span class="tiny muted">密码为 10–128 个字符；修改后其他会话会退出。</span><button class="btn" type="submit" data-busy>更新密码</button></div></form></details></section>`;
}

function bindAccountForms(){
  const profile=$('#profile-form');
  if(profile)profile.onsubmit=async event=>{
    event.preventDefault();if(busy)return;
    const preferences={theme:$('#pref-theme').value,default_view:$('#pref-home').value,research_field:$('#pref-field').value,
      default_constraints:$('#pref-constraints').value,search_days:Number($('#pref-days').value),translation_target:$('#pref-target').value,
      glossary:$('#pref-glossary').value,sidebar_collapsed:$('#pref-sidebar').checked,context_hidden:$('#pref-context').checked,prefer_model:$('#pref-model').checked};
    const data={display_name:$('#pref-name').value,preferences};
    clearTimeout(layoutSaveTimer);layoutPatch={};
    await work('保存个人偏好…',async()=>{
      try{
        const result=await api('/api/profile/update',data);S.account.user=result.user;S.account.preferences=result.user.preferences;
        applyAccountPreferences();daysDraft=String(preferences.search_days);readerCapture();readerState.target=preferences.translation_target;readerState.glossary=preferences.glossary;
        render();toast('个人偏好已保存');
      }catch(err){if($('#profile-error'))$('#profile-error').textContent=err.message;else throw err;}
    });
  };
  const password=$('#password-form');
  if(password)password.onsubmit=async event=>{
    event.preventDefault();if(busy)return;
    const error=$('#password-error');error.textContent='';
    if($('#password-new').value!==$('#password-confirm').value){error.textContent='两次输入的新密码不一致';$('#password-confirm').focus();return;}
    const data={current_password:$('#password-current').value,new_password:$('#password-new').value};
    await work('更新账号密码…',async()=>{
      try{await api('/api/auth/password',data);password.reset();signalAccountChange();toast('密码已更新，其他会话已退出');}
      catch(err){if($('#password-error'))$('#password-error').textContent=err.message;else throw err;}
    });
  };
}

function saveLayoutPreferences(patch){
  if(!currentUser())return;
  Object.assign(layoutPatch,patch);clearTimeout(layoutSaveTimer);
  Object.assign(S.account.preferences,patch);
  if($('#pref-sidebar'))$('#pref-sidebar').checked=sidebarCollapsed;
  if($('#pref-context'))$('#pref-context').checked=contextHidden;
  layoutSaveTimer=setTimeout(async()=>{
    const preferences=layoutPatch;layoutPatch={};
    try{await api('/api/profile/update',{preferences});}
    catch(err){toast('布局偏好未保存：'+err.message,true);}
  },250);
}

async function accountAction(action,button){
  if(action==='auth-open'){authModal(button.dataset.mode||'login');return true;}
  if(action==='auth-mode'){authModal(button.dataset.mode,$('#auth-email')?.value||'');return true;}
  if(action==='account-settings'){await nav('settings');return true;}
  if(action==='account-reload'){location.reload();return true;}
  if(action==='auth-logout'||action==='auth-guest'){
    if(busy){toast('请等待当前任务完成后再切换账号');return true;}
    try{await api('/api/auth/logout',{});reloadAccount('home');}catch(err){toast(err.message,true);}return true;
  }
  return false;
}
