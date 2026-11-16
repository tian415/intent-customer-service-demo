let csrf = ''
let sessionRevision = 0
export const setCsrf = (value:string) => { csrf = value; sessionRevision++ }
export const getSessionRevision = () => sessionRevision
export class ApiError extends Error { constructor(message:string, public status:number) { super(message) } }
export async function api<T>(path:string, options:{method?:string;body?:unknown;notifyUnauthorized?:boolean} = {}):Promise<T> {
  const requestSessionRevision = sessionRevision
  const method = options.method ?? 'GET'
  const headers:Record<string,string> = { 'Accept':'application/json' }
  if (method !== 'GET') { headers['Content-Type']='application/json'; headers['X-Requested-With']='ticket-ui'; if(csrf) headers['X-CSRF-Token']=csrf }
  let response:Response
  try { response = await fetch(`/api${path}`, {method,headers,credentials:'same-origin', ...(options.body === undefined ? {} : {body:JSON.stringify(options.body)})}) }
  catch { throw new ApiError('无法连接服务，请检查本地后端并重试。',0) }
  const data = await response.json().catch(() => null)
  if(!response.ok) {
    if(response.status===401 && requestSessionRevision===sessionRevision && path!=='/auth/login' && options.notifyUnauthorized!==false) window.dispatchEvent(new Event('session-expired'))
    const detail = data?.detail
    const message = typeof detail==='string' ? detail : Array.isArray(detail) ? detail.map((x:{loc?:string[];msg?:string})=>`${x.loc?.slice(1).join('.') ?? '字段'}：${x.msg ?? '格式无效'}`).join('；') : `请求失败（${response.status}）`
    throw new ApiError(message,response.status)
  }
  return data as T
}
export const errorText = (e:unknown) => e instanceof Error ? e.message : '操作失败，请重试。'
