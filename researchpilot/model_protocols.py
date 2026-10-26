"""Text request/response adapters shared by official APIs and relay endpoints."""
import re
import urllib.parse


STYLES=('chat_completions','responses','anthropic_messages','gemini')
AUTH_TYPES=('bearer','x-api-key','x-goog-api-key','none')


def api_root(config):
    base=config['base'].rstrip('/')
    # Native vendor roots need their API version. Preserve every custom path
    # provided by a relay; never insert another version into that path.
    if not urllib.parse.urlparse(base).path:
        if config['style']=='anthropic_messages':base+='/v1'
        elif config['style']=='gemini':base+='/v1beta'
    return base


def headers(config):
    result={'Content-Type':'application/json','Accept':'application/json'}
    if config['auth']=='bearer':result['Authorization']='Bearer '+config['key']
    elif config['auth'] in ('x-api-key','x-goog-api-key'):result[config['auth']]=config['key']
    if config['style']=='anthropic_messages':result['anthropic-version']='2023-06-01'
    return result


def text_request(config,system,content,max_tokens):
    style=config['style']
    if style=='responses':
        route='/responses'
        body=dict(model=config['model'],instructions=system,input=content,max_output_tokens=max_tokens,store=False)
    elif style=='chat_completions':
        route='/chat/completions'
        body=dict(model=config['model'],messages=[dict(role='system',content=system),dict(role='user',content=content)],
                  max_tokens=max_tokens,stream=False)
    elif style=='anthropic_messages':
        route='/messages'
        body=dict(model=config['model'],system=system,messages=[dict(role='user',content=content)],
                  max_tokens=max_tokens,stream=False)
    elif style=='gemini':
        model=config['model'].removeprefix('models/')
        if not re.fullmatch(r'[A-Za-z0-9][A-Za-z0-9_.:-]{0,159}',model):
            raise ValueError('Gemini 模型 ID 格式无效，请使用模型列表中的名称')
        route='/models/'+urllib.parse.quote(model,safe='')+':generateContent'
        body=dict(systemInstruction=dict(parts=[dict(text=system)]),
                  contents=[dict(role='user',parts=[dict(text=content)])],
                  generationConfig=dict(maxOutputTokens=max_tokens))
    else:raise ValueError('不支持的模型接口协议')
    return api_root(config)+route,body,headers(config)


class ModelResponseError(ValueError):
    """A safe, actionable failure category; never includes model text or secrets."""
    def __init__(self,code,message):
        super().__init__(message)
        self.code=code


def response_text(style,result):
    if not isinstance(result,dict) or result.get('error'):
        raise ModelResponseError('invalid_response','模型服务未返回有效响应，请检查接口协议与配置')
    reason=None;reasoning=False
    try:
        if style=='responses':
            text='\n'.join(c.get('text','') for out in result.get('output',[]) if out.get('type')=='message'
                           for c in out.get('content',[]) if c.get('type')=='output_text')
            reason=(result.get('incomplete_details') or {}).get('reason') or result.get('status')
            complete=result.get('status') in (None,'completed')
        elif style=='chat_completions':
            choice=(result.get('choices') or [{}])[0];message=choice.get('message') or {}
            text=message.get('content','');reason=choice.get('finish_reason')
            if text is None:text=''
            reasoning=bool(message.get('reasoning_content'))
            if isinstance(text,list):
                text='\n'.join(part['text'] for part in text if isinstance(part,dict) and part.get('type')=='text' and isinstance(part.get('text'),str))
            complete=reason in (None,'stop','end_turn','eos')
        elif style=='anthropic_messages':
            text='\n'.join(c.get('text','') for c in result.get('content',[]) if c.get('type')=='text')
            reason=result.get('stop_reason');complete=reason in ('end_turn','stop_sequence')
        elif style=='gemini':
            candidate=(result.get('candidates') or [{}])[0]
            parts=candidate.get('content',{}).get('parts',[])
            text='\n'.join(p.get('text','') for p in parts if not p.get('thought'))
            reason=candidate.get('finishReason') or result.get('promptFeedback',{}).get('blockReason')
            complete=(reason=='STOP' and not result.get('promptFeedback',{}).get('blockReason')
                      and not any('functionCall' in p for p in parts))
        else:raise ValueError('不支持的模型接口协议')
    except (AttributeError,TypeError,IndexError,KeyError):
        raise ModelResponseError('protocol_mismatch','模型响应格式与所选接口协议不匹配，请核对接口协议。') from None
    if reason in ('length','max_tokens','MAX_TOKENS','max_output_tokens'):
        raise ModelResponseError('output_limit','模型输出达到本次长度上限，未返回完整文本。请重试；若再次出现，请缩短材料或换用更轻量的模型。')
    if reason in ('content_filter','SAFETY','RECITATION','PROHIBITED_CONTENT','refusal'):
        raise ModelResponseError('blocked','模型服务未提供可用回答，请调整问题后重试。')
    if reason in ('tool_calls','function_call'):
        raise ModelResponseError('unexpected_tool_call','模型返回了工具调用，但当前步骤需要文本回答，请检查接口兼容性。')
    if not complete:
        raise ModelResponseError('interrupted','模型生成中断，未返回完整文本，请重试。')
    if not isinstance(text,str):
        raise ModelResponseError('protocol_mismatch','模型正文格式与所选接口协议不匹配，请核对接口协议。')
    if not text.strip():
        if reasoning:
            raise ModelResponseError('reasoning_only','模型只返回了思考内容，没有回答正文。请重试或换用非思考模型。')
        raise ModelResponseError('empty_text','模型服务返回了空正文，请重试或检查模型与接口协议是否兼容。')
    return text


def model_page(config,result):
    if not isinstance(result,dict) or result.get('error'):
        raise ValueError('模型列表响应无效，可手动填写模型 ID')
    style=config['style']
    field='models' if style=='gemini' else 'data'
    items=result.get(field)
    if not isinstance(items,list):raise ValueError('模型列表格式与所选协议不匹配，可手动填写模型 ID')
    ids=[]
    for item in items:
        if not isinstance(item,dict):continue
        name=item.get('name' if style=='gemini' else 'id')
        if style=='gemini' and 'generateContent' not in item.get('supportedGenerationMethods',['generateContent']):continue
        if isinstance(name,str):ids.append(name.removeprefix('models/') if style=='gemini' else name)
    params={}
    if style=='gemini' and isinstance(result.get('nextPageToken'),str):params['pageToken']=result['nextPageToken']
    if style=='anthropic_messages' and result.get('has_more') and isinstance(result.get('last_id'),str):params['after_id']=result['last_id']
    return ids,params
