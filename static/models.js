'use strict';
// Each purpose has independent settings and credentials; never substitute one for the other.
function modelConnection(purpose){return S.models?.[purpose]||(purpose==='research'?S.model:{ready:false,provider:'致远1号'});}
function updateModelConnection(purpose,config){
  S.models=S.models||{};S.models[purpose]=config;
  if(purpose==='research'){S.model=config;if(!config.ready){useModel=false;shareProject=false;}}
}
function savedConnections(purpose){
  const cfg=modelConnection(purpose),prefix='provider-'+purpose+'-';
  const entries=(S.connections||[]).filter(entry=>entry.purpose===purpose);
  const sourceName={official:'官方 API',relay:'中转站 / 聚合平台',local:'本地服务',custom:'自定义'};
  return `<div class="divider"></div><h4>服务配置库</h4><p class="tiny muted" style="margin:8px 0">保存当前已生效的地址、协议、模型和密钥，之后可一键切换。科研与翻译配置分别管理。</p><div class="run-controls"><div class="form-group"><label class="form-label" for="${prefix}saved-name">配置名称</label><input class="field full" id="${prefix}saved-name" maxlength="60" value="${e(cfg.provider||'')}" placeholder="例如：官方主用、备用中转站"></div><div class="form-group"><label class="form-label" for="${prefix}source">接入来源</label><select class="field full" id="${prefix}source">${Object.entries(sourceName).map(([value,label])=>`<option value="${value}" ${value==='custom'?'selected':''}>${label}</option>`).join('')}</select></div></div><button class="btn small" type="button" data-action="save-connection" data-purpose="${purpose}" data-busy ${cfg.ready?'':'disabled'}>${icon('plus')} 将当前连接存入配置库</button><div class="saved-connections">${entries.map(entry=>`<div class="saved-connection"><div><strong>${e(entry.label)}</strong><span class="tag gray">${sourceName[entry.source]||'自定义'}</span><p class="tiny muted">${e(entry.base)}<br>${e(entry.model)} · ${e(entry.style)}${entry.available?'':' · 配置需重新保存'}</p></div><div class="button-row"><button class="btn small" type="button" data-action="use-connection" data-purpose="${purpose}" data-connection="${entry.id}" data-busy ${entry.available?'':'disabled'}>切换到此配置</button><button class="btn text" type="button" data-action="remove-connection" data-purpose="${purpose}" data-connection="${entry.id}" data-busy>移除配置</button></div></div>`).join('')||'<p class="tiny muted" style="margin-top:12px">还没有保存服务配置。</p>'}</div><p class="tiny muted">${currentUser()?'配置库按账号保存在本机；切换会替换当前用途的连接。':'访客配置库与密钥只在本次服务运行中保留。'}清除当前连接密钥与移除配置库中的副本是两个独立操作。切换不会调用模型，已提交任务继续使用提交时的连接。</p>`;
}
function modelConnectionCard(purpose){
  const cfg=modelConnection(purpose),translation=purpose==='translation',prefix='provider-'+purpose+'-';
  const label=translation?'文献翻译':'科研任务';
  return `<section class="panel model-connection" data-model-purpose="${purpose}">
    <div class="panel-head"><h3>${icon(translation?'book':'spark')} ${label}连接</h3><span class="tag ${cfg.ready?'':'warm'}">${cfg.key_saved?'已保存至账号':cfg.ready?'已配置':'未配置'}</span></div>
    <p class="muted small-copy">${translation?'用于论文阅读中的段落翻译。可接致远1号，单次只发送待译文字和术语约定。':'用于研究意图澄清、文献分析、候选 Idea 生成与独立审查。可接模型厂商官方 API、中转站或本地兼容服务。'}</p>
    ${cfg.credential_error||cfg.blocked_reason?`<div class="callout warm" role="alert">${e(cfg.credential_error||cfg.blocked_reason)}</div>`:''}
    <div class="button-row" style="margin-top:14px"><button class="btn small" type="button" data-action="model-preset" data-purpose="${purpose}" data-preset="${translation?'zhiyuan':'deepseek'}">${translation?'致远1号预设':'DeepSeek 官方预设'}</button><button class="btn small" type="button" data-action="model-preset" data-purpose="${purpose}" data-preset="claude">Claude 官方</button><button class="btn small" type="button" data-action="model-preset" data-purpose="${purpose}" data-preset="gemini">Gemini 官方</button><button class="btn text" type="button" data-action="model-preset" data-purpose="${purpose}" data-preset="custom">中转站 / 自定义接口</button></div>
    <form data-model-form="${purpose}" style="margin-top:18px">
      <div class="run-controls"><div class="form-group"><label class="form-label" for="${prefix}name">接口名称</label><input class="field full" id="${prefix}name" value="${e(cfg.provider||'')}" maxlength="60" required></div><div class="form-group"><label class="form-label" for="${prefix}style">接口协议</label><select class="field full" id="${prefix}style">${[['chat_completions','OpenAI Chat Completions'],['responses','OpenAI Responses'],['anthropic_messages','Claude Messages（原生）'],['gemini','Gemini generateContent（原生）']].map(([value,label])=>`<option value="${value}" ${cfg.style===value?'selected':''}>${label}</option>`).join('')}</select></div></div>
      <div class="form-group"><label class="form-label" for="${prefix}base">Base URL · 接口根地址</label><input class="field full" id="${prefix}base" type="url" value="${e(cfg.base||'')}" placeholder="https://your-provider.example/v1" required></div>
      <div class="form-group"><label class="form-label" for="${prefix}model">模型 ID</label><input class="field full" id="${prefix}model" value="${e(cfg.model||'')}" list="${prefix}options" placeholder="以服务返回的模型列表为准" required><datalist id="${prefix}options"></datalist></div>
      <div class="run-controls"><div class="form-group"><label class="form-label" for="${prefix}auth">认证方式</label><select class="field full" id="${prefix}auth">${[['bearer','Authorization: Bearer'],['x-api-key','x-api-key'],['x-goog-api-key','x-goog-api-key（Gemini）'],['none','无需认证（仅本机）']].map(([value,title])=>`<option value="${value}" ${cfg.auth===value?'selected':''}>${title}</option>`).join('')}</select></div><div class="form-group"><label class="form-label" for="${prefix}key">${currentUser()?'API Key · 按用途保存至账号':'API Key · 仅在本次运行有效'}</label><input class="field full" id="${prefix}key" type="password" autocomplete="off" maxlength="8192" placeholder="${cfg.key_saved?'已保存；同地址留空沿用':cfg.ready?'已配置；同地址留空沿用':'填写此服务的独立密钥'}"></div></div>
      <div class="button-row"><button class="btn primary" type="submit" data-busy>${icon('check')} 保存${label}连接</button><button class="btn" type="button" data-action="list-models" data-purpose="${purpose}" data-busy ${cfg.ready?'':'disabled'}>拉取可用模型</button><button class="btn" type="button" data-action="check-model" data-purpose="${purpose}" data-busy ${cfg.ready?'':'disabled'}>检查连接</button>${cfg.ready||cfg.key_saved?`<button class="btn text" type="button" data-action="clear-model-key" data-purpose="${purpose}" data-busy>移除此用途密钥</button>`:''}</div>
      ${savedConnections(purpose)}
    </form>
    <p class="tiny muted" style="margin-top:14px">${translation?'校内服务需符合校园网 / VPN 访问要求。':'科研连接未配置或失败时，不会回退到致远1号。'}保存不会调用模型；检查连接会发送一条${translation?'翻译':'连接验证'}请求，可能使用服务额度。</p>
    <p class="tiny muted" style="margin-top:8px">${currentUser()?'连接信息和密钥按账号、用途分别保存在本机，重新登录或重启后恢复。':'访客密钥不落盘；登录后分别保存两组连接可长期使用。'}<a href="${cfg.style==='gemini'?'https://ai.google.dev/api/generate-content':cfg.style==='anthropic_messages'?'https://platform.claude.com/docs/en/api/messages/create':translation?'https://claw.sjtu.edu.cn/guide/sjtu-api/':'https://api-docs.deepseek.com/'}" target="_blank" rel="noopener noreferrer">接口说明 ↗</a></p>
  </section>`;
}
function modelConnections(){return `<div class="callout" style="margin-bottom:20px"><strong>官方 API、中转站与本地服务，统一按协议接入</strong><p>支持 OpenAI Chat Completions / Responses、Claude Messages 和 Gemini generateContent。填写服务提供的版本化接口根路径（如 /v1 或 /v1beta）；自定义路径会原样保留。可保存多组配置并手动切换。致远1号仅用于文献翻译，科研与翻译连接分别管理。</p></div><div class="settings-grid model-connections">${modelConnectionCard('research')}${modelConnectionCard('translation')}</div>`;}
function captureModelDrafts(except){
  return [...document.querySelectorAll('[data-model-form]')].filter(form=>form.dataset.modelForm!==except).map(form=>({
    purpose:form.dataset.modelForm,values:[...form.querySelectorAll('input,select')].map(field=>[field.id,field.value])
  }));
}
function restoreModelDrafts(drafts){for(const draft of drafts)for(const [id,value] of draft.values){const field=document.getElementById(id);if(field)field.value=value;}}
function bindModelForms(){
  document.querySelectorAll('[data-model-purpose]').forEach(card=>{
    const purpose=card.dataset.modelPurpose,prefix='#provider-'+purpose+'-';
    $(prefix+'style').onchange=()=>{$(prefix+'auth').value=({'anthropic_messages':'x-api-key','gemini':'x-goog-api-key'})[$(prefix+'style').value]||'bearer';};
  });
  document.querySelectorAll('[data-model-form]').forEach(form=>form.onsubmit=event=>{
    event.preventDefault();const purpose=form.dataset.modelForm,prefix='#provider-'+purpose+'-';
    const drafts=captureModelDrafts(purpose),source=$(prefix+'source').value,snapshotName=$(prefix+'saved-name').value;const data={purpose};for(const [field,id] of [['provider','name'],['base','base'],['model','model'],['style','style'],['auth','auth'],['key','key']])data[field]=$(prefix+id).value;
    work('保存'+(purpose==='translation'?'翻译':'科研')+'连接…',async()=>{const cfg=await api('/api/model/configure',data);updateModelConnection(purpose,cfg);render();restoreModelDrafts(drafts);$(prefix+'source').value=source;$(prefix+'saved-name').value=snapshotName||cfg.provider;toast(cfg.key_saved?'已按用途保存至当前账号':cfg.ready?'连接已保存，可检查连接':'连接已保存，请补充此用途的密钥');});
  });
}
async function modelAction(action,button){
  if(!['model-preset','clear-model-key','list-models','check-model','save-connection','use-connection','remove-connection'].includes(action))return false;
  const purpose=button.dataset.purpose||'research',label=purpose==='translation'?'翻译':'科研';
  if(['save-connection','use-connection','remove-connection'].includes(action)){
    const prefix='#provider-'+purpose+'-';
    const data={purpose,id:button.dataset.connection};
    if(action==='save-connection'){
      const cfg=modelConnection(purpose);
      if([['provider','name'],['base','base'],['model','model'],['style','style'],['auth','auth']].some(([field,id])=>$(prefix+id).value!==(cfg[field]||''))||$(prefix+'key').value){toast('请先保存上方连接，再将生效的配置存入配置库',true);return true;}
      data.label=$(prefix+'saved-name').value;data.source=$(prefix+'source').value;
    }
    const endpoint=action==='save-connection'?'save':action==='use-connection'?'use':'remove';
    await work(label+'服务配置…',async()=>{
      const drafts=captureModelDrafts(endpoint==='use'?purpose:undefined);
      const result=await api('/api/model/connections/'+endpoint,data);
      S.connections=result.connections;if(result.model)updateModelConnection(purpose,result.model);
      render();restoreModelDrafts(drafts);
      if(endpoint==='use'){const entry=S.connections.find(item=>item.id===data.id);if(entry){$(prefix+'source').value=entry.source;$(prefix+'saved-name').value=entry.label;}}
      toast(endpoint==='use'?'已切换'+label+'连接，新任务将使用此服务':endpoint==='save'?'已保存到服务配置库':'已移除配置库中的副本，当前连接未变');
    });return true;
  }
  if(action==='model-preset'){
    const preset=button.dataset.preset;
    const cfg=preset==='zhiyuan'?{name:'致远1号',base:'https://models.sjtu.edu.cn/api/v1',model:'deepseek-chat'}:preset==='deepseek'?{name:'DeepSeek',base:'https://api.deepseek.com',model:'deepseek-v4-pro'}:preset==='claude'?{name:'Claude 官方',base:'https://api.anthropic.com/v1',model:'',style:'anthropic_messages',auth:'x-api-key'}:preset==='gemini'?{name:'Gemini 官方',base:'https://generativelanguage.googleapis.com/v1beta',model:'',style:'gemini',auth:'x-goog-api-key'}:{name:'',base:'',model:''};
    for(const [field,value] of Object.entries({style:'chat_completions',auth:'bearer',...cfg,key:''}))$('#provider-'+purpose+'-'+field).value=value;
    $('#provider-'+purpose+'-source').value=preset==='custom'?'relay':'official';
    $('#provider-'+purpose+'-saved-name').value=cfg.name;
    toast('预设已填入，请核对模型 ID 并保存'+label+'连接');return true;
  }
  if(action==='clear-model-key')await work('移除'+label+'密钥…',async()=>{const drafts=captureModelDrafts(purpose);updateModelConnection(purpose,await api('/api/model/clear-key',{purpose}));render();restoreModelDrafts(drafts);toast('已移除'+label+'密钥，另一组连接保持可用');});
  if(action==='list-models')await work('获取'+label+'模型列表…',async()=>{const r=await job('/api/model/models',{purpose});$('#provider-'+purpose+'-options').innerHTML=r.models.map(model=>`<option value="${e(model)}">`).join('');toast('可用模型：'+r.models.join('、'));});
  if(action==='check-model')await work('检查'+label+'连接…',async()=>{const r=await job('/api/model/check',{purpose});toast(label+'连接：'+r.text);});
  return true;
}
